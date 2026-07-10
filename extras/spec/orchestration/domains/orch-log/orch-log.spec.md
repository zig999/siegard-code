# orch-log — Subsystem Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Technical contract: `orch-log.contract.md`
> Fidelity: prescriptive. Current-behavior claims cite `dist/.claude/lib/orch_core.py`.

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | Provide the append-only, hash-chained event log that is the single source of truth for the engine (INV-01). |
| Core entity | `Event` — an immutable, hash-linked record (`orch_core.py:471`). |
| Bounded context | Physical persistence: write path (append/claim), read path (filtered reads), integrity (verify/recover), payload externalization (blobs). |
| Out of scope | Interpreting events into state (orch-state); deciding what to append (orch-dispatch/orch-control). |

## 2. Actors

| Actor | Description | Permissions |
|-------|-------------|-------------|
| orchestrator | Meta/phase orchestrator | append control/phase/task events; claim tasks; read; verify |
| worker | Leaf agent (via `emit.py`) | append `task_progress`/`task_completed`/`task_failed` only (guard-railed) |
| reaper | stale-monitor path | append `task_failed(stale_timeout)` + `task_scheduled_retry` |
| hook | on_stop / on_subagent_stop | append synthesized `task_failed` + `task_scheduled_retry` |
| operator | Human (via recovery CLI) | append `log_recovered`; run `verify --recover` |

## 3. Use Cases

### UC-01 — Append event
**Actor:** orchestrator / worker / reaper / hook
**Pre:** `event_type ∈ EventType`; `data` holds the required fields for that type.
**Post:** exactly one new line appended; `seq = prev.seq + 1`; hash chain extended; fsync'd.
**Main flow:**
1. Validate `event_type` is known (else UnknownEventType).
2. Validate required `data` fields + enum values (else EventValidationError).
3. Acquire `LogLock` (exclusive, `LOCK_TIMEOUT_S`).
4. Run registered append-time preconditions for the type (BR-06).
5. Recompute the tail event's hash; abort if it no longer matches (BR-02).
6. Compute `seq`, `prev_hash`; externalize `data` to a blob if serialized size > `MAX_INLINE_PAYLOAD` (UC-06).
7. Build `Event`, compute `hash`, write one `os.write` on an `O_APPEND` fd, `fsync`.
**Alternative flows:**
`2a` missing data field / bad enum → EventValidationError (ERR-02), no write.
`3a` lock not acquired in `LOCK_TIMEOUT_S` → LockTimeoutError (ERR-01).
`4a` precondition returns a reason → PreconditionViolation (ERR-09), no write.
`5a` tail hash mismatch → CorruptedLogError (ERR-03), no write.
`1a` unknown type → UnknownEventType (ERR-05).
**Related contract:** op `append_event` / CLI `append.py`. (`orch_core.py:1305`, `_append_event_locked:1355`)

### UC-02 — Claim task (atomic check-and-claim)
**Actor:** orchestrator
**Pre:** target task exists and is `READY`.
**Post:** a single `task_claimed` appended; or a structured refusal, with no write.
**Main flow:**
1. Validate `task_claimed` data.
2. Acquire `LogLock`.
3. `reduce_all()` inside the lock; read target task status.
4. If `status == READY`, append `task_claimed` under the same lock acquisition.
**Alternative flows:**
`3a` task absent → return `(None, "task_not_found")`.
`3b` status ≠ READY → return `(None, "not_ready:<status>")`; caller MUST NOT spawn a worker.
`3c` log cannot be replayed → IllegalTransition / CorruptedLogError.
**Related contract:** op `claim_task` / CLI `claim.py`. Closes the double-dispatch race (two orchestrators reading the same READY task). (`orch_core.py:1426`)

### UC-03 — Read events (filtered)
**Actor:** any
**Pre:** log file exists (absent → empty stream).
**Post:** an ordered list/stream of matching events; blobs resolved when a `phase` filter is active.
**Main flow:** iterate from `from_seq`; filter by `task_id` / `event_type` / `phase`; apply `tail` last-N.
**Alternative flows:** `1a` truncated final line → tolerated (skipped), not an error.
**Related contract:** op `read_events` / `read_events_filtered` / CLI `read.py`. (`orch_core.py:666,728`)

### UC-04 — Verify chain integrity
**Actor:** operator / integrity check
**Pre:** log file exists.
**Post:** a verdict: `verified` with count, or the first offending seq.
**Main flow:** walk events; recompute each `hash`; assert each `prev_hash` equals the predecessor's `hash`.
**Alternative flows:** `2a` hash/linkage mismatch → report first bad seq (verdict not-ok). `mode=cached` verifies only the unverified suffix.
**Related contract:** op `verify_chain` / `verify_chain_cached` / CLI `verify.py`. (`orch_core.py:802,931`)

### UC-05 — Recover corrupted log
**Actor:** operator
**Pre:** `--confirm` AND `--from-seq <seq>` AND `--operator <identity>` all present (safety gate).
**Post:** corrupt tail archived; log truncated at `from_seq`; a `log_recovered` marker appended.
**Alternative flows:** `Pa` any flag missing → refusal (no truncation).
**Related contract:** CLI `verify.py --recover`. Emits EV-29.

