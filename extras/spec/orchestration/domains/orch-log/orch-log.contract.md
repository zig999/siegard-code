# orch-log — Technical Contract

> Stack: Python 3.10+ stdlib only | Storage: `.orch/log.jsonl` (JSONL) | Version: 0.1.0 | Status: draft | Layer: permanent
> Business spec: `orch-log.spec.md`
> The engine's analog of `openapi.yaml`: the event envelope, the CLI surface, and the
> library surface of the log subsystem.

## 1. Stack and Patterns

| Aspect | Value | Note |
|--------|-------|------|
| Language | Python 3.10+ | zero external deps (CLAUDE.md constraint) |
| Storage | `.orch/log.jsonl` | one JSON object per line, append-only |
| Locking | POSIX `flock` (msvcrt on Windows) | exclusive, `LOCK_TIMEOUT_S = 10.0` |
| Hashing | SHA-256 over canonical JSON | `Event.compute_hash` |
| Blobs | `.orch/blobs/<event_id>.json` | payloads > `MAX_INLINE_PAYLOAD` |

## 2. Data Model

### Event envelope (`orch_core.py:471`)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `seq` | int | ≥ 1, monotonic +1 | assigned under lock from the tail |
| `event_id` | string | unique | `new_event_id()` |
| `ts` | string | ISO-8601 UTC, ms precision + `Z` | `now_iso()` |
| `agent` | string | non-empty | emitting actor identity |
| `event_type` | string | ∈ `EventType` | see event-catalog.md |
| `task_id` | string \| null | — | null for non-task events |
| `attempt` | int | ≥ 1 | attempt this event pertains to |
| `data` | object | required fields per type (`_REQUIRED_DATA_FIELDS:547`) | inline payload or blob ref |
| `prev_hash` | string | 64-hex or `"GENESIS"` | predecessor's `hash` |
| `hash` | string | 64-hex | SHA-256 of canonical JSON excluding `hash` |

### Blob reference (replaces `data` when externalized)

```json
{ "_blob_ref": "<event_id>.json", "_size": 4821, "_blob_hash": "<sha256>" }
```

### File layout

```
.orch/
├── log.jsonl          # the event log (this contract)
├── log.jsonl.lock     # flock target
└── blobs/<id>.json    # externalized payloads
```

## 3. CLI Contracts

All scripts under `skills/orch-log/scripts/`. Exit 0 on success; errors in stdout JSON unless noted.

### append.py
```
--agent <id> (req)  --event-type <type> (req)  --task-id <id>  --attempt <n=1>  --data <json='{}'>
```
stdout: the appended event as JSON (`event.to_dict()`). Errors: `{"status":"error","reason":...}`, exit 1.

### claim.py
```
--agent <id> (req)  --task-id <id> (req)  --attempt <n=1>  --data <json='{}'>
```
stdout: `{"claimed": true, "event": {...}}` on success, OR `{"claimed": false, "reason": "task_not_found"|"not_ready:<status>"}` on refusal (`claim.py:85,88`).

### read.py
```
--from-seq <n=0>  --tail <n>  --task-id <id>  --event-type <type>  --phase <name>
```
stdout: one JSON event per line (filtered, ordered by seq).

### verify.py
```
--mode <strict|audit=strict>  [--recover --confirm --from-seq <n> --operator <id>]
```
stdout: `{"ok": bool, "message": ..., "mode": ..., "events_verified": N}` plus optional `first_error_seq` / `error_details` on failure (`verify.py:113-126`).
`--recover` requires `--confirm` + `--from-seq` + `--operator` (safety gate); archives tail, truncates, appends `log_recovered`.
> Conformance note (CONF-04): the CLI always calls `verify_chain`; `verify_chain_cached` has no CLI exposure — the cached-verify surface is library-only.

## 4. Library Contract (`orch_core`)

| Function | Signature (abridged) | Pre / Post | Raises |
|----------|----------------------|-----------|--------|
| `append_event` | `(agent, event_type, task_id=None, attempt=1, data=None) -> Event` | validates + locks + chains + writes | UnknownEventType, EventValidationError, PreconditionViolation, CorruptedLogError, LockTimeoutError, OSError |
| `claim_task` | `(agent, task_id, attempt=1, data=None) -> tuple[Event\|None, str\|None]` | atomic check-and-claim under lock | EventValidationError, IllegalTransition, CorruptedLogError, LockTimeoutError |
| `read_events` | `(from_seq=0) -> Iterator[Event]` | tolerates truncated last line | CorruptedLogError (mid-log bad JSON) |
| `read_events_filtered` | `(from_seq=0, task_id=None, event_type=None, phase=None, tail=None) -> list[Event]` | AND-filter; resolves blobs when phase set | — |
| `last_event` | `() -> Event \| None` | tail or None | — |
| `verify_chain` | `(...) -> VerifyResult` | full walk, recompute hashes | CorruptedLogError |
| `verify_chain_cached` | `() -> VerifyResult` | verifies only the unverified suffix | CorruptedLogError |
| `externalize_blob` | `(data, event_id) -> tuple[str,str]` | writes blob + returns (ref, hash) | OSError |
| `load_blob_data` | `(event) -> dict` | resolves + re-checks hash | BlobIntegrityError, BlobNotFoundError |
| `is_blob_ref` | `(data) -> bool` | true if `data` is a blob reference | — |

## 5. Constants

| Constant | Value | Role |
|----------|-------|------|
| `MAX_INLINE_PAYLOAD` | 3500 (bytes) | externalization threshold |
| `LOCK_TIMEOUT_S` | 10.0 (s) | max wait for the log lock |
| `SNAPSHOT_EVERY_N_EVENTS` | 100 | reducer snapshot cadence (used by orch-state) |

## 6. Out of Scope

- Reducer/state derivation (orch-state contract).
- Retry/DLQ/circuit contracts (orch-resilience contract).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Event envelope, CLI + library contracts, constants | — |