### UC-06 — Externalize / resolve blob
**Actor:** system (append / reduce)
**Pre:** —
**Post:** oversized `data` stored as `{_blob_ref,_size,_blob_hash}`; readers get the full data back.
**Main flow:** on append, if serialized `data` > `MAX_INLINE_PAYLOAD`, write `.orch/blobs/<ref>` + sha256 and store the reference; on read, `load_blob_data` resolves and re-checks the hash.
**Alternative flows:** `2a` blob hash mismatch → BlobIntegrityError (ERR-06). `2b` blob missing → BlobNotFoundError (ERR-07).
**Related contract:** ops `is_blob_ref:1140` / `externalize_blob:1150` / `load_blob_data:1167`.

## 4. Business Rules

### BR-01 — Hash-chain continuity (enforces INV-01, INV-03)
Every event stores `prev_hash` = predecessor's `hash`; the first event uses `prev_hash = "GENESIS"`. `hash` = SHA-256 of canonical JSON excluding `hash`. Referenced by UC-01, UC-04. (`orch_core.py:1375-1403`)

### BR-02 — Refuse to chain onto a corrupt tail
Before writing, the tail event's hash is recomputed; on mismatch the append raises CorruptedLogError and writes nothing — a corrupt tail never propagates an invalid `prev_hash` into following events. Related UC: UC-01. (`orch_core.py:1371-1374`, SIEGARD-03)

### BR-03 — Single-writer serialization
All appends occur under an exclusive `LogLock` (POSIX flock / msvcrt on Windows), acquired within `LOCK_TIMEOUT_S = 10.0`. Related UC: UC-01, UC-02. Enforces INV-05 substrate. (`orch_core.py:150`, `:107`)

### BR-04 — Atomic, durable append
The event line is written with a single `os.write` on an `O_APPEND` fd followed by `fsync`, minimizing the partial-line window on mid-append kill. Related UC: UC-01. (`orch_core.py:1416-1419`)

### BR-05 — Payload externalization threshold
`data` whose canonical serialization exceeds `MAX_INLINE_PAYLOAD = 3500` bytes is externalized to `.orch/blobs/` with a sha256; otherwise stored inline. Keeps the log line small (≤ PIPE_BUF for atomicity). Related UC: UC-01, UC-06. (`orch_core.py:106,1380-1389`)

### BR-06 — Append-time preconditions run under the lock
Registered precondition functions run after data validation and before the write, inside the lock, over a fresh read; a non-None return raises PreconditionViolation and rejects the append. Default registry installs only the `phase_transitioned` guard. Related UC: UC-01. (`orch_core.py:1345-1351`, `install_transition_preconditions`)

### BR-07 — Monotonic sequence
`seq` starts at 1 and increases by exactly 1 per appended event; it is assigned inside the lock from the tail. Related UC: UC-01. (`orch_core.py:1375`)

### BR-08 — Schema validation precedes any write
Required `data` fields and closed enums (tier, failure/skip reason) are validated before the lock is taken; invalid input never reaches the log. Related UC: UC-01. (`_validate_event_data:623`, invoked pre-lock at `:1337`; lock at `:1341`)

> Idempotency (INV-04) and deterministic ordering (INV-05) are *realized* by the
> orch-state reducer over this log — the log permits a duplicate; the reducer makes
> it an audited no-op. orch-log owns only INV-01/INV-03 and the INV-05 substrate.

## 5. State Machine

N/A — orch-log has no entity state machine. The task and phase state machines are
owned by orch-state (ST-01) and orch-phases (ST-02).

## 6. Error Behaviors

| Situation | Raised | ERR | Description |
|-----------|--------|-----|-------------|
| Unknown event_type | `UnknownEventType` | ERR-05 | type not in `EventType` |
| Missing required data / bad enum | `EventValidationError` | ERR-02 | rejected pre-lock |
| Precondition rejection | `PreconditionViolation` | ERR-09 | e.g. forward transition without approval |
| Corrupt tail on append | `CorruptedLogError` | ERR-03 | refuses to extend a broken chain |
| Broken chain / bad JSON on verify | `CorruptedLogError` | ERR-03 | reported with first bad seq |
| Lock not acquired in 10s | `LockTimeoutError` | ERR-01 | contended or stuck writer |
| Blob hash mismatch | `BlobIntegrityError` | ERR-06 | externalized payload tampered/corrupt |
| Blob reference missing | `BlobNotFoundError` | ERR-07 | referenced blob file absent |

## 7. Cross-Domain Dependencies

| Domain | Type | Description |
|--------|------|-------------|
| orch-state | produces | orch-state consumes the event stream to derive all state |
| orch-dispatch | synchronizes | uses `claim_task` (UC-02) for atomic dispatch |
| orch-resilience | consumes | appends synthesized terminals + scheduled retries |
| orch-control | consumes | appends control/phase events; reads for decisions (INV-08) |

## 8. Out of Scope

- Deriving or interpreting state (orch-state).
- Retry/backoff/DLQ policy (orch-resilience).
- Multi-node/distributed logs — the log is a single local file.

## 9. Local Glossary

| Term | Definition |
|------|------------|
| Genesis | The `prev_hash` sentinel `"GENESIS"` of the first event. |
| Tail | The last event currently in the log. |
| Blob | An externalized oversized payload stored under `.orch/blobs/`. |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial orch-log spec (UC-01..06, BR-01..08) | — |
