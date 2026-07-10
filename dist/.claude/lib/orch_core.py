"""
Orchestrator core library.

Event sourcing engine for multi-phase Claude Code workflow orchestration.
Zero external dependencies — Python 3.10+ stdlib only.
"""
from __future__ import annotations

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover — Windows (fcntl is POSIX-only)
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False
    import msvcrt
import fnmatch
import hashlib
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class OrchError(Exception):
    """Base class for all orch_core exceptions."""


class LockTimeoutError(OrchError, TimeoutError):
    """Could not acquire log lock within timeout."""


class EventValidationError(OrchError):
    """Event doesn't match schema (envelope or type-specific)."""


class CorruptedLogError(OrchError):
    """Log file is corrupted: invalid JSON or broken hash chain."""


class IllegalTransition(OrchError):
    """Event would cause illegal state transition.

    Handlers raise this with a human-readable message only. `apply_event`
    enriches the instance in-flight with the offending event's context
    (`seq`, `task_id`, `event_type`, `workflow_id`, `phase`) so downstream
    consumers — e.g. the monitor — can pinpoint the event without re-scanning
    the log. Attributes are `None` until enriched.
    """

    seq: int | None = None
    task_id: str | None = None
    event_type: str | None = None
    workflow_id: str | None = None
    phase: str | None = None


class UnknownEventType(OrchError):
    """Event type not recognized."""


class BlobIntegrityError(OrchError):
    """Blob hash doesn't match _blob_hash (tampering detected)."""


class BlobNotFoundError(OrchError):
    """Blob file referenced by event doesn't exist."""


class ConfigError(OrchError):
    """Config file is missing, invalid, or has wrong schema."""


class PreconditionViolation(OrchError):
    """Append rejected: event would violate a registered log-ordering precondition."""


# ---------------------------------------------------------------------------
# Constants and paths
# ---------------------------------------------------------------------------

# C7: Resolve project root from env var so hooks work regardless of CWD.
_orch_root: Path = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

ORCH_DIR: Path = _orch_root / ".orch"
LOG_PATH: Path = ORCH_DIR / "log.jsonl"
LOCK_PATH: Path = ORCH_DIR / "log.jsonl.lock"
STATE_DIR: Path = ORCH_DIR / "state"
DLQ_DIR: Path = ORCH_DIR / "dlq"
AUDIT_DIR: Path = ORCH_DIR / "audit"
METRICS_DIR: Path = ORCH_DIR / "metrics"
BLOBS_DIR: Path = ORCH_DIR / "blobs"
WORKERS_DIR: Path = ORCH_DIR / "workers"
CONFIG_PATH: Path = ORCH_DIR / "config.json"

MAX_INLINE_PAYLOAD: int = 3500
LOCK_TIMEOUT_S: float = 10.0
# Used by snapshots (Task 1.8 — deferred); kept for API compatibility.
SNAPSHOT_EVERY_N_EVENTS: int = 100


def ensure_dirs() -> None:
    """Creates all .orch/ subdirectories if missing. Idempotent."""
    for d in (ORCH_DIR, STATE_DIR, DLQ_DIR, AUDIT_DIR, METRICS_DIR, BLOBS_DIR, WORKERS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

def _lock_acquire_nb(fd: int) -> None:
    """Acquire an exclusive non-blocking lock on fd.

    Cross-platform seam: POSIX flock when available, msvcrt byte-range lock
    on Windows. Raises BlockingIOError on both platforms when the lock is
    already held, so the LogLock polling loop is platform-agnostic.
    """
    if _HAS_FCNTL:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:  # pragma: no cover — exercised via fake-msvcrt subprocess test
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            # msvcrt raises plain OSError/PermissionError when the byte is
            # locked elsewhere; normalize to BlockingIOError for the caller.
            raise BlockingIOError(str(exc)) from exc


def _lock_release(fd: int) -> None:
    """Release the lock acquired by _lock_acquire_nb."""
    if _HAS_FCNTL:
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:  # pragma: no cover — exercised via fake-msvcrt subprocess test
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


class LogLock:
    """
    Exclusive lock on the log lock file (POSIX flock; msvcrt on Windows).

    Non-blocking with polling loop and timeout.
    Releases automatically on context exit, even on exception.

    Usage:
        with LogLock():
            # safe to write to log
    """

    def __init__(
        self,
        lock_path: Path | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self._lock_path = lock_path or LOCK_PATH
        self._timeout_s = timeout_s if timeout_s is not None else LOCK_TIMEOUT_S
        self._fd: int | None = None

    def __enter__(self) -> "LogLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        start = time.monotonic()
        while True:
            try:
                _lock_acquire_nb(self._fd)
                return self
            except BlockingIOError:
                if time.monotonic() - start >= self._timeout_s:
                    os.close(self._fd)
                    self._fd = None
                    raise LockTimeoutError(
                        f"Could not acquire log lock within {self._timeout_s}s"
                    )
                time.sleep(0.05)

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._fd is not None:
            _lock_release(self._fd)
            os.close(self._fd)
            self._fd = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_event_id() -> str:
    """Generates a unique event identifier with evt_ prefix (UUID-based, 26 hex chars)."""
    return f"evt_{uuid.uuid4().hex.upper()[:26]}"


def now_iso() -> str:
    """Returns current UTC time as ISO 8601 with millisecond precision."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def parse_iso(ts: str) -> datetime:
    """Parses ISO 8601 UTC timestamp string to datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _elapsed_seconds(now: str, then: str) -> float:
    """Seconds between two ISO timestamps, tolerant of a tz-naive operand.

    All engine timestamps are UTC, but a legacy / hand-edited / externally-injected
    event may carry a last_event_at with no 'Z'/offset. Subtracting a naive from an
    aware datetime raises TypeError, which on the SubagentStop hot path would crash
    the hook (and the reaper). Coerce any naive operand to UTC before subtracting.
    """
    a = parse_iso(now)
    b = parse_iso(then)
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (a - b).total_seconds()


def _safe_parse_iso(ts: str) -> datetime | None:
    """Parses ISO 8601 timestamp; returns None on any parse failure (never raises)."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


# 5-a: no '_' — underscore is the task-ID namespace delimiter (see slugify_workflow_id).
_WORKFLOW_ID_RE = re.compile(r"[A-Za-z0-9.-]+")


def slugify_workflow_id(raw: str | None) -> str | None:
    """Returns a sanitized human-readable workflow_id, or None if unusable (F-04).

    A usable id is a non-empty string of [A-Za-z0-9.-] with no path separators
    (a workflow_id keys a session directory `.orch/sessions/<id>/`, so it must be a
    single safe path segment). The id is lowercased: targets run on a Windows
    case-insensitive filesystem, so 'Chat-UI' and 'chat-ui' would otherwise be two
    distinct log ids resolving to the SAME session dir — silently clobbering one
    run's artifacts (a P1 'log is the truth' violation). Lowercasing is also the
    project's domain-slug convention. UUIDs pass this filter — they are valid ids —
    but the engine should only MINT a UUID-like opaque id when nothing readable was
    requested; see resolve_workflow_id.

    5-a: '_' is mapped to '-' — underscore is the component delimiter inside
    namespaced task IDs (sdd_{wf}_{domain}_{stage}), so a workflow id containing
    '_' would make the namespace non-injective: workflow 'pay_v2' + domain 'auth'
    and workflow 'pay' + domain 'v2_auth' would mint the SAME task id, and every
    startswith('dev_pay_') prefix filter would leak into 'pay_v2'. Mapping (not
    rejecting) keeps operator-requested ids usable.
    """
    if not isinstance(raw, str):
        return None
    raw = raw.strip().lower().replace("_", "-")
    if not raw or "/" in raw or "\\" in raw or raw in (".", ".."):
        return None
    if not _WORKFLOW_ID_RE.fullmatch(raw):
        return None
    return raw


def resolve_workflow_id(
    requested: str | None,
    today: str,
    existing: "Iterator[str] | tuple" = (),
) -> tuple[str, bool]:
    """Resolves the effective workflow_id for a first-run workflow (F-04).

    The engine used to mint an opaque uuid4 unconditionally, discarding the
    readable id the operator passed to /u-spec — sessions became unreachable by
    name. This honors a usable requested id verbatim, and otherwise falls back to
    a READABLE slug `spec-<YYYYMMDD>` (disambiguated with `-2`, `-3`, … against
    existing session ids), never an opaque UUID.

    Args:
        requested: the workflow_id from the invocation prompt (may be None/empty/invalid).
        today:     compact date stamp `YYYYMMDD` for the fallback slug.
        existing:  already-used workflow ids (e.g. `.orch/sessions/*` names) to avoid collisions.

    Returns:
        (workflow_id, diverged) where `diverged` is True only when a non-empty id
        was requested but could not be used (so the caller logs the divergence
        instead of silently substituting).
    """
    existing = set(existing or ())
    slug = slugify_workflow_id(requested)
    if slug is not None:
        return slug, False
    base = f"spec-{today}"
    candidate = base
    n = 2
    while candidate in existing:
        candidate = f"{base}-{n}"
        n += 1
    diverged = bool(requested and str(requested).strip())
    return candidate, diverged


def sha256_hex(data: bytes) -> str:
    """Returns SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Canonical JSON serialization for hashing. Sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Canonical event types. 30 total."""

    # Task lifecycle (9)
    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_SCHEDULED_RETRY = "task_scheduled_retry"
    TASK_RETRIED = "task_retried"
    TASK_DLQ = "task_dlq"
    # TASK_SKIPPED: emitted when an orchestrator skips a step in a restricted mode
    # (e.g., implementation_only or targeted). Required by DECLARATIVE_TRUNCATION.
    TASK_SKIPPED = "task_skipped"

    # Phase lifecycle (7)
    PHASE_DECLARED = "phase_declared"
    PHASE_ENTERED = "phase_entered"
    PHASE_EXIT_CRITERION_MET = "phase_exit_criterion_met"
    PHASE_EXIT_APPROVED = "phase_exit_approved"
    PHASE_TRANSITIONED = "phase_transitioned"
    PHASE_PAUSED = "phase_paused"
    PHASE_RESUMED = "phase_resumed"

    # Improve flow (1)
    # Emitted by orchestrator-sdd when workflow_type=="improve" and SDD phase
    # completes, closing the spec_change_status loop in improve-scope.json.
    SPEC_PIPELINE_RETURN = "spec_pipeline_return"

    # Dispatch governance (3)
    # DISPATCH_DECISION: emitted by an orchestrator before each batch of task_claimed
    # events; captures batch members, rationale, and applied constraints.
    # CONTEXT_BUDGET_EVALUATED: emitted before spawning a worker; records estimated
    # context size and any mitigation applied (split, summarize) per WORKER_CONTEXT_BUDGET.
    # OPERATION_MODE_DECLARED: emitted by an orchestrator before any worker spawn,
    # declaring the operation mode for the current invocation per ORCHESTRATOR_AUTHORITY.
    DISPATCH_DECISION = "dispatch_decision"
    CONTEXT_BUDGET_EVALUATED = "context_budget_evaluated"
    OPERATION_MODE_DECLARED = "operation_mode_declared"

    # Management and operations (9)
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    ESCALATION = "escalation"
    HUMAN_RESPONSE = "human_response"
    SNAPSHOT = "snapshot"
    LOG_RECOVERED = "log_recovered"
    PREFLIGHT_FAILED = "preflight_failed"
    # Emitted by the orchestrator at the start of each dispatch loop iteration.
    # Used by on_stop.py to detect a stale orchestrator (alive but not making progress).
    ORCHESTRATOR_HEARTBEAT = "orchestrator_heartbeat"
    # Supervised auto-resume (E2 / B(b) — CONF-05 follow-up). Both AUDIT-ONLY: no reducer
    # handler, so the log is the single source for budget/cooldown accounting (P1/P2).
    # ORCHESTRATOR_RESUME_REQUESTED: appended by supervisor_tick.py when a phase is stalled
    # (total phase silence) and within the resume budget. ORCHESTRATOR_RESUMED: appended by
    # the /u-supervise command after it re-invokes the meta-orchestrator in foreground.
    ORCHESTRATOR_RESUME_REQUESTED = "orchestrator_resume_requested"
    ORCHESTRATOR_RESUMED = "orchestrator_resumed"
    # Handoff loop-closure (prod-hardening task 08, A3-F5): a receipt that a
    # manifest was consumed — a logged event (not a session side-file) so
    # consumed/orphan handoff state is derived from the log (P1/P12).
    HANDOFF_RECEIPT = "handoff_receipt"
    # Review shared-suite-run flow (prod-hardening task 11): emitted by
    # orchestrator-review around SHARED_SUITE_RUN. Previously undefined — the
    # append.py calls would raise UnknownEventType at runtime (latent crash).
    SUITE_RUN_STARTED = "suite_run_started"
    SUITE_RUN_COMPLETED = "suite_run_completed"

    @classmethod
    def is_worker_emittable(cls, event_type: str) -> bool:
        """Returns True if workers are allowed to emit this type."""
        return event_type in {
            cls.TASK_PROGRESS.value,
            cls.TASK_COMPLETED.value,
            cls.TASK_FAILED.value,
        }

    @classmethod
    def is_terminal_for_attempt(cls, event_type: str) -> bool:
        """Returns True if this event closes a task attempt."""
        return event_type in {
            cls.TASK_COMPLETED.value,
            cls.TASK_FAILED.value,
        }

    @classmethod
    def values(cls) -> frozenset[str]:
        """Returns all valid event type string values."""
        return _EVENT_TYPE_VALUES


# Cached at module load — avoids creating a new set on every append_event call.
_EVENT_TYPE_VALUES: frozenset[str] = frozenset(e.value for e in EventType)


class TaskStatus(str, Enum):
    """Derived task statuses (computed by reducer, never stored in events)."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    DLQ = "dlq"
    CANCELLED = "cancelled"

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        # SKIPPED is terminal for dependency evaluation per STEP_DEPENDENCIES principle.
        # CANCELLED is reserved for future use; no handler produces it yet.
        return status in {cls.COMPLETED.value, cls.SKIPPED.value, cls.DLQ.value}


class PhaseStatus(str, Enum):
    """Derived phase statuses."""
    PENDING = "pending"
    ACTIVE = "active"
    EXIT_APPROVED = "exit_approved"
    COMPLETED = "completed"
    PAUSED = "paused"


class Tier(str, Enum):
    """Task priority tiers governing retry, timeout, and model selection."""
    CRITICAL = "critical"
    STANDARD = "standard"
    BULK = "bulk"

    @property
    def default_max_attempts(self) -> int:
        return {"critical": 5, "standard": 3, "bulk": 1}[self.value]

    @property
    def default_stale_seconds(self) -> int:
        return {"critical": 600, "standard": 300, "bulk": 120}[self.value]

    @property
    def default_base_delay_s(self) -> float:
        return {"critical": 15.0, "standard": 30.0, "bulk": 0.0}[self.value]


# Heartbeat-staleness threshold for an active orchestrator (seconds). An active
# phase with non-terminal tasks but no orchestrator_heartbeat within this window
# is treated as a stalled orchestrator. Single source of truth: detect_stale_orchestrator
# defaults to it; monitor.py imports it; on_stop.py reaches it via detect_stale_orchestrator.
ORCHESTRATOR_STALE_SECONDS = 900  # 15 minutes


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """A single immutable event in the orchestrator log."""

    seq: int
    event_id: str
    ts: str
    agent: str
    event_type: str
    task_id: str | None
    attempt: int
    data: dict[str, Any]
    prev_hash: str
    hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Converts to dict for JSON serialization."""
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "ts": self.ts,
            "agent": self.agent,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "attempt": self.attempt,
            "data": self.data,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        """Creates Event from dict (inverse of to_dict)."""
        return cls(
            seq=d["seq"],
            event_id=d["event_id"],
            ts=d["ts"],
            agent=d["agent"],
            event_type=d["event_type"],
            task_id=d.get("task_id"),
            attempt=d["attempt"],
            data=d["data"],
            prev_hash=d["prev_hash"],
            hash=d.get("hash", ""),
        )

    def canonical_json(self) -> str:
        """
        Canonical JSON for hashing. Excludes the `hash` field. Keys sorted.
        Deterministic: same event always produces same string.
        """
        d = self.to_dict()
        d.pop("hash", None)
        return canonical_json(d)

    def compute_hash(self) -> str:
        """Computes SHA-256 hash of the canonical representation (excludes hash field)."""
        return sha256_hex(self.canonical_json().encode("utf-8"))


# ---------------------------------------------------------------------------
# Event data validation
# ---------------------------------------------------------------------------

_TASK_EVENTS = {
    EventType.TASK_CREATED.value,
    EventType.TASK_CLAIMED.value,
    EventType.TASK_PROGRESS.value,
    EventType.TASK_COMPLETED.value,
    EventType.TASK_FAILED.value,
    EventType.TASK_SCHEDULED_RETRY.value,
    EventType.TASK_RETRIED.value,
    EventType.TASK_DLQ.value,
    EventType.TASK_SKIPPED.value,
}

_REQUIRED_DATA_FIELDS: dict[str, set[str]] = {
    EventType.TASK_CREATED.value:              {"phase", "tier", "type", "spec", "deps"},
    EventType.TASK_CLAIMED.value:              {"phase", "worker_type", "worker_id"},
    EventType.TASK_PROGRESS.value:             {"phase", "note"},
    EventType.TASK_COMPLETED.value:            {"phase", "artifacts"},
    EventType.TASK_FAILED.value:               {"phase", "reason", "retryable"},
    EventType.TASK_SCHEDULED_RETRY.value:      {"phase", "next_retry_at", "backoff_seconds", "previous_failure_seq"},
    EventType.TASK_RETRIED.value:              {"phase", "previous_attempt", "scheduled_retry_seq"},
    EventType.TASK_DLQ.value:                  {"phase", "reason", "last_error"},
    EventType.TASK_SKIPPED.value:              {"phase", "reason"},
    EventType.OPERATION_MODE_DECLARED.value:   {"phase", "mode"},
    EventType.DISPATCH_DECISION.value:         {"phase", "batch", "rationale", "constraints"},
    EventType.PHASE_DECLARED.value:            {"workflow_id", "phases"},
    EventType.PHASE_ENTERED.value:             {"phase", "order", "workflow_id"},
    EventType.PHASE_EXIT_CRITERION_MET.value:  {"phase", "criterion"},
    EventType.PHASE_EXIT_APPROVED.value:       {"phase", "criteria_met", "next_phase", "workflow_id"},
    EventType.PHASE_TRANSITIONED.value:        {"from_phase", "to_phase", "evidence_seq", "workflow_id"},
    EventType.PHASE_PAUSED.value:              {"phase", "reason"},
    EventType.PHASE_RESUMED.value:             {"phase", "paused_seq"},
    EventType.SPEC_PIPELINE_RETURN.value:      {"workflow_id", "session_id", "spec_change_status"},
    EventType.ESCALATION.value:                {"code", "severity", "reason", "evidence"},
    EventType.CIRCUIT_BREAKER_TRIPPED.value:   {"window_start", "window_end", "failure_count", "threshold"},
    EventType.HUMAN_RESPONSE.value:            {"escalation_seq", "action", "operator"},
    EventType.LOG_RECOVERED.value:             {"seq_truncated_from", "events_removed", "operator", "corrupt_file_path"},
    EventType.HANDOFF_RECEIPT.value:           {"manifest_id", "manifest_sha256", "consumed_by"},
    EventType.SUITE_RUN_STARTED.value:         {"phase", "suite_run_id"},
    EventType.SUITE_RUN_COMPLETED.value:       {"phase", "suite_run_id"},
}


_VALID_TIERS: frozenset[str] = frozenset(t.value for t in Tier)

# Closed enumeration of structured failure/skip reason codes used by orchestrators
# and workers. Per STRUCTURED_FAILURE_STATES principle: free-form strings are not
# permitted; reasons must come from this set.
_VALID_FAILURE_REASONS: frozenset[str] = frozenset({
    # Orchestrator-emitted (synthesis or cascade)
    "worker_exited_without_terminal",
    "cascade_from_dep",
    "max_attempts_exceeded",
    "non_retryable",
    "select_worker_failed",
    "context_budget_exceeded",
    "stale_timeout",
    "delivery_artifact_missing",
    # Worker-emitted (structural / input)
    "missing_input_spec_files",
    "schema_violation",
    "validation_failed",
    "requirement_missing",
    "improve_scope_missing",
    "internal_error",
    # Planner-emitted (handoff-driven control flow)
    "dev_impact:stop_domain_task_contracts",
})

# Closed enumeration of skip reason codes (DECLARATIVE_TRUNCATION).
_VALID_SKIP_REASONS: frozenset[str] = frozenset({
    "implementation_only_no_spec_change",
    "targeted_mode_step_not_in_scope",
    "phase_short_circuit",
})

# Failure reasons emitted ONLY by the framework when it synthesizes a terminal for
# a worker it believes died: the stale reaper (reap_stale_tasks -> stale_timeout)
# and the SubagentStop hook (worker_exited_without_terminal). A worker never emits
# these — its own task_failed carries a worker-emitted reason (validation_failed,
# internal_error, ...). This set is the key for the F2 false-positive reconciliation
# in _handle_task_completed: a synthesized FAILED that is later contradicted by a
# genuine task_completed from the same worker was a false positive, not corruption.
_SYNTHESIZED_FAILURE_REASONS: frozenset[str] = frozenset({
    "stale_timeout",
    "worker_exited_without_terminal",
})


def _validate_event_data(event_type: str, data: dict[str, Any]) -> None:
    """Validates required fields in event data. Raises EventValidationError."""
    required = _REQUIRED_DATA_FIELDS.get(event_type)
    if required is None:
        return
    missing = required - set(data.keys())
    if missing:
        raise EventValidationError(
            f"{event_type}: missing required data fields: {sorted(missing)}"
        )
    if event_type == EventType.PHASE_TRANSITIONED.value:
        to_phase = data.get("to_phase")
        if not to_phase or not isinstance(to_phase, str):
            raise EventValidationError(
                "phase_transitioned: 'to_phase' must be a non-empty string "
                "(use \"done\" for terminal transitions)"
            )
    if event_type == EventType.TASK_CREATED.value:
        tier = data.get("tier")
        if tier is not None and tier not in _VALID_TIERS:
            raise EventValidationError(
                f"task_created: tier {tier!r} must be one of {sorted(_VALID_TIERS)}"
            )
    if event_type in (EventType.TASK_FAILED.value, EventType.TASK_DLQ.value):
        reason = data.get("reason")
        if reason is not None and reason not in _VALID_FAILURE_REASONS:
            raise EventValidationError(
                f"{event_type}: reason {reason!r} must be one of "
                f"{sorted(_VALID_FAILURE_REASONS)}"
            )
    if event_type == EventType.TASK_SKIPPED.value:
        reason = data.get("reason")
        if reason is not None and reason not in _VALID_SKIP_REASONS:
            raise EventValidationError(
                f"task_skipped: reason {reason!r} must be one of "
                f"{sorted(_VALID_SKIP_REASONS)}"
            )


# ---------------------------------------------------------------------------
# Log I/O — public
# ---------------------------------------------------------------------------

def read_events(from_seq: int = 0) -> Iterator[Event]:
    """
    Yields events from the log with seq >= from_seq, in order.

    Tolerates a truncated last line (returns without raising).
    Raises CorruptedLogError on invalid JSON in the middle of the log.
    """
    if not LOG_PATH.exists():
        return

    raw_bytes = LOG_PATH.read_bytes()
    lines = raw_bytes.splitlines()
    last_idx = len(lines) - 1

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            event = Event.from_dict(d)
        except (json.JSONDecodeError, KeyError) as exc:
            if i == last_idx:
                return  # truncated last line — tolerate silently
            raise CorruptedLogError(
                f"Invalid JSON at log line {i + 1}: {exc}"
            ) from exc

        if event.seq >= from_seq:
            yield event


def last_event() -> Event | None:
    """
    Returns the last valid event in the log, or None if empty.

    Reads only the tail of the file for efficiency on large logs.
    """
    if not LOG_PATH.exists() or LOG_PATH.stat().st_size == 0:
        return None

    with open(LOG_PATH, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return None
        chunk_size = min(8192, size)
        f.seek(-chunk_size, 2)
        chunk = f.read()

    for raw_line in reversed(chunk.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        try:
            return Event.from_dict(json.loads(line))
        except (json.JSONDecodeError, KeyError):
            continue

    return None


def read_events_filtered(
    from_seq: int = 0,
    task_id: str | None = None,
    event_type: str | None = None,
    phase: str | None = None,
    tail: int | None = None,
) -> list[Event]:
    """
    Returns events matching all provided filters (AND logic).

    If tail is set, returns only the last N events after filtering.
    When phase filter is active, blob payloads are resolved transparently.
    """
    results: list[Event] = []
    for event in read_events(from_seq=from_seq):
        if task_id is not None and event.task_id != task_id:
            continue
        if event_type is not None and event.event_type != event_type:
            continue
        if phase is not None:
            # Resolve blob ref so phase field is always accessible.
            resolved = load_blob_data(event) if is_blob_ref(event.data) else event.data
            if resolved.get("phase") != phase:
                continue
        results.append(event)

    if tail is not None:
        results = results[-tail:]

    return results


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

@dataclass
class VerifyResult:
    """Result of a verify_chain call."""
    ok: bool
    message: str
    mode: str
    events_verified: int = 0
    first_error_seq: int | None = None
    error_details: list[dict[str, Any]] = field(default_factory=list)
    truncation_candidate: dict[str, Any] | None = None


def _iter_events_from_path(path: Path) -> Iterator[Event]:
    """
    Yields events from an explicit path.

    Tolerates a truncated last line.
    Raises CorruptedLogError on invalid JSON in the middle of the log.
    """
    if not path.exists():
        return
    raw_bytes = path.read_bytes()
    lines = raw_bytes.splitlines()
    last_idx = len(lines) - 1
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            yield Event.from_dict(json.loads(line))
        except (json.JSONDecodeError, KeyError) as exc:
            if i == last_idx:
                return  # truncated last line — tolerate
            raise CorruptedLogError(
                f"Invalid data at log line {i + 1}: {exc}"
            ) from exc


def verify_chain(
    mode: str = "strict",
    log_path: Path | None = None,
) -> VerifyResult:
    """
    Verifies hash chain integrity of the log.

    Modes:
        strict: stops at first error.
        audit:  collects all errors without modifying the log.

    Args:
        mode: "strict" or "audit".
        log_path: Override default log path (for testing).

    Returns:
        VerifyResult with ok, message, details.
    """
    effective_path = log_path or LOG_PATH

    if not effective_path.exists() or effective_path.stat().st_size == 0:
        return VerifyResult(ok=True, message="Log is empty", mode=mode,
                            events_verified=0)

    errors: list[dict[str, Any]] = []
    prev_hash = "GENESIS"
    count = 0

    try:
        for event in _iter_events_from_path(effective_path):
            count += 1
            error: dict[str, Any] | None = None

            if event.prev_hash != prev_hash:
                error = {
                    "seq": event.seq,
                    "type": "chain_broken",
                    "expected_prev_hash": prev_hash[:16] + "…",
                    "actual_prev_hash": event.prev_hash[:16] + "…",
                }
            else:
                computed = event.compute_hash()
                if computed != event.hash:
                    error = {
                        "seq": event.seq,
                        "type": "hash_mismatch",
                        "expected": computed[:16] + "…",
                        "actual": event.hash[:16] + "…",
                    }

            if error:
                errors.append(error)
                if mode == "strict":
                    return VerifyResult(
                        ok=False,
                        message=f"Hash chain error at seq={event.seq}: {error['type']}",
                        mode=mode,
                        events_verified=count - 1,
                        first_error_seq=event.seq,
                        error_details=errors,
                    )

            prev_hash = event.hash

    except CorruptedLogError as exc:
        error = {"seq": None, "type": "parse_error", "message": str(exc)}
        errors.append(error)
        if mode == "strict":
            return VerifyResult(
                ok=False,
                message=f"Log parse error: {exc}",
                mode=mode,
                events_verified=count,
                first_error_seq=None,
                error_details=errors,
            )

    if errors:
        return VerifyResult(
            ok=False,
            message=f"{len(errors)} error(s) found in log",
            mode=mode,
            events_verified=count,
            first_error_seq=errors[0].get("seq"),
            error_details=errors,
        )

    return VerifyResult(
        ok=True,
        message=f"Chain verified: {count} event(s)",
        mode=mode,
        events_verified=count,
    )


def _verify_cache_path() -> Path:
    return STATE_DIR / "verify_cache.json"


def _write_verify_cache(seq: int, boundary_offset: int, event_hash: str,
                        events_verified: int) -> None:
    """Best-effort atomic write of the verified-prefix cache."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "engine_rev": _engine_rev(),
            "seq": seq,
            "boundary_offset": boundary_offset,
            "event_hash": event_hash,
            "events_verified": events_verified,
            "written_at": now_iso(),
        }
        tmp = _verify_cache_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, _verify_cache_path())
    except Exception:  # noqa: BLE001 — cache write is opportunistic
        pass


def _full_verify_and_cache() -> VerifyResult:
    result = verify_chain(mode="strict")
    if result.ok:
        b = _last_event_boundary()
        if b is not None:
            _write_verify_cache(b[1].seq, b[0], b[1].hash, result.events_verified)
    return result


def verify_chain_cached() -> VerifyResult:
    """Strict-mode verify accelerated by the verified-prefix cache.

    The append path already re-validates the tail hash on every write
    (_append_event_locked), so re-hashing the whole chain from GENESIS on
    every cycle re-proves what was already proven. This variant re-reads the
    cached boundary line in place (seq + hash must match) and hash-verifies
    only the tail appended since. EVERY anomaly — missing/corrupt cache,
    engine change, boundary mismatch, or a tail error — defers to the
    canonical full verify_chain('strict'), so failure reports are always
    authoritative (first_error_seq from a GENESIS scan). Semantics are
    therefore identical to strict mode; only the happy path is cheaper.
    Audit mode is untouched — periodic full audits still re-hash everything.
    ORCH_SNAPSHOT=0 disables the cache here too.
    """
    if not _snapshot_enabled():
        return verify_chain(mode="strict")
    try:
        cache = json.loads(_verify_cache_path().read_text(encoding="utf-8"))
        if not isinstance(cache, dict) or cache.get("schema") != 1 \
                or cache.get("engine_rev") != _engine_rev():
            return _full_verify_and_cache()
        boundary = int(cache["boundary_offset"])
        if not LOG_PATH.exists() or LOG_PATH.stat().st_size <= boundary:
            return _full_verify_and_cache()
        with open(LOG_PATH, "rb") as f:
            f.seek(boundary)
            line = f.readline()
            tail_start = f.tell()
        event = Event.from_dict(json.loads(line.decode("utf-8")))
        if event.seq != int(cache["seq"]) or event.hash != cache["event_hash"]:
            return _full_verify_and_cache()
    except Exception:  # noqa: BLE001 — unusable cache → canonical full verify
        return _full_verify_and_cache()

    prev_hash = event.hash
    count = int(cache.get("events_verified", 0))
    last_boundary: tuple[int, str, int] | None = None
    pairs = _read_offset_lines(LOG_PATH, tail_start)
    last_idx = len(pairs) - 1
    for i, (off, raw) in enumerate(pairs):
        try:
            ev = Event.from_dict(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
            if i == last_idx:
                break  # truncated last line — tolerated, same as verify_chain
            return _full_verify_and_cache()
        if ev.prev_hash != prev_hash or ev.compute_hash() != ev.hash:
            return _full_verify_and_cache()
        prev_hash = ev.hash
        count += 1
        last_boundary = (off, ev.hash, ev.seq)

    if last_boundary is not None:
        _write_verify_cache(last_boundary[2], last_boundary[0],
                            last_boundary[1], count)
    return VerifyResult(
        ok=True,
        message=f"Chain verified: {count} event(s) (cached prefix)",
        mode="strict",
        events_verified=count,
    )


# ---------------------------------------------------------------------------
# Log recovery
# ---------------------------------------------------------------------------

def verify_and_recover(
    from_seq: int,
    operator: str,
    confirm: bool,
) -> Event:
    """
    Truncates the log at from_seq, archives the corrupt tail, and emits log_recovered.

    The log is truncated so that events with seq >= from_seq are removed.
    The removed events are written to .orch/log.jsonl.corrupt.{timestamp}.
    A log_recovered event is then appended to the clean log.

    Args:
        from_seq: First seq to remove (events 1..from_seq-1 are kept).
        operator: Identity of the operator authorising this recovery.
        confirm:  Must be True. Raises ValueError if False (safety gate).

    Returns:
        The log_recovered Event that was appended.

    Raises:
        ValueError: confirm is False.
        ValueError: from_seq < 1.
        FileNotFoundError: log does not exist.
        OSError: filesystem errors.
    """
    if not confirm:
        raise ValueError(
            "verify_and_recover requires confirm=True — this operation is never automatic"
        )
    if from_seq < 1:
        raise ValueError(f"from_seq must be >= 1, got {from_seq!r}")

    if not LOG_PATH.exists():
        raise FileNotFoundError(f"Log not found: {LOG_PATH}")

    ensure_dirs()

    with LogLock():
        # Read all raw lines from the log
        raw_lines = LOG_PATH.read_bytes().splitlines(keepends=True)

        # Separate good lines (seq < from_seq) from corrupt lines (seq >= from_seq)
        good_lines: list[bytes] = []
        corrupt_lines: list[bytes] = []
        last_good_hash: str = "GENESIS"
        events_removed = 0

        for line in raw_lines:
            line = line.rstrip(b"\n") + b"\n"
            try:
                obj = json.loads(line)
                seq = obj.get("seq", 0)
            except (json.JSONDecodeError, AttributeError):
                # Unparseable lines go to corrupt
                corrupt_lines.append(line)
                events_removed += 1
                continue

            if seq < from_seq:
                good_lines.append(line)
                last_good_hash = obj.get("hash", last_good_hash)
            else:
                corrupt_lines.append(line)
                events_removed += 1

        # Determine last good seq for the event data
        last_good_seq = from_seq - 1

        # Write the corrupt portion to a timestamped file
        ts_tag = now_iso().replace(":", "-").replace(".", "-").rstrip("Z")[:23]
        corrupt_filename = f"log.jsonl.corrupt.{ts_tag}"
        corrupt_rel_path = f".orch/{corrupt_filename}"
        corrupt_path = ORCH_DIR / corrupt_filename

        if corrupt_lines:
            corrupt_path.write_bytes(b"".join(corrupt_lines))

        # Rewrite the clean log
        LOG_PATH.write_bytes(b"".join(good_lines))

        # Build and append the log_recovered event inline (bypasses append_event
        # to avoid acquiring the lock a second time)
        last_line = good_lines[-1] if good_lines else None
        if last_line:
            try:
                last_obj = json.loads(last_line)
                prev_hash = last_obj.get("hash", "GENESIS")
                next_seq = last_obj.get("seq", 0) + 1
            except json.JSONDecodeError:
                prev_hash = "GENESIS"
                next_seq = 1
        else:
            prev_hash = "GENESIS"
            next_seq = 1

        event_id = new_event_id()
        recovery_data: dict[str, Any] = {
            "seq_truncated_from": from_seq,
            "seq_truncated_to": last_good_seq,
            "events_removed": events_removed,
            "operator": operator,
            "corrupt_file_path": corrupt_rel_path,
            "hash_before_truncation": last_good_hash,
        }

        recovery_event = Event(
            seq=next_seq,
            event_id=event_id,
            ts=now_iso(),
            agent="operator",
            event_type=EventType.LOG_RECOVERED.value,
            task_id=None,
            attempt=1,
            data=recovery_data,
            prev_hash=prev_hash,
            hash="",
        )
        recovery_event.hash = recovery_event.compute_hash()
        # hash_after_truncation is the event's own hash (the new chain head after recovery).
        # Store it in data so auditors can reference it, but recompute hash to stay consistent.
        recovery_event.data["hash_after_truncation"] = recovery_event.hash
        recovery_event.hash = recovery_event.compute_hash()

        line_bytes = (
            json.dumps(recovery_event.to_dict(), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")

        with open(LOG_PATH, "ab") as f:
            f.write(line_bytes)
            f.flush()
            os.fsync(f.fileno())

    return recovery_event


# ---------------------------------------------------------------------------
# Blob externalization
# ---------------------------------------------------------------------------

def is_blob_ref(data: dict[str, Any]) -> bool:
    """Returns True if data is a blob reference (has _blob_ref, _size, _blob_hash)."""
    return (
        isinstance(data, dict)
        and "_blob_ref" in data
        and "_size" in data
        and "_blob_hash" in data
    )


def externalize_blob(data: dict[str, Any], event_id: str) -> tuple[str, str]:
    """
    Persists large payload to .orch/blobs/{event_id}.json.

    Returns:
        Tuple of (blob_ref, blob_hash).
        blob_ref is a path relative to ORCH_DIR (e.g. "blobs/evt_XYZ.json").
    """
    blob_path = BLOBS_DIR / f"{event_id}.json"
    raw = canonical_json(data).encode("utf-8")
    blob_hash = hashlib.sha256(raw).hexdigest()
    blob_path.write_bytes(raw)
    # Store path relative to ORCH_DIR so the ref survives project moves.
    rel_ref = str(blob_path.relative_to(ORCH_DIR))
    return rel_ref, blob_hash


def load_blob_data(event: Event) -> dict[str, Any]:
    """
    Returns data of event, loading from blob if externalized.

    Resolves _blob_ref relative to ORCH_DIR.

    Raises:
        BlobIntegrityError: hash mismatch (tampering detected).
        BlobNotFoundError: blob file missing.
    """
    if not is_blob_ref(event.data):
        return event.data

    blob_path = ORCH_DIR / event.data["_blob_ref"]
    expected_hash = event.data["_blob_hash"]

    if not blob_path.exists():
        raise BlobNotFoundError(f"Blob not found: {blob_path}")

    raw = blob_path.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()

    if actual_hash != expected_hash:
        raise BlobIntegrityError(
            f"Blob integrity error: {blob_path} — expected {expected_hash}, got {actual_hash}"
        )

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Append-time preconditions (prod-hardening task 00)
# ---------------------------------------------------------------------------
# Registered functions run inside append_event, under LogLock, BEFORE the event
# is written. Signature: (data: dict, events: list[Event]) -> str | None.
# A non-None return is the rejection reason and raises PreconditionViolation.
# The default registry is empty => behavior-neutral (no-op). Later tasks
# register guards for phase_transitioned (task 01), task_claimed (task 12),
# handoff_receipt (task 08), etc. — moving those guarantees from prompt to code.

_APPEND_PRECONDITIONS: dict[str, list[Callable[[dict, list[Event]], str | None]]] = {}


def register_precondition(
    event_type: str, fn: Callable[[dict, list[Event]], str | None]
) -> None:
    """Registers an append-time precondition for an event type (multiple allowed)."""
    _APPEND_PRECONDITIONS.setdefault(event_type, []).append(fn)


def clear_preconditions(event_type: str | None = None) -> None:
    """Removes preconditions for one event type, or all of them if event_type is None."""
    if event_type is None:
        _APPEND_PRECONDITIONS.clear()
    else:
        _APPEND_PRECONDITIONS.pop(event_type, None)


def last_event_where(
    events: list[Event], pred: Callable[[Event], bool]
) -> Event | None:
    """Returns the last event satisfying pred (scanning newest-first), or None."""
    for e in reversed(events):
        if pred(e):
            return e
    return None


def any_event_where(events: list[Event], pred: Callable[[Event], bool]) -> bool:
    """Returns True if any event satisfies pred."""
    return any(pred(e) for e in events)


# Loop-back (rejection) transitions: not approved exits, so they are exempt from
# the gate/approval preconditions. Returning to an earlier phase never advances
# the workflow toward "done".
_RETURN_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("review", "dev"), ("test", "dev"), ("test", "review"),
})


def _evt_data(e: Event) -> dict:
    """Event data with any externalized blob resolved (transition/approval events
    are small and never externalized, but resolve defensively)."""
    return load_blob_data(e) if is_blob_ref(e.data) else e.data


def _precond_phase_transitioned(data: dict, events: list[Event]) -> str | None:
    """Hard-block a forward phase transition unless its gate is satisfied in the log.

    Enforces (in Python, not prompt):
      - a phase_exit_approved for from_phase must precede the transition (C1/A4-F1);
      - evidence_seq must reference a prior event (P8/A3-F8);
      - leaving review forward (review->test) requires a human_response action=approve
        OR an E18 auto-approval escalation (A1-F1).
    Return-to-dev / loop-back transitions are exempt (rejection paths, not exits).
    """
    from_phase = data.get("from_phase")
    to_phase = data.get("to_phase")
    if not from_phase or not to_phase:
        return "missing from_phase/to_phase"
    if (from_phase, to_phase) in _RETURN_TRANSITIONS:
        return None
    approved = last_event_where(
        events,
        lambda e: e.event_type == EventType.PHASE_EXIT_APPROVED.value
        and _evt_data(e).get("phase") == from_phase,
    )
    if approved is None:
        return f"no phase_exit_approved for {from_phase!r} precedes the transition (P11/P7)"
    ev_seq = data.get("evidence_seq")
    if not isinstance(ev_seq, int) or not any_event_where(events, lambda e: e.seq == ev_seq):
        return f"evidence_seq {ev_seq!r} does not reference a prior event"
    if from_phase == "review":
        human_ok = last_event_where(
            events,
            lambda e: e.event_type == EventType.HUMAN_RESPONSE.value
            and _evt_data(e).get("action") == "approve",
        )
        e18 = last_event_where(
            events,
            lambda e: e.event_type == EventType.ESCALATION.value
            and str(_evt_data(e).get("code", "")).startswith("E18"),
        )
        if human_ok is None and e18 is None:
            return (
                "review->test requires a human_response action=approve "
                "(or an E18 auto-approval) in the log (A1-F1)"
            )
    return None


def install_transition_preconditions() -> None:
    """Idempotent: register the phase_transitioned hard-block guard exactly once."""
    clear_preconditions(EventType.PHASE_TRANSITIONED.value)
    register_precondition(EventType.PHASE_TRANSITIONED.value, _precond_phase_transitioned)


def append_event(
    agent: str,
    event_type: str,
    task_id: str | None = None,
    attempt: int = 1,
    data: dict[str, Any] | None = None,
) -> Event:
    """
    Atomically appends an event to the log with hash chain integrity.

    Thread-safe and process-safe via POSIX flock.
    Validates event type and required data fields before writing.
    Externalizes payloads > MAX_INLINE_PAYLOAD to .orch/blobs/.

    Raises:
        UnknownEventType: event_type not in EventType enum.
        EventValidationError: data missing required fields.
        LockTimeoutError: could not acquire lock within LOCK_TIMEOUT_S.
        OSError: filesystem errors.
    """
    if data is None:
        data = {}

    if event_type not in EventType.values():
        raise UnknownEventType(f"Unknown event type: {event_type!r}")

    # For events that require an auditable operator identity, default to the
    # --agent value so callers don't have to repeat it in --data.
    _OPERATOR_EVENTS = {EventType.HUMAN_RESPONSE.value, EventType.LOG_RECOVERED.value}
    if event_type in _OPERATOR_EVENTS and "operator" not in data:
        data = {**data, "operator": agent}

    _validate_event_data(event_type, data)

    ensure_dirs()

    with LogLock():
        # Append-time preconditions (prod-hardening task 00): run BEFORE the
        # write, under the lock, so the check is consistent with the append.
        # Empty registry (default) => no-op. A non-None return rejects the append.
        _preconds = _APPEND_PRECONDITIONS.get(event_type)
        if _preconds:
            _existing = list(read_events())
            for _fn in _preconds:
                _reason = _fn(data, _existing)
                if _reason:
                    raise PreconditionViolation(f"{event_type} rejected: {_reason}")
        return _append_event_locked(agent, event_type, task_id, attempt, data)


def _append_event_locked(
    agent: str,
    event_type: str,
    task_id: str | None,
    attempt: int,
    data: dict[str, Any],
) -> Event:
    """Write path of append_event. Caller MUST hold LogLock and have validated
    event_type/data already. Extracted so claim_task can run a state check and
    the append under the SAME lock acquisition (atomic check-and-append)."""
    last = last_event()
    # SIEGARD-03: refuse to chain onto a corrupted tail. If the last event no
    # longer matches its own hash, the log is already corrupt — fail HERE (at
    # append) instead of propagating an invalid prev_hash into every following
    # event (the cascade that forces recovery to truncate N valid events).
    # Cost: one hash recompute per append (cheap).
    if last is not None and last.compute_hash() != last.hash:
        raise CorruptedLogError(
            f"refusing to append onto corrupted tail: seq={last.seq} hash mismatch"
        )
    seq = (last.seq + 1) if last else 1
    prev_hash = last.hash if last else "GENESIS"

    event_id = new_event_id()

    serialized_size = len(canonical_json(data).encode("utf-8"))
    if serialized_size > MAX_INLINE_PAYLOAD:
        blob_ref, blob_hash = externalize_blob(data, event_id)
        stored_data: dict[str, Any] = {
            "_blob_ref": blob_ref,
            "_size": serialized_size,
            "_blob_hash": blob_hash,
        }
    else:
        stored_data = data

    event = Event(
        seq=seq,
        event_id=event_id,
        ts=now_iso(),
        agent=agent,
        event_type=event_type,
        task_id=task_id,
        attempt=attempt,
        data=stored_data,
        prev_hash=prev_hash,
        hash="",
    )
    event.hash = event.compute_hash()

    line_bytes = (
        json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")

    # SIEGARD-03: append in a single os.write on an O_APPEND fd. Under LogLock
    # there are no concurrent cooperating writers; the win is shrinking the
    # "partial line" window if the process is killed mid-append (the dominant
    # corruption vector, correlated with worker kills). fsync preserves
    # durability. Blobs (MAX_INLINE_PAYLOAD) keep the line small, so it
    # typically fits in a single atomic write (<= PIPE_BUF).
    fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)

    return event


def claim_task(
    agent: str,
    task_id: str,
    attempt: int = 1,
    data: dict[str, Any] | None = None,
) -> tuple[Event | None, str | None]:
    """Atomic check-and-claim — serializes dispatch against the append lock.

    The orchestrators' dispatch cycle is read-then-append: derive state, pick a
    batch, append task_claimed per task. Two concurrent orchestrator instances
    can both read the same READY task before either claim lands (double-dispatch
    race). This function closes that window: it re-derives the task's status
    from the log INSIDE LogLock and appends task_claimed only when the task is
    still claimable (status == ready). Racing claimants serialize on the lock;
    the loser gets a structured refusal instead of writing a duplicate claim.

    Returns:
        (event, None)  — claim appended.
        (None, reason) — not claimable; reason is "task_not_found" or
                         "not_ready:<current status>". Caller MUST drop the
                         task from its dispatch batch and NOT spawn a worker.

    Raises:
        EventValidationError: data missing required task_claimed fields.
        IllegalTransition / CorruptedLogError: log cannot be replayed.
        LockTimeoutError, OSError: as append_event.
    """
    if data is None:
        data = {}
    _validate_event_data(EventType.TASK_CLAIMED.value, data)
    ensure_dirs()
    with LogLock():
        state = reduce_all()
        task = state.tasks.get(task_id)
        if task is None:
            return None, "task_not_found"
        if task.status != TaskStatus.READY:
            return None, f"not_ready:{TaskStatus(task.status).value}"
        event = _append_event_locked(
            agent, EventType.TASK_CLAIMED.value, task_id, attempt, data
        )
        return event, None


# ---------------------------------------------------------------------------
# Reducer — state dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TaskState:
    """Derived state for a single task."""
    task_id: str
    phase: str
    status: "TaskStatus"
    deps: list[str]
    tier: str
    task_type: str
    spec: str
    attempts: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
    stack: str | None = None
    # 5-a: explicit workflow binding from task_created data.workflow_id (None on
    # legacy events). Lets orchestrators and exit gates scope task queries per
    # workflow by FIELD instead of parsing/prefix-matching the task ID.
    workflow_id: str | None = None
    artifacts: list[str] = field(default_factory=list)
    last_error: str | None = None
    last_failure_reason: str | None = None
    last_failure_retryable: bool | None = None
    next_retry_at: str | None = None
    claimed_at: str | None = None
    last_event_at: str | None = None
    failed_at: str | None = None
    evidence: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "status": self.status,
            "deps": self.deps,
            "tier": self.tier,
            "task_type": self.task_type,
            "spec": self.spec,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "worker_id": self.worker_id,
            "stack": self.stack,
            "workflow_id": self.workflow_id,
            "artifacts": self.artifacts,
            "last_error": self.last_error,
            "last_failure_reason": self.last_failure_reason,
            "last_failure_retryable": self.last_failure_retryable,
            "next_retry_at": self.next_retry_at,
            "claimed_at": self.claimed_at,
            "last_event_at": self.last_event_at,
            "failed_at": self.failed_at,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskState":
        raw_status = d["status"]
        try:
            status = TaskStatus(raw_status)
        except ValueError as exc:
            raise ValueError(
                f"unknown task status {raw_status!r} for task {d.get('task_id')!r}"
            ) from exc
        return cls(
            task_id=d["task_id"],
            phase=d["phase"],
            status=status,
            deps=d.get("deps", []),
            tier=d["tier"],
            task_type=d["task_type"],
            spec=d.get("spec", ""),
            attempts=d.get("attempts", 0),
            max_attempts=d.get("max_attempts", 3),
            worker_id=d.get("worker_id"),
            stack=d.get("stack"),
            workflow_id=d.get("workflow_id"),
            artifacts=d.get("artifacts", []),
            last_error=d.get("last_error"),
            last_failure_reason=d.get("last_failure_reason"),
            last_failure_retryable=d.get("last_failure_retryable"),
            next_retry_at=d.get("next_retry_at"),
            claimed_at=d.get("claimed_at"),
            last_event_at=d.get("last_event_at"),
            failed_at=d.get("failed_at"),
            evidence=d.get("evidence", []),
        )


@dataclass
class PhaseState:
    """Derived state for a workflow phase."""
    name: str
    order: int
    required: bool
    status: str
    entered_at: str | None = None
    criteria_met: list[str] = field(default_factory=list)
    approved_at: str | None = None
    completed_at: str | None = None
    paused_at: str | None = None
    pause_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "order": self.order,
            "required": self.required,
            "status": self.status,
            "entered_at": self.entered_at,
            "criteria_met": self.criteria_met,
            "approved_at": self.approved_at,
            "completed_at": self.completed_at,
            "paused_at": self.paused_at,
            "pause_reason": self.pause_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhaseState":
        return cls(
            name=d["name"],
            order=d["order"],
            required=d["required"],
            status=d["status"],
            entered_at=d.get("entered_at"),
            criteria_met=d.get("criteria_met", []),
            approved_at=d.get("approved_at"),
            completed_at=d.get("completed_at"),
            paused_at=d.get("paused_at"),
            pause_reason=d.get("pause_reason"),
        )


@dataclass
class OrchState:
    """Aggregate state derived from event log."""
    workflow_id: str | None = None
    run_status: str = "active"
    current_phase: str | None = None
    tasks: dict[str, "TaskState"] = field(default_factory=dict)
    phases: dict[str, "PhaseState"] = field(default_factory=dict)
    escalation: dict[str, Any] | None = None
    circuit_breaker: dict[str, Any] | None = None
    last_seq: int = 0
    last_snapshot_seq: int = 0
    # ISO timestamps of every task_failed event — used by evaluate_circuit_state
    failure_timestamps: list[str] = field(default_factory=list)
    # Audited no-op events: duplicates the reducer absorbed instead of raising
    # IllegalTransition (e.g. a duplicate task_claimed from a concurrent
    # orchestrator). Fail loud, not fail dead — visible in reduce output, never
    # silent, never fatal. Each entry: {seq, event_type, task_id, reason}.
    anomalies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "run_status": self.run_status,
            "current_phase": self.current_phase,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "phases": {k: v.to_dict() for k, v in self.phases.items()},
            "escalation": self.escalation,
            "circuit_breaker": self.circuit_breaker,
            "last_seq": self.last_seq,
            "last_snapshot_seq": self.last_snapshot_seq,
            # C3: expose failure_timestamps so orchestrator can evaluate circuit breaker
            "failure_timestamps": self.failure_timestamps,
            "anomalies": self.anomalies,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OrchState":
        obj = cls(
            workflow_id=d.get("workflow_id"),
            run_status=d.get("run_status", "active"),
            current_phase=d.get("current_phase"),
            escalation=d.get("escalation"),
            circuit_breaker=d.get("circuit_breaker"),
            last_seq=d.get("last_seq", 0),
            last_snapshot_seq=d.get("last_snapshot_seq", 0),
        )
        obj.tasks = {k: TaskState.from_dict(v) for k, v in d.get("tasks", {}).items()}
        obj.phases = {k: PhaseState.from_dict(v) for k, v in d.get("phases", {}).items()}
        obj.failure_timestamps = list(d.get("failure_timestamps", []))
        obj.anomalies = list(d.get("anomalies", []))
        return obj

    def tasks_by_status(self, status: str) -> list["TaskState"]:
        return [t for t in self.tasks.values() if t.status == status]

    def tasks_by_phase(self, phase: str) -> list["TaskState"]:
        return [t for t in self.tasks.values() if t.phase == phase]

    def ready_tasks(self) -> list["TaskState"]:
        return [t for t in self.tasks.values() if t.status == TaskStatus.READY]


# ---------------------------------------------------------------------------
# Reducer — internal helpers
# ---------------------------------------------------------------------------

def _deps_complete(task: TaskState, state: OrchState) -> bool:
    """Returns True if all deps are in a terminal-acceptable state for promotion.

    Per STEP_DEPENDENCIES principle, both COMPLETED and SKIPPED are valid terminal
    states for dependency evaluation. Returns False for missing, DLQ, or non-terminal deps.
    """
    return all(
        state.tasks.get(dep_id) is not None
        and state.tasks[dep_id].status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
        for dep_id in task.deps
    )


def get_orphaned_dep_ids(task: TaskState, state: OrchState) -> list[str]:
    """
    Returns dep IDs that are referenced by task but absent from state.

    Orphaned deps occur when crash recovery truncates task_created events for
    dependency tasks, leaving the child task permanently blocked. The caller
    (orchestrator dispatch loop) should cascade DLQ to the child task when this
    returns a non-empty list.
    """
    return [dep_id for dep_id in task.deps if dep_id not in state.tasks]


def _phase_is_active(phase_name: str, state: OrchState) -> bool:
    return state.current_phase == phase_name


def _try_promote_to_ready(task: TaskState, state: OrchState) -> None:
    """Promotes task from pending to ready if conditions are met (mutates task)."""
    if task.status != TaskStatus.PENDING:
        return
    if _phase_is_active(task.phase, state) and _deps_complete(task, state):
        task.status = TaskStatus.READY


def _promote_pending_tasks(state: OrchState) -> None:
    """Re-evaluates all pending tasks after a state change."""
    for task in state.tasks.values():
        if task.status == TaskStatus.PENDING:
            _try_promote_to_ready(task, state)


# ---------------------------------------------------------------------------
# Reducer — event handlers
# ---------------------------------------------------------------------------

def _handle_escalation(state: OrchState, event: Event) -> None:
    state.run_status = "escalated"
    state.escalation = {**event.data, "seq": event.seq}


def _handle_phase_declared(state: OrchState, event: Event) -> None:
    state.workflow_id = event.data.get("workflow_id")
    for phase_def in event.data.get("phases", []):
        name = phase_def["name"]
        state.phases[name] = PhaseState(
            name=name,
            order=phase_def.get("order", 0),
            required=phase_def.get("required", True),
            status=PhaseStatus.PENDING,
        )


def _handle_phase_entered(state: OrchState, event: Event) -> None:
    phase_name = event.data["phase"]
    if phase_name not in state.phases:
        raise IllegalTransition(
            f"phase_entered: phase {phase_name!r} not declared"
        )
    for p in state.phases.values():
        if p.status == PhaseStatus.ACTIVE:
            raise IllegalTransition(
                f"phase_entered: phase {p.name!r} is already active"
            )
    state.phases[phase_name].status = PhaseStatus.ACTIVE
    state.phases[phase_name].entered_at = event.ts
    state.current_phase = phase_name
    _promote_pending_tasks(state)


def _handle_phase_exit_criterion_met(state: OrchState, event: Event) -> None:
    phase_name = event.data["phase"]
    criterion = event.data.get("criterion", "")
    if phase_name in state.phases:
        state.phases[phase_name].criteria_met.append(criterion)


def _handle_phase_exit_approved(state: OrchState, event: Event) -> None:
    phase_name = event.data["phase"]
    if phase_name in state.phases:
        state.phases[phase_name].status = PhaseStatus.EXIT_APPROVED
        state.phases[phase_name].approved_at = event.ts
        criteria = event.data.get("criteria_met", [])
        state.phases[phase_name].criteria_met.extend(criteria)


def _handle_phase_transitioned(state: OrchState, event: Event) -> None:
    from_phase = event.data.get("from_phase")
    if from_phase and from_phase in state.phases:
        state.phases[from_phase].status = PhaseStatus.COMPLETED
        state.phases[from_phase].completed_at = event.ts
    if state.current_phase == from_phase:
        state.current_phase = None


def _handle_phase_paused(state: OrchState, event: Event) -> None:
    phase_name = event.data["phase"]
    if phase_name in state.phases:
        state.phases[phase_name].status = PhaseStatus.PAUSED
        state.phases[phase_name].paused_at = event.ts
        state.phases[phase_name].pause_reason = event.data.get("reason")


def _handle_phase_resumed(state: OrchState, event: Event) -> None:
    phase_name = event.data["phase"]
    if phase_name in state.phases:
        state.phases[phase_name].status = PhaseStatus.ACTIVE
        state.phases[phase_name].paused_at = None
        state.phases[phase_name].pause_reason = None


def _handle_task_created(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None:
        return
    data = event.data
    task = TaskState(
        task_id=task_id,
        phase=data.get("phase", ""),
        status=TaskStatus.PENDING,
        deps=list(data.get("deps", [])),
        tier=data.get("tier", Tier.STANDARD.value),
        task_type=data.get("type", ""),
        spec=data.get("spec", ""),
        stack=data.get("stack"),
        workflow_id=data.get("workflow_id"),
        max_attempts=Tier(data.get("tier", Tier.STANDARD.value)).default_max_attempts,
        last_event_at=event.ts,
    )
    task.evidence.append(event.seq)
    state.tasks[task_id] = task
    _try_promote_to_ready(task, state)


def _handle_task_claimed(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    # C2: Idempotency — a duplicate claim of an already-RUNNING task by the same
    # worker_id is residue from a concurrent orchestrator dispatching the same
    # batch (double-dispatch race). The log is append-only, so raising here would
    # make every future replay fail — the duplicate must be an audited no-op, not
    # a fatal transition. Recorded in state.anomalies (fail loud, not fail dead).
    if task.status == TaskStatus.RUNNING and task.worker_id == event.data.get("worker_id"):
        state.anomalies.append({
            "seq": event.seq,
            "event_type": EventType.TASK_CLAIMED.value,
            "task_id": task_id,
            "reason": "duplicate_claim_same_worker",
        })
        return
    if task.status != TaskStatus.READY:
        raise IllegalTransition(
            f"task_claimed: task {task_id!r} is {task.status!r}, expected ready"
        )
    task.status = TaskStatus.RUNNING
    task.worker_id = event.data.get("worker_id")
    task.claimed_at = event.ts
    task.last_event_at = event.ts
    task.evidence.append(event.seq)


def _handle_task_progress(state: OrchState, event: Event) -> None:
    """Heartbeat: a live worker's progress checkpoint resets the staleness timer.

    F1 (SIEGARD): the stale reaper (stale_tasks) and the SubagentStop liveness gate
    (worker_liveness_expired) both measure silence as (now - task.last_event_at).
    stale_tasks' own docstring promises task_progress updates last_event_at so
    heartbeats reset the timer — but task_progress had NO reducer handler, so
    last_event_at only advanced on state transitions (task_claimed, ...). A worker
    emitting context_loaded -> analysis_complete -> draft_written without any
    transition never reset the timer and was reaped while alive. This handler makes
    the implementation match the contract.

    Only a progress for the CURRENT attempt of a RUNNING task counts (mirrors the
    straggler guards in _handle_task_completed/_handle_task_failed): progress on a
    non-running task (e.g. one already reaped to FAILED) must not revive it, and an
    older attempt's straggler progress must not reset a newer attempt's timer.
    last_event_at is advanced but evidence is NOT appended — heartbeats are frequent
    and would grow the evidence list unbounded.
    """
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    if task.status != TaskStatus.RUNNING:
        return
    if event.attempt < (task.attempts or 1):
        return
    task.last_event_at = event.ts


def _handle_task_completed(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    # C2: Idempotency — if already terminal, no-op. Prevents TOCTOU duplicate from
    # on_subagent_stop hook and orchestrator Step 6.4 racing on the same task.
    if task.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.DLQ):
        return
    # Superseded-attempt straggler: a task_retried already advanced this task to a
    # newer attempt (task.attempts). A task_completed carrying an OLDER event.attempt
    # is residue from the previous attempt's worker → idempotent no-op, not fatal.
    # `task.attempts` defaults to 0 and is only set on failure/retry, so the happy
    # path (attempts=0, event.attempt=1) evaluates `1 < 1` → False and proceeds.
    if event.attempt < (task.attempts or 1):
        return
    # F2 (SIEGARD): false-positive reconciliation. A SYNTHESIZED terminal — emitted
    # by the stale reaper (stale_timeout) or the SubagentStop hook
    # (worker_exited_without_terminal), never by the worker — marked a still-live
    # worker as FAILED. Its late task_completed (same attempt, no retry advanced the
    # attempt counter) proves the worker was alive and finished; the FAILED was the
    # error, not this event. Accept FAILED->COMPLETED and record the anomaly (fail
    # loud, not fail dead) so a single false positive no longer makes the whole log
    # irreducible. This is deliberately NARROW: a completed over a WORKER-reported
    # FAILED (validation_failed, internal_error, ...) or over a never-claimed task
    # still raises below — the validator rejecting genuine corruption stays a feature.
    reconciled_false_positive = (
        task.status == TaskStatus.FAILED
        and task.last_failure_reason in _SYNTHESIZED_FAILURE_REASONS
    )
    if reconciled_false_positive:
        state.anomalies.append({
            "seq": event.seq,
            "event_type": EventType.TASK_COMPLETED.value,
            "task_id": task_id,
            "reason": "reconciled_false_positive_completion",
            "prior_failure": task.last_failure_reason,
        })
    elif task.status != TaskStatus.RUNNING:
        raise IllegalTransition(
            f"task_completed: task {task_id!r} is {task.status!r}, expected running"
        )
    task.status = TaskStatus.COMPLETED
    task.last_event_at = event.ts
    artifacts = event.data.get("artifacts", [])
    if artifacts:
        task.artifacts.extend(artifacts)
    task.evidence.append(event.seq)
    _promote_pending_tasks(state)


def _handle_task_skipped(state: OrchState, event: Event) -> None:
    """Task is declared skipped by the orchestrator (DECLARATIVE_TRUNCATION).

    Skipped is terminal for dependency evaluation; downstream tasks may proceed.
    Allowed source statuses: PENDING, READY (task was created but not yet dispatched).
    """
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    if task.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.DLQ):
        return
    if task.status not in (TaskStatus.PENDING, TaskStatus.READY):
        raise IllegalTransition(
            f"task_skipped: task {task_id!r} is {task.status!r}, expected pending or ready"
        )
    task.status = TaskStatus.SKIPPED
    task.last_event_at = event.ts
    task.evidence.append(event.seq)
    _promote_pending_tasks(state)


def _handle_task_failed(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    # C2: Idempotency — already terminal or failed → no-op. Prevents TOCTOU duplicate
    # from on_subagent_stop hook and orchestrator Step 6.4 racing on the same task.
    if task.status in (TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.DLQ):
        return
    # Superseded-attempt straggler: task_retried already advanced this task to a newer
    # attempt. A task_failed carrying an OLDER event.attempt is residue from the prior
    # attempt's worker → idempotent no-op. Placed before the RUNNING check so a late
    # failed for attempt N cannot corrupt a task currently RUNNING on attempt N+1.
    if event.attempt < (task.attempts or 1):
        return
    if task.status != TaskStatus.RUNNING:
        raise IllegalTransition(
            f"task_failed: task {task_id!r} is {task.status!r}, expected running"
        )
    task.status = TaskStatus.FAILED
    task.attempts = event.attempt
    task.last_failure_reason = event.data.get("reason")
    task.last_failure_retryable = event.data.get("retryable", True)
    task.last_error = event.data.get("error")
    task.failed_at = event.ts
    task.last_event_at = event.ts
    task.evidence.append(event.seq)
    state.failure_timestamps.append(event.ts)


def _handle_task_scheduled_retry(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    if task.status != TaskStatus.FAILED:
        raise IllegalTransition(
            f"task_scheduled_retry: task {task_id!r} is {task.status!r}, expected failed"
        )
    task.status = TaskStatus.SCHEDULED
    task.next_retry_at = event.data.get("next_retry_at")
    task.last_event_at = event.ts
    task.evidence.append(event.seq)


def _handle_task_retried(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    if task.status != TaskStatus.SCHEDULED:
        raise IllegalTransition(
            f"task_retried: task {task_id!r} is {task.status!r}, expected scheduled"
        )
    task.attempts = event.attempt
    task.next_retry_at = None
    task.worker_id = None
    task.last_event_at = event.ts
    task.evidence.append(event.seq)
    task.status = TaskStatus.PENDING
    _try_promote_to_ready(task, state)


def _handle_task_dlq(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    # PENDING/SCHEDULED allowed for cascade-from-dep: dep went to DLQ, so dependent
    # can never run and goes directly to DLQ. SCHEDULED added for C5: a task waiting
    # for retry whose dep entered DLQ should be cascaded immediately, not left scheduled.
    if task.status not in (TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.SCHEDULED):
        raise IllegalTransition(
            f"task_dlq: task {task_id!r} is {task.status!r}, expected failed, running, pending, or scheduled"
        )
    task.status = TaskStatus.DLQ
    task.last_event_at = event.ts
    task.evidence.append(event.seq)


def _handle_circuit_breaker_tripped(state: OrchState, event: Event) -> None:
    state.circuit_breaker = {"status": "tripped", **event.data}


def _handle_human_response(state: OrchState, event: Event) -> None:
    # Any human_response resolves the active escalation, regardless of action.
    # Clearing run_status and escalation here is required so that the meta-orchestrator
    # can correctly derive run_status as "active" on the next invocation instead of
    # re-entering the escalated terminal check (P2 invariant).
    state.escalation = None
    if state.run_status == "escalated":
        state.run_status = "active"

    action = event.data.get("action")
    if action == "reset_circuit_breaker":
        state.circuit_breaker = None
        state.failure_timestamps.clear()


_HANDLERS: dict[str, Any] = {
    EventType.PHASE_DECLARED: _handle_phase_declared,
    EventType.PHASE_ENTERED: _handle_phase_entered,
    EventType.PHASE_EXIT_CRITERION_MET: _handle_phase_exit_criterion_met,
    EventType.PHASE_EXIT_APPROVED: _handle_phase_exit_approved,
    EventType.PHASE_TRANSITIONED: _handle_phase_transitioned,
    EventType.PHASE_PAUSED: _handle_phase_paused,
    EventType.PHASE_RESUMED: _handle_phase_resumed,
    EventType.TASK_CREATED: _handle_task_created,
    EventType.TASK_CLAIMED: _handle_task_claimed,
    EventType.TASK_PROGRESS: _handle_task_progress,
    EventType.TASK_COMPLETED: _handle_task_completed,
    EventType.TASK_SKIPPED: _handle_task_skipped,
    EventType.TASK_FAILED: _handle_task_failed,
    EventType.TASK_SCHEDULED_RETRY: _handle_task_scheduled_retry,
    EventType.TASK_RETRIED: _handle_task_retried,
    EventType.TASK_DLQ: _handle_task_dlq,
    EventType.ESCALATION: _handle_escalation,
    EventType.CIRCUIT_BREAKER_TRIPPED: _handle_circuit_breaker_tripped,
    EventType.HUMAN_RESPONSE: _handle_human_response,
    # log_recovered is a no-op in the reducer — it's an audit marker only
}


# ---------------------------------------------------------------------------
# Reducer — public API
# ---------------------------------------------------------------------------

def apply_event(state: OrchState, event: Event) -> OrchState:
    """
    Applies a single event to state, returning updated state.

    Mutates state in-place and returns it. deepcopy before calling if you
    need to preserve the original.

    Known event types with no reducer effect (e.g. snapshot) are silently
    skipped — last_seq is still updated. (task_progress DOES have an effect: it
    advances last_event_at as a liveness heartbeat — see _handle_task_progress.)

    Raises:
        IllegalTransition: Event implies an illegal state transition.
        UnknownEventType: event_type is not a recognized EventType value.
    """
    if event.event_type not in _EVENT_TYPE_VALUES:
        raise UnknownEventType(f"Unrecognized event type: {event.event_type!r}")

    handler = _HANDLERS.get(event.event_type)
    if handler is not None:
        # Transparently resolve externalized blob so handlers always see full data.
        original_data = event.data
        if is_blob_ref(event.data):
            event.data = load_blob_data(event)
        try:
            handler(state, event)
        except IllegalTransition as exc:
            # Enrich with the offending event's context so the failure can be
            # pinpointed without re-scanning the log. Only fill fields the
            # handler did not already set (handlers raise message-only).
            if exc.seq is None:
                exc.seq = event.seq
            if exc.task_id is None:
                exc.task_id = event.task_id
            if exc.event_type is None:
                exc.event_type = event.event_type
            if exc.workflow_id is None:
                exc.workflow_id = event.data.get("workflow_id")
            if exc.phase is None:
                exc.phase = event.data.get("phase")
            raise
        finally:
            event.data = original_data

    state.last_seq = event.seq
    return state


# ---------------------------------------------------------------------------
# State snapshot cache (Task 1.8) — O(tail) reduction instead of O(log)
# ---------------------------------------------------------------------------
# The snapshot is a DERIVED CACHE, not state (P1 — the log stays the only
# truth): a JSON file under STATE_DIR holding {seq, boundary_offset,
# event_hash, engine_rev, state}. Loading seeks to boundary_offset, re-reads
# that one line, and accepts the cache only if the event there still has the
# recorded seq and hash — any mismatch (log truncated by recovery, log
# replaced, file tampered, engine code changed, JSON corrupt) silently falls
# back to a full replay, which then re-primes the cache. Deleting the file is
# always safe. ORCH_SNAPSHOT=0 disables both load and write.

_SNAPSHOT_SCHEMA = 1
_ENGINE_REV: str | None = None


def _engine_rev() -> str:
    """Content hash of this module — any engine change invalidates all
    snapshots (over-invalidation is safe: one full replay re-primes)."""
    global _ENGINE_REV
    if _ENGINE_REV is None:
        try:
            _ENGINE_REV = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
        except OSError:
            _ENGINE_REV = "unknown"
    return _ENGINE_REV


def _snapshot_enabled() -> bool:
    return os.environ.get("ORCH_SNAPSHOT", "1") != "0"


def _snapshot_path() -> Path:
    return STATE_DIR / "snapshot.json"


def _read_offset_lines(path: Path, start_offset: int = 0) -> list[tuple[int, bytes]]:
    """Non-empty lines of `path` from `start_offset`, as (line_start_offset, raw)."""
    with open(path, "rb") as f:
        f.seek(start_offset)
        data = f.read()
    out: list[tuple[int, bytes]] = []
    pos = start_offset
    for raw in data.split(b"\n"):
        if raw.strip():
            out.append((pos, raw))
        pos += len(raw) + 1
    return out


def _last_event_boundary() -> tuple[int, "Event"] | None:
    """(line_start_offset, event) of the last parseable log line, or None."""
    if not LOG_PATH.exists():
        return None
    try:
        pairs = _read_offset_lines(LOG_PATH)
    except OSError:
        return None
    for off, raw in reversed(pairs):
        try:
            return off, Event.from_dict(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
            continue
    return None


def _load_reduce_snapshot() -> tuple["OrchState", int, int] | None:
    """Validated snapshot as (base_state, tail_start_offset, base_seq), or None.

    None ALWAYS means "do a full replay" — the cache is disposable by design,
    so every anomaly is swallowed here rather than surfaced.
    """
    if not _snapshot_enabled():
        return None
    try:
        snap = json.loads(_snapshot_path().read_text(encoding="utf-8"))
        if not isinstance(snap, dict) or snap.get("schema") != _SNAPSHOT_SCHEMA:
            return None
        if snap.get("engine_rev") != _engine_rev():
            return None
        seq = int(snap["seq"])
        boundary = int(snap["boundary_offset"])
        if not LOG_PATH.exists():
            return None
        with open(LOG_PATH, "rb") as f:
            f.seek(0, 2)
            if f.tell() <= boundary:
                return None  # log shrank (recovery truncation / replacement)
            f.seek(boundary)
            line = f.readline()
        event = Event.from_dict(json.loads(line.decode("utf-8")))
        if event.seq != seq or event.hash != snap["event_hash"]:
            return None
        state = OrchState.from_dict(snap["state"])
        if state.last_seq != seq:
            return None
    except Exception:  # noqa: BLE001 — cache must never take the engine down
        return None
    return state, boundary + len(line), seq


def _write_reduce_snapshot(state: "OrchState", boundary_offset: int,
                           event_hash: str) -> None:
    """Best-effort atomic cache write — failure is silent by design."""
    if not _snapshot_enabled():
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": _SNAPSHOT_SCHEMA,
            "engine_rev": _engine_rev(),
            "seq": state.last_seq,
            "boundary_offset": boundary_offset,
            "event_hash": event_hash,
            "written_at": now_iso(),
            "state": state.to_dict(),
        }
        tmp = _snapshot_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, _snapshot_path())
    except Exception:  # noqa: BLE001 — cache write is opportunistic
        pass


def reduce_all() -> OrchState:
    """
    Builds state by replaying events — from the snapshot cache's boundary
    when a valid snapshot exists (O(tail)), else from log start (O(log)).

    Snapshot semantics: the cache is validated against the log (seq + hash of
    the boundary event re-read in place) before use; any mismatch falls back
    to a full replay. A fresh snapshot is written whenever the replayed tail
    reaches SNAPSHOT_EVERY_N_EVENTS. Both paths produce the identical state —
    ORCH_SNAPSHOT=0 forces the full path.

    Raises:
        IllegalTransition: Log contains illegal transition.
        CorruptedLogError: Log is corrupted.
    """
    loaded = _load_reduce_snapshot()
    if loaded is not None:
        state, tail_start, base_seq = loaded
        last_boundary: tuple[int, str] | None = None
        pairs = _read_offset_lines(LOG_PATH, tail_start)
        last_idx = len(pairs) - 1
        for i, (off, raw) in enumerate(pairs):
            try:
                event = Event.from_dict(json.loads(raw.decode("utf-8")))
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as exc:
                if i == last_idx:
                    break  # truncated last line — tolerate (read_events semantics)
                raise CorruptedLogError(
                    f"Invalid JSON at byte offset {off}: {exc}"
                ) from exc
            apply_event(state, event)
            last_boundary = (off, event.hash)
        if last_boundary is not None \
                and state.last_seq - base_seq >= SNAPSHOT_EVERY_N_EVENTS:
            _write_reduce_snapshot(state, last_boundary[0], last_boundary[1])
        return state

    state = OrchState()
    for event in read_events():
        apply_event(state, event)
    if _snapshot_enabled() and state.last_seq >= SNAPSHOT_EVERY_N_EVENTS:
        b = _last_event_boundary()
        if b is not None and b[1].seq == state.last_seq:
            _write_reduce_snapshot(state, b[0], b[1].hash)
    return state


@dataclass
class Violation:
    """A single illegal transition encountered during tolerant reduction.

    Mirrors the enriched-`IllegalTransition` locus so consumers get the same
    fields whether they catch the strict exception or list violations.
    """

    seq: int | None
    task_id: str | None
    event_type: str | None
    workflow_id: str | None
    phase: str | None
    message: str


def reduce_all_tolerant() -> tuple[OrchState, list[Violation]]:
    """Replay all events, collecting every illegal transition instead of
    stopping at the first.

    This is a DIAGNOSTIC variant for read-only consumers (e.g. the monitor).
    The engine MUST use the strict `reduce_all` — the validator rejecting a
    bad log is a feature, not a bug. Here an offending event is recorded as a
    `Violation` and skipped (not applied); reduction continues so the operator
    sees the full list, including any cascade the skip produces.

    A `CorruptedLogError` (broken hash chain / invalid JSON) still propagates:
    once the chain is untrustworthy, no further event can be trusted.

    Returns:
        (state, violations) — partial state and the violations in log order.
    """
    state = OrchState()
    violations: list[Violation] = []
    for event in read_events():
        try:
            apply_event(state, event)
        except IllegalTransition as exc:
            violations.append(Violation(
                seq=exc.seq if exc.seq is not None else event.seq,
                task_id=exc.task_id if exc.task_id is not None else event.task_id,
                event_type=exc.event_type if exc.event_type is not None else event.event_type,
                workflow_id=exc.workflow_id,
                phase=exc.phase,
                message=str(exc),
            ))
            # Skip the offending event; keep reducing the rest.
            state.last_seq = event.seq
        except UnknownEventType as exc:
            violations.append(Violation(
                seq=event.seq, task_id=event.task_id, event_type=event.event_type,
                workflow_id=event.data.get("workflow_id"), phase=event.data.get("phase"),
                message=str(exc),
            ))
            state.last_seq = event.seq
    return state, violations


def reduce_workflow(workflow_id: str) -> OrchState:
    """Reduce ONLY the events belonging to `workflow_id` into a fresh OrchState.

    Workflow isolation (strategy B — derive on reduction; compatible with existing
    logs, no back-fill). Attribution precedence per event:

    1. explicit `data.workflow_id` on the event (always wins);
    2. the task→workflow map: a `task_created` whose resolved workflow is known
       binds its task_id, and every later event for that task follows the
       binding — robust against interleaved workflows (5-a: orchestrators stamp
       `workflow_id` into every task_created they emit);
    3. positional fallback (legacy logs): every event between one
       `phase_declared` and the next belongs to the workflow it declared.

    Events before any `phase_declared` with no embedded id and no task binding
    belong to no workflow and are skipped.

    Why this exists: `reduce_all` is global — a single illegal transition in ONE
    workflow aborts reduction for the WHOLE log, stalling every other workflow.
    Reducing per-workflow scopes that failure to its own workflow. The decision
    engine still defaults to the strict `reduce_all`; this is the scoped variant a
    caller uses to keep healthy workflows derivable when a sibling is corrupted.

    The reduction itself stays STRICT: an illegal transition inside `workflow_id`
    still raises `IllegalTransition` (scoped to this workflow). Use
    `reduce_all_tolerant` for diagnostic, non-raising reduction.

    Raises:
        IllegalTransition: the target workflow's events contain an illegal transition.
        CorruptedLogError: log is corrupted (broken hash chain / invalid JSON).
    """
    state = OrchState()
    current_wf: str | None = None
    task_wf: dict[str, str] = {}
    for event in read_events():
        data = event.data
        if is_blob_ref(data):
            try:
                data = load_blob_data(event)
            except Exception:  # noqa: BLE001
                data = {}
        if event.event_type == EventType.PHASE_DECLARED.value:
            declared = data.get("workflow_id")
            if declared:
                current_wf = declared
        if event.event_type == EventType.TASK_CREATED.value:
            # A task_created is a (re-)incarnation: attribute it by explicit id or
            # the positional boundary — NEVER by the binding map, or the first
            # creation would own the id forever and a legacy workflow's legitimate
            # reuse of a bare id (pre-5-a logs) would misattribute every later
            # event to the earlier workflow. The new creation REBINDS the id.
            event_wf = data.get("workflow_id") or current_wf
            if event.task_id and event_wf:
                task_wf[event.task_id] = event_wf
        else:
            event_wf = (
                data.get("workflow_id")
                or (task_wf.get(event.task_id) if event.task_id else None)
                or current_wf
            )
        if event_wf == workflow_id:
            apply_event(state, event)
    return state


def scoped_phase_tasks(state: "OrchState", phase: str) -> list["TaskState"]:
    """Tasks of `phase`, scoped to ORCH_WORKFLOW_ID when set (5-a gate scoping).

    Exit gates used to read the GLOBAL state: another workflow's non-terminal
    task in the shared log could block (or wrongly satisfy) the current
    workflow's phase exit forever. When ORCH_WORKFLOW_ID is set, a task is in
    scope when its TaskState.workflow_id (stamped from task_created data)
    matches — or when it has NO binding (legacy pre-5-a task): a workflow
    upgraded mid-flight must keep seeing its own un-namespaced tasks, and the
    residual overlap with other legacy workflows is exactly the pre-5-a status
    quo, never worse. With ORCH_WORKFLOW_ID unset behavior is unchanged (global).
    """
    wf = os.environ.get("ORCH_WORKFLOW_ID")
    tasks = [t for t in state.tasks.values() if t.phase == phase]
    if not wf:
        return tasks
    return [t for t in tasks if t.workflow_id == wf or t.workflow_id is None]


def detect_stale_orchestrator(
    state: OrchState,
    events: list[Event],
    now: str,
    threshold: int = ORCHESTRATOR_STALE_SECONDS,
) -> dict[str, Any] | None:
    """Detect an orchestrator that stopped with non-terminal tasks remaining.

    Complements `stale_tasks` / `reap_stale_tasks`, which cover only RUNNING tasks
    hung past their tier threshold. This covers the orthogonal hazard: the active
    phase has tasks in READY/PENDING/SCHEDULED/RUNNING/FAILED (anything not terminal)
    but the orchestrator emitted no `orchestrator_heartbeat` within `threshold`
    seconds — i.e. the orchestrator died/stalled and nobody is dispatching the
    remaining tasks. `verify_and_recover` is NOT triggered here (it is destructive
    and manual by design); this is detection + an actionable signal only.

    Pure function (no I/O) so it is unit-testable and reusable by both the on_stop
    backstop and the live orchestrator's Step 5.0 check (check_stale.py).

    Returns a diagnostic dict (workflow_id, phase, pending_task_ids, command) when
    stale, else None.
    """
    if state.current_phase is None:
        return None
    phase = state.phases.get(state.current_phase)
    phase_status = phase.status.value if phase and hasattr(phase.status, "value") else (phase.status if phase else None)
    if not phase or phase_status != "active":
        return None

    _TERMINAL = (TaskStatus.COMPLETED.value, TaskStatus.DLQ.value, TaskStatus.SKIPPED.value)
    pending = [
        t for t in state.tasks.values()
        if t.phase == state.current_phase
        and (t.status.value if hasattr(t.status, "value") else t.status) not in _TERMINAL
    ]
    if not pending:
        return None

    heartbeats = [
        e for e in events
        if e.event_type == "orchestrator_heartbeat"
        and e.data.get("phase") == state.current_phase
    ]
    if heartbeats:
        last_hb = max(heartbeats, key=lambda e: e.seq)
        try:
            age = (parse_iso(now) - parse_iso(last_hb.ts)).total_seconds()
            if age < threshold:
                return None
        except (ValueError, TypeError):
            pass

    return {
        "stale_orchestrator": state.current_phase,
        "workflow_id": state.workflow_id,
        "pending_tasks": len(pending),
        "pending_task_ids": [t.task_id for t in pending],
        "last_heartbeat": heartbeats[-1].ts if heartbeats else None,
        "action_required": (
            "Orchestrator stopped making progress with non-terminal tasks remaining. "
            "Re-invoke /u-orchestrator — the log is intact and execution will resume "
            "from the current state."
        ),
        "command": "/u-orchestrator",
    }


def compute_progress(state: "OrchState") -> dict[str, Any]:
    """Rec #8 — estimable progress for ETA / observability. Pure function of the
    derived state: overall + per-phase task completion. Terminal counts as
    completed | dlq | skipped. Orchestrators may emit this in heartbeats; on_stop
    surfaces it in metrics. No I/O, no time math — safe to call anywhere."""
    terminal = {TaskStatus.COMPLETED, TaskStatus.DLQ, TaskStatus.SKIPPED}

    def _pct(done: int, total: int) -> float:
        return round(100.0 * done / total, 1) if total else 0.0

    by_phase: dict[str, dict[str, Any]] = {}
    total = 0
    done = 0
    for t in state.tasks.values():
        total += 1
        is_term = t.status in terminal
        done += 1 if is_term else 0
        ph = by_phase.setdefault(t.phase, {"total": 0, "terminal": 0})
        ph["total"] += 1
        ph["terminal"] += 1 if is_term else 0
    for ph in by_phase.values():
        ph["remaining"] = ph["total"] - ph["terminal"]
        ph["pct_complete"] = _pct(ph["terminal"], ph["total"])

    return {
        "tasks_total": total,
        "tasks_terminal": done,
        "tasks_remaining": total - done,
        "pct_complete": _pct(done, total),
        "current_phase": state.current_phase,
        "by_phase": by_phase,
    }


def stale_threshold_seconds(task: TaskState, config: dict[str, Any] | None = None) -> int:
    """Resolves the stale threshold (seconds) for a task (F-02).

    Resolution order (single source of truth for both the stale reaper and the
    SubagentStop liveness window):
      1. stale_policy.overrides_by_task_type[task.task_type]  — writers drafting
         large artifacts go silent for minutes; they get a longer window.
      2. stale_policy.defaults_by_tier[task.tier]             — per-tier default.
      3. Tier(task.tier).default_stale_seconds                — hard-coded fallback.
    """
    cfg = config if config is not None else load_config()
    sp = cfg.get("stale_policy", {}) if isinstance(cfg, dict) else {}
    overrides = sp.get("overrides_by_task_type", {}) or {}
    tt = task.task_type or ""
    if tt in overrides:
        try:
            return int(overrides[tt])
        except (TypeError, ValueError):
            pass
    try:
        tier = Tier(task.tier)
    except ValueError:
        tier = Tier.STANDARD
    tier_defaults = sp.get("defaults_by_tier", {}) or {}
    if tier.value in tier_defaults:
        try:
            return int(tier_defaults[tier.value])
        except (TypeError, ValueError):
            pass
    return tier.default_stale_seconds


def worker_liveness_expired(
    task: TaskState, now: str, config: dict[str, Any] | None = None
) -> bool:
    """True when a worker's task has been silent long enough that the SubagentStop
    hook may safely synthesize its terminal (F-03).

    SubagentStop fires on ANY subagent's stop and carries no key correlating it to
    a specific registered worker. Synthesizing a terminal for a worker whose last
    event is recent would kill a sibling worker still mid-flight and spawn a retry
    that races the original (latent file/branch corruption). The hook therefore
    only acts once the worker is silent past its stale threshold — the SAME bound
    the stale reaper uses (stale_threshold_seconds), so the two never disagree.
    Genuine deaths still get a terminal: here once expired, or via reap_stale_tasks
    at orchestrator Step 5.0 / session end.

    A task with no recorded activity at all (last_event_at is None) returns True —
    there is no evidence of life to protect.
    """
    if task.last_event_at is None:
        return True
    threshold = stale_threshold_seconds(task, config)
    return _elapsed_seconds(now, task.last_event_at) > threshold


def stale_tasks(state: OrchState, now: str, config: dict[str, Any] | None = None) -> list[TaskState]:
    """
    Returns tasks in `running` status whose last activity exceeds their
    stale threshold (F-02: task-type aware, config-driven).

    A task is stale when (now - last_event_at) > stale_threshold_seconds(task).
    `last_event_at` is updated on every event for the task, including
    task_progress, so recent heartbeats reset the staleness timer.

    Args:
        state:  Current OrchState (from reduce_all or reduce_incremental).
        now:    Current UTC time as ISO 8601 string (e.g. from now_iso()).
        config: Optional pre-loaded config; defaults to load_config().

    Returns:
        List of TaskState objects that are stale. Empty list if none.
    """
    cfg = config if config is not None else load_config()
    result: list[TaskState] = []
    for task in state.tasks.values():
        if task.status != TaskStatus.RUNNING:
            continue
        if task.last_event_at is None:
            continue
        threshold = stale_threshold_seconds(task, cfg)
        if _elapsed_seconds(now, task.last_event_at) > threshold:
            result.append(task)
    return result


def reap_stale_tasks(now: str | None = None) -> list[str]:
    """Emits task_failed(reason=stale_timeout) for every RUNNING task past its tier's
    stale threshold; returns the reaped task_ids.

    Deterministic runtime enforcement of the timeout invariant (A2-F1): a worker
    that hangs (process alive, emitting no events) is detected and failed by Python,
    not only by a prompt-level check the orchestrator LLM might skip. Thresholds
    come from stale_threshold_seconds() — task-type aware, config-driven (F-02),
    the single source of truth (A2-F6).
    Idempotent: a task already terminal/FAILED is a no-op in the reducer. Callable
    from check_stale.py (orchestrator Step 5.0) and on_stop.py (session-end backstop).
    """
    now = now or now_iso()
    cfg = load_config()
    state = reduce_all()
    reaped: list[str] = []
    for task in stale_tasks(state, now, cfg):
        try:
            failed = append_event(
                agent="stale-monitor",
                event_type=EventType.TASK_FAILED.value,
                task_id=task.task_id,
                attempt=task.attempts or 1,
                data={"phase": task.phase, "reason": "stale_timeout", "retryable": True},
            )
            reaped.append(task.task_id)
            # F3/F4: schedule the retry atomically in this same Python call so the
            # task never stalls in FAILED if the orchestrator turn ends before Step 5.5.
            schedule_retry_if_due(task.task_id, failed.seq, now, cfg)
        except Exception:  # noqa: BLE001 — a reaper must never raise
            continue
    return reaped


def consumed_manifest_ids(events: list[Event]) -> set[str]:
    """Returns the set of manifest_ids that have a handoff_receipt in the log.

    Lets the Spec orchestrator derive consumed/orphan handoff state from the log
    (P1/P12, A3-F5) instead of reading session side-files. Pure function.
    """
    out: set[str] = set()
    for e in events:
        if e.event_type == EventType.HANDOFF_RECEIPT.value:
            data = load_blob_data(e) if is_blob_ref(e.data) else e.data
            mid = data.get("manifest_id")
            if mid:
                out.add(mid)
    return out


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def default_config() -> dict[str, Any]:
    """Returns the full default config (matches architecture §19)."""
    return {
        "version": "1.0",
        "retry_policy": {
            "defaults_by_tier": {
                "critical": {"max_attempts": 5, "base_delay_s": 15.0, "cap_s": 600.0},
                "standard": {"max_attempts": 3, "base_delay_s": 30.0, "cap_s": 600.0},
                "bulk":     {"max_attempts": 1, "base_delay_s": 0.0,  "cap_s": 0.0},
            },
            "overrides_by_task_type": {},
        },
        # Allowlist for the clean-tree gates (check_qa_on_integrated_main,
        # check_all_branches_integrated). fnmatch patterns matched against each
        # dirty entry's repo-relative path AND basename. Default [] = every
        # dirty entry blocks (behavior unchanged unless the operator opts in).
        # Gates MUST surface what they ignored in evidence — nothing silent.
        "clean_tree_gates": {
            "ignore_patterns": [],
        },
        "circuit_breaker": {
            # A4/CONF-01: window-based detection, STICKY trip. When failures in the
            # rolling window first reach failure_threshold, run_circuit_check.py appends
            # circuit_breaker_tripped (trip_circuit_if_due) and state.circuit_breaker is
            # set; the breaker then stays blocked (already_tripped) until a manual reset
            # (scripts/circuit_breaker.py --reset → human_response). It does NOT relax on
            # age-out — a persisted trip forces human attention. No cooldown / success-
            # reset logic — do NOT re-add cooldown_minutes or reset_on_success_count.
            "enabled": True,
            "window_minutes": 10,
            "failure_threshold": 50,
            "scope": "workflow",
        },
        # E2/B(b): bounded supervised auto-resume. supervisor_tick.py + /u-supervise
        # re-invoke a stalled phase orchestrator, capped so a persistently stuck workflow
        # escalates to a human (E23_resume_budget_exhausted) instead of looping forever.
        # All accounting is derived from the log (orchestrator_resumed / _resume_requested).
        "supervisor_policy": {
            "enabled": True,
            "max_auto_resumes": 3,          # per phase, since its last phase_entered
            "cooldown_seconds": 300,        # min gap between resumes of the same phase
            "in_flight_ttl_seconds": 900,   # a resume_requested older than this with no
                                            # following resumed/heartbeat is expired (no wedge)
        },
        "payload_limits": {
            "max_inline_bytes": 3500,
            "blob_storage_path": ".orch/blobs",
        },
        "verify": {
            "startup_mode": "strict",
            "auto_recover": False,
        },
        "preflight": {
            "runtime_threshold_tasks": 10,
            "timeout_seconds": 60,
        },
        # SIEGARD-02: dev-phase batch ceiling (max parallel impl workers per
        # dispatch cycle). Was a hardcoded 2 in the dev state machine; now
        # config-driven so independent Task Contracts can parallelise beyond 2.
        # The cap stays SM-owned (A6-F2): the orchestrator loads this policy and
        # passes it into the SM inputs; DevStateMachine clamps to >= 1 (default 2).
        "dispatch_policy": {
            "dev": {"max_concurrent": 2},
        },
        # F-02: stale-detection thresholds, configurable and task-type aware. A
        # worker may stay legitimately silent for minutes between semantic
        # checkpoints (e.g. a spec writer drafting a large artifact between
        # analysis_complete and draft_written). The flat per-tier thresholds were
        # too short for writers, producing stale_timeout false positives. Resolution
        # order in stale_threshold_seconds(): task_type override > tier default > Tier enum.
        "stale_policy": {
            # Tier defaults derive from Tier.default_stale_seconds — single source of
            # truth (A2-F6); editing the enum propagates here automatically.
            "defaults_by_tier": {t.value: t.default_stale_seconds for t in Tier},
            # Keys are the task_type values emitted in task_created (see orchestrators).
            "overrides_by_task_type": {
                "spec-writer": 1200,
                "spec-back": 1200,
                "spec-front": 1200,
                "spec-reviewer": 900,
                "spec-validator": 900,
                "spec-compliance": 900,
                "spec-triage": 600,
                "impl": 1200,
                "planning": 900,
                "qa": 900,
                # SIEGARD BUG-1: a real test-runner ran 1496s (a long but live suite);
                # the old 1200s window would reap it as stale. Test suites emit no
                # semantic heartbeats while running, so the window must exceed the
                # worst observed runtime — 1800s (30 min) gives headroom above 1496s.
                "test-run": 1800,
                "security-review": 900,
                "architecture-review": 900,
            },
        },
        "phases": {
            "default_workflow": "dev-cycle",
            "workflows": {
                "dev-cycle": {"description": "Feature development", "phases": ["sdd", "dev", "review", "test"]},
                "bug-fix":   {"description": "Bug fix", "phases": ["reproduce", "fix", "verify", "regression"]},
                "refactor":  {"description": "Refactor", "phases": ["analyze", "migrate", "verify"]},
                "spike":     {"description": "Research spike", "phases": ["research", "document"]},
            },
        },
    }


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    Loads .orch/config.json with defaults for missing fields.

    If file doesn't exist, returns full default config.

    Raises:
        ConfigError: File exists but contains invalid JSON.
    """
    path = config_path or CONFIG_PATH
    cfg = default_config()
    if not path.exists():
        return cfg
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid config JSON at {path}: {exc}") from exc
    # Recursive deep-merge: a partial nested override (e.g. stale_policy with only
    # defaults_by_tier.critical) must not wipe sibling sub-keys (standard/bulk,
    # overrides_by_task_type). A shallow .update() replaced whole sub-dicts and
    # silently dropped the writer-protective stale defaults (F-02 regression).
    _deep_merge(cfg, loaded)
    return cfg


def split_porcelain_by_allowlist(
    porcelain: str,
    patterns: list[str],
) -> tuple[list[str], list[str]]:
    """Partitions `git status --porcelain` output into (dirty, ignored) lines.

    The clean-tree gates block on ANY dirty entry, which lets pre-existing
    operator tooling unrelated to the workflow (dev.sh, tmux.conf) hard-block a
    phase transition. `clean_tree_gates.ignore_patterns` (.orch/config.json)
    declares fnmatch patterns for such entries: a line is ignored when its
    repo-relative path OR its basename matches any pattern (renames match on
    either side of `->`). With no patterns (the default) every dirty line
    blocks — exactly the pre-allowlist behavior.

    Transparency contract: callers MUST surface the returned `ignored` list in
    the gate's evidence — an allowlisted entry is visible, never silent.
    """
    dirty: list[str] = []
    ignored: list[str] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        path_part = line[3:] if len(line) > 3 else line
        names: set[str] = set()
        for cand in path_part.split(" -> "):
            cand = cand.strip().strip('"')
            if cand:
                names.add(cand)
                names.add(cand.rsplit("/", 1)[-1])
        if patterns and any(
            fnmatch.fnmatch(name, pat) for name in names for pat in patterns
        ):
            ignored.append(line)
        else:
            dirty.append(line)
    return dirty, ignored


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merges `override` into `base` in place; returns `base`.

    Dict values are merged key-by-key at every level; non-dict values (scalars,
    lists) replace wholesale. This preserves default sub-keys the operator did not
    restate, for any nesting depth (stale_policy, retry_policy, phases).
    """
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """Retry configuration for a tier or task_type."""
    max_attempts: int
    base_delay_s: float
    cap_s: float

    @classmethod
    def for_tier(cls, tier: str, config: dict) -> "RetryPolicy":
        """Loads policy from config defaults for the given tier."""
        defaults = config.get("retry_policy", {}).get("defaults_by_tier", {})
        t = Tier(tier) if tier in (t.value for t in Tier) else Tier.STANDARD
        d = defaults.get(t.value, {})
        return cls(
            max_attempts=d.get("max_attempts", t.default_max_attempts),
            base_delay_s=d.get("base_delay_s", t.default_base_delay_s),
            cap_s=d.get("cap_s", 600.0),
        )

    @classmethod
    def for_task(cls, task_type: str, tier: str, config: dict) -> "RetryPolicy":
        """Loads policy with task_type override precedence over tier defaults."""
        overrides = config.get("retry_policy", {}).get("overrides_by_task_type", {})
        if task_type and task_type in overrides:
            ov = overrides[task_type]
            # Start from tier defaults, then apply overrides
            base = cls.for_tier(tier, config)
            return cls(
                max_attempts=ov.get("max_attempts", base.max_attempts),
                base_delay_s=ov.get("base_delay_s", base.base_delay_s),
                cap_s=ov.get("cap_s", base.cap_s),
            )
        return cls.for_tier(tier, config)


def backoff_seconds(
    attempts: int,
    base_delay_s: float = 30.0,
    cap_s: float = 600.0,
    jitter_range: tuple[float, float] = (0.8, 1.2),
) -> float:
    """
    Computes exponential backoff with multiplicative jitter.

    formula: min(base * 2^(attempts-1), cap) * uniform(jitter_range)

    Args:
        attempts: Attempt number that just failed (>= 1).
        base_delay_s: Base delay in seconds for the first retry.
        cap_s: Maximum delay before jitter.
        jitter_range: (low, high) multiplicative jitter.

    Returns:
        Seconds to wait before next retry (>= 0).
    """
    if attempts < 1:
        attempts = 1
    raw = min(base_delay_s * (2 ** (attempts - 1)), cap_s)
    return raw * random.uniform(*jitter_range)


def load_retry_policy(
    tier: str,
    task_type: str | None = None,
    config_path: Path | None = None,
) -> RetryPolicy:
    """
    Loads retry policy from config with task_type override precedence.

    Args:
        tier: Task tier (critical/standard/bulk).
        task_type: Optional task_type for override lookup.
        config_path: Override default config path.

    Returns:
        RetryPolicy to apply.
    """
    cfg = load_config(config_path)
    return RetryPolicy.for_task(task_type or "", tier, cfg)


def should_retry(task: TaskState, policy: RetryPolicy) -> bool:
    """
    Returns True if task should be retried after a failure.

    Rules (in order):
      - last_failure_retryable is False → False (immediate DLQ)
      - structural failure reasons cap at 1 retry (attempt 2 = already retried once)
      - attempts >= policy.max_attempts → False (max exhausted)
      - otherwise → True

    Structural reasons (agent could not execute, not a logic error) — these are the
    synthesized worker/task-level task_failed reasons in _VALID_FAILURE_REASONS:
      worker_exited_without_terminal, stale_timeout
    (CONF-02: `subagent_invalid_response` was previously listed here but is a
    meta→phase-orchestrator envelope/escalation concept — code E13_subagent_invalid_response,
    with its own retry logic in orchestrator.md — never a task_failed reason. It is not
    in _VALID_FAILURE_REASONS, so a task's last_failure_reason can never equal it; the
    entry was dead. Removed to keep this set == the real structural reason enum.)
    """
    if task.last_failure_retryable is False:
        return False
    _STRUCTURAL_REASONS = frozenset({
        "worker_exited_without_terminal",
        "stale_timeout",
    })
    if task.last_failure_reason in _STRUCTURAL_REASONS and task.attempts >= 2:
        return False
    if task.attempts >= policy.max_attempts:
        return False
    return True


def schedule_retry_if_due(
    task_id: str,
    previous_failure_seq: int,
    now: str | None = None,
    config: dict[str, Any] | None = None,
) -> str | None:
    """Emit task_scheduled_retry for a just-failed task IN THE SAME PYTHON CALL as the
    failure, when the failure is retryable (F3/F4 — SIEGARD BUG-4).

    The stale reaper and the SubagentStop hook emit task_failed from Python, but the
    matching task_scheduled_retry was emitted only later by the orchestrator LLM (Step
    5.5). If the orchestrator turn ended between the two, the task stalled in FAILED
    forever with nobody scheduling the retry. Emitting the retry here removes that
    single point of failure: even if the turn dies immediately after, the task is
    already SCHEDULED and the next orchestrator invocation resumes it via due_retries.

    Contract:
      - Re-derives state and acts ONLY when the task is currently FAILED. A concurrent
        retry/DLQ that already advanced it is left untouched (no double-schedule; the
        orchestrator's Step 5.5 iterates status==failed, so it won't re-schedule this).
      - Non-retryable failures (should_retry False — max attempts, structural cap, or
        retryable=False) are left FAILED for the orchestrator to route to DLQ.
      - Never raises: a reaper/hook path must not crash. Returns next_retry_at when it
        scheduled a retry, else None.
    """
    from datetime import timedelta

    now = now or now_iso()
    cfg = config if config is not None else load_config()
    try:
        state = reduce_all()
    except Exception:  # noqa: BLE001 — never raise from a reaper/hook path
        return None
    task = state.tasks.get(task_id)
    if task is None or task.status != TaskStatus.FAILED:
        return None
    policy = RetryPolicy.for_task(task.task_type or "", task.tier, cfg)
    if not should_retry(task, policy):
        return None
    delay = backoff_seconds(task.attempts, policy.base_delay_s, policy.cap_s)
    retry_dt = parse_iso(now) + timedelta(seconds=delay)
    next_retry_at = (
        retry_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{retry_dt.microsecond // 1000:03d}Z"
    )
    try:
        append_event(
            agent="stale-monitor",
            event_type=EventType.TASK_SCHEDULED_RETRY.value,
            task_id=task_id,
            attempt=task.attempts,
            data={
                "phase": task.phase,
                "next_retry_at": next_retry_at,
                "backoff_seconds": round(delay, 3),
                "previous_failure_seq": previous_failure_seq,
            },
        )
    except Exception:  # noqa: BLE001 — never raise from a reaper/hook path
        return None
    return next_retry_at


def parse_manifest_fields(content: str) -> dict[str, Any]:
    """
    Parses a subset of fields from a handoff-manifest.yaml string without
    external dependencies. Supports unquoted, single-quoted, and double-quoted
    scalar values, and inline comments.

    Extracted fields:
        stack        — "be"|"fe"|"fullstack" when explicit or inferable from
                       backend_package/frontend_package presence; else None (A3-F7 fail-closed)
        type         — handoff type string (default: "new_domain")
        dev_impact   — dev impact string (default: "")
        changed_files — list of strings from the changed_files block (default: [])

    Returns:
        dict with keys: stack, type, dev_impact, changed_files
    """
    def _extract_scalar(key: str, text: str, default: str = "") -> str:
        # Matches: key: value  or  key: "value"  or  key: 'value'
        # Strips inline comments (# ...) from unquoted values.
        pattern = (
            r'^\s*' + re.escape(key) + r'\s*:\s*'
            r'(?:"([^"]*)"'        # double-quoted
            r"|'([^']*)'"          # single-quoted
            r'|([^#\n\r]*))'       # unquoted (stops before comment)
        )
        m = re.search(pattern, text, re.MULTILINE)
        if not m:
            return default
        value = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        return value if value else default

    def _extract_list(key: str, text: str) -> list[str]:
        # Finds the block under `key:` and extracts `- item` entries.
        block_pattern = re.search(
            r'^\s*' + re.escape(key) + r'\s*:(.*?)(?=\n\s*\w|\Z)',
            text, re.DOTALL | re.MULTILINE,
        )
        if not block_pattern:
            return []
        block = block_pattern.group(1)
        items = re.findall(r'^\s*-\s+(.+)$', block, re.MULTILINE)
        return [i.strip().strip('"\'') for i in items if i.strip()]

    raw_stack = _extract_scalar("stack", content, "").lower()
    if raw_stack in {"be", "fe", "fullstack"}:
        stack = raw_stack
    else:
        # A3-F7: do NOT silently coerce an unknown/absent stack to "be" (that
        # mis-routed FE-only handoffs to BE workers). Infer from package presence;
        # if nothing resolves, return None so the caller fails-closed.
        has_be = bool(re.search(r"^\s*backend_package\s*:", content, re.MULTILINE))
        has_fe = bool(re.search(r"^\s*frontend_package\s*:", content, re.MULTILINE))
        if has_be and has_fe:
            stack = "fullstack"
        elif has_fe:
            stack = "fe"
        elif has_be:
            stack = "be"
        else:
            stack = None

    # Extract `type` from the `handoff:` block specifically to avoid matching
    # a `type:` key in a sibling block (e.g., change_summary.type).
    handoff_block_m = re.search(r'^handoff\s*:(.*?)(?=^\S|\Z)', content, re.DOTALL | re.MULTILINE)
    handoff_block = handoff_block_m.group(1) if handoff_block_m else content
    handoff_type = _extract_scalar("type", handoff_block, "new_domain").lower()

    dev_impact = _extract_scalar("dev_impact", content, "").lower()
    changed_files = _extract_list("changed_files", content)

    return {
        "stack": stack,
        "type": handoff_type,
        "dev_impact": dev_impact,
        "changed_files": changed_files,
    }


def tasks_ready_for_retry(state: OrchState, now: str) -> list[TaskState]:
    """
    Returns scheduled tasks whose next_retry_at has passed.

    Args:
        state: Current OrchState.
        now:   Current UTC time as ISO 8601 string.

    Returns:
        List of TaskState objects ready to be retried. Empty if none.
    """
    now_dt = parse_iso(now)
    result: list[TaskState] = []
    for task in state.tasks.values():
        if task.status != TaskStatus.SCHEDULED:
            continue
        if task.next_retry_at is None:
            result.append(task)
            continue
        retry_dt = _safe_parse_iso(task.next_retry_at)
        if retry_dt is None or retry_dt <= now_dt:
            # Malformed timestamp treated as overdue — retry immediately.
            result.append(task)
    return result


# ---------------------------------------------------------------------------
# Circuit breaker evaluation
# ---------------------------------------------------------------------------

def evaluate_circuit_state(
    state: OrchState,
    now: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Evaluates circuit breaker state based on failure frequency in the rolling window.

    Counts task_failed events recorded in state.failure_timestamps that fall within
    the last window_minutes. Returns a dict with:
      - should_trip (bool): True if failure_count >= threshold and breaker not already tripped
      - already_tripped (bool): True if circuit_breaker_tripped is already in state
      - failure_count (int): failures in current window
      - threshold (int): configured threshold
      - window_start (str): ISO timestamp of window start
      - window_end (str): now
      - window_minutes (float): configured window

    Args:
        state: Current OrchState (must have failure_timestamps populated).
        now:   Current UTC time as ISO 8601 string.
        config: Optional config dict; uses default_config() if None.
    """
    cfg = config if config is not None else default_config()
    cb_cfg = cfg.get("circuit_breaker", {})
    enabled: bool = cb_cfg.get("enabled", True)
    window_minutes: float = cb_cfg.get("window_minutes", 10)
    threshold: int = cb_cfg.get("failure_threshold", 50)

    now_dt = parse_iso(now)
    from datetime import timedelta
    window_start_dt = now_dt - timedelta(minutes=window_minutes)
    window_start = window_start_dt.isoformat()

    already_tripped: bool = state.circuit_breaker is not None

    if not enabled:
        return {
            "should_trip": False,
            "already_tripped": already_tripped,
            "failure_count": 0,
            "threshold": threshold,
            "window_start": window_start,
            "window_end": now,
            "window_minutes": window_minutes,
        }

    failure_count = sum(
        1 for ts in state.failure_timestamps
        if (dt := _safe_parse_iso(ts)) is not None and dt >= window_start_dt
    )

    should_trip = (not already_tripped) and (failure_count >= threshold)

    return {
        "should_trip": should_trip,
        "already_tripped": already_tripped,
        "failure_count": failure_count,
        "threshold": threshold,
        "window_start": window_start,
        "window_end": now,
        "window_minutes": window_minutes,
    }


def trip_circuit_if_due(
    now: str | None = None,
    config: dict | None = None,
    state: "OrchState | None" = None,
) -> "Event | None":
    """Append `circuit_breaker_tripped` when the failure window first crosses the
    threshold, so the breaker becomes PERSISTED state instead of an ephemeral
    per-cycle gate (CONF-01 — SIEGARD self-spec).

    Before this, `evaluate_circuit_state`/`run_circuit_check.py` only computed
    `should_trip` and blocked the cycle; nothing ever appended the event, so
    `state.circuit_breaker` was always None, the breaker relaxed silently when
    failures aged out of the window, and `circuit_breaker.py --reset` was
    unreachable (`no_cb_event`). Emitting the event here makes the breaker STICKY:
    once tripped it stays blocked (via `already_tripped`) until a human resets it
    with `circuit_breaker.py --reset` (human_response → `_handle_human_response`).

    Idempotent: `should_trip` is `(not already_tripped) and (count >= threshold)`,
    so once the trip is persisted a second call is a no-op (no duplicate event).
    Never raises — an infra check must not crash the orchestrator cycle.

    Returns the appended Event when it tripped, else None.
    """
    now = now or now_iso()
    cfg = config if config is not None else load_config()
    try:
        st = state if state is not None else reduce_all()
    except Exception:  # noqa: BLE001 — an infra check must not raise
        return None
    cb = evaluate_circuit_state(st, now, cfg)
    if not cb.get("should_trip"):
        return None
    try:
        return append_event(
            agent="circuit-monitor",
            event_type=EventType.CIRCUIT_BREAKER_TRIPPED.value,
            data={
                "window_start": cb["window_start"],
                "window_end": cb["window_end"],
                "failure_count": cb["failure_count"],
                "threshold": cb["threshold"],
            },
        )
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Escalation detection helpers
# ---------------------------------------------------------------------------

def detect_dependency_cycle(state: OrchState) -> list[str]:
    """
    Detects cycles in the task dependency graph using DFS.

    Returns a list of task_ids that form part of a cycle. Empty if no cycle.
    Only considers non-terminal tasks (pending, ready, running, scheduled, failed).
    """
    terminal = {TaskStatus.COMPLETED, TaskStatus.DLQ}
    live_tasks = {
        tid: t for tid, t in state.tasks.items()
        if t.status not in terminal
    }

    # Build adjacency: task → its unresolved deps
    adj: dict[str, list[str]] = {}
    for tid, task in live_tasks.items():
        adj[tid] = [d for d in task.deps if d in live_tasks]

    visited: set[str] = set()
    rec_stack: set[str] = set()
    cycle_nodes: list[str] = []

    def _dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbour in adj.get(node, []):
            if neighbour not in visited:
                if _dfs(neighbour):
                    return True
            elif neighbour in rec_stack:
                cycle_nodes.append(node)
                return True
        rec_stack.discard(node)
        return False

    for tid in list(adj.keys()):
        if tid not in visited:
            if _dfs(tid):
                break

    return cycle_nodes


def detect_deadlock(state: OrchState) -> bool:
    """
    Returns True if the workflow is deadlocked.

    Deadlock: tasks exist, none are ready/running/scheduled, and the remaining
    pending tasks cannot make progress (all their deps are DLQ or non-existent,
    or there is a dependency cycle).
    """
    if not state.tasks:
        return False

    actionable = {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.SCHEDULED}
    if any(t.status in actionable for t in state.tasks.values()):
        return False

    # Any pending tasks remaining?
    pending = [t for t in state.tasks.values() if t.status == TaskStatus.PENDING]
    if not pending:
        return False  # all tasks are terminal — not a deadlock, it's completion

    # Cycle among live tasks is always a deadlock
    if detect_dependency_cycle(state):
        return True

    # Check if any pending task can ever become ready:
    # A dep blocks progress if it is DLQ or does not exist
    blocking_statuses = {TaskStatus.DLQ}

    def _can_become_ready(task: TaskState) -> bool:
        for dep_id in task.deps:
            dep = state.tasks.get(dep_id)
            if dep is None or dep.status in blocking_statuses:
                return False
        return True

    if any(_can_become_ready(t) for t in pending):
        return False

    return True


def detect_critical_dlq(state: OrchState) -> list[str]:
    """
    Returns task_ids of critical-tier tasks that are in DLQ status.

    A critical task in DLQ requires immediate escalation (E04).
    """
    return [
        tid for tid, t in state.tasks.items()
        if t.status == TaskStatus.DLQ and t.tier == Tier.CRITICAL
    ]


# ---------------------------------------------------------------------------
# Worker registry — C1/C7: robust context for on_subagent_stop hook
# ---------------------------------------------------------------------------

def register_worker(
    worker_id: str,
    task_id: str,
    attempt: int,
    *,
    phase: str | None = None,
    stack: str | None = None,
    task_type: str | None = None,
    spawn_context_chars: int | None = None,
) -> None:
    """
    Writes a worker registry entry before the orchestrator spawns the agent.

    Idempotent: if an entry already exists for this worker_id with the same
    task_id and attempt, the call is a no-op. This prevents orphaned entries
    when an orchestrator is interrupted between register_worker() and the Agent
    spawn, and then re-invoked (it would otherwise overwrite a valid entry with
    a new registered_at timestamp, confusing staleness detection).

    The on_subagent_stop hook reads these entries to identify which task each
    subagent was handling, without relying on shell env vars (which are
    unreliable under parallel dispatch).
    """
    ensure_dirs()
    entry_path = WORKERS_DIR / f"{worker_id}.json"
    if entry_path.exists():
        try:
            existing = json.loads(entry_path.read_text(encoding="utf-8"))
            if existing.get("task_id") == task_id and existing.get("attempt") == attempt:
                return  # idempotent: same entry already registered
        except (json.JSONDecodeError, OSError):
            pass  # overwrite corrupt entry

    entry: dict[str, Any] = {
        "worker_id": worker_id,
        "task_id": task_id,
        "attempt": attempt,
        "registered_at": now_iso(),
    }
    if phase is not None:
        entry["phase"] = phase
    if stack is not None:
        entry["stack"] = stack
    if task_type is not None:
        entry["task_type"] = task_type
    # SIEGARD-01 follow-up: persist the spawn context size so on_subagent_stop's
    # _infer_cause can attribute a worker death to context_limit (its >150k branch
    # is otherwise dormant — the registry never carried this signal).
    if spawn_context_chars is not None:
        entry["spawn_context_chars"] = spawn_context_chars
    entry_path.write_text(
        json.dumps(entry, separators=(",", ":")),
        encoding="utf-8",
    )


def cleanup_stale_workers(max_age_seconds: int = 3600) -> list[str]:
    """
    Removes registry entries older than max_age_seconds that have no
    corresponding running task in the current log state.

    Returns the list of worker_ids that were removed.

    Call this at the start of each orchestrator dispatch cycle to prevent
    accumulation of orphaned entries from interrupted sessions. Only removes
    entries whose task is already in a terminal state (completed, dlq) or
    whose registered_at timestamp exceeds max_age_seconds — it never removes
    entries for genuinely running tasks.
    """
    if not WORKERS_DIR.exists():
        return []

    try:
        state = reduce_all()
    except Exception:
        return []

    removed: list[str] = []
    cutoff_dt = None
    try:
        from datetime import datetime, timezone
        cutoff_dt = datetime.now(timezone.utc).timestamp() - max_age_seconds
    except Exception:
        return []

    for p in list(WORKERS_DIR.glob("*.json")):
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            p.unlink(missing_ok=True)
            removed.append(p.stem)
            continue

        task_id = entry.get("task_id")
        attempt = entry.get("attempt")
        registered_at = entry.get("registered_at", "")

        # Remove if the task has already reached a terminal state
        task = state.tasks.get(task_id) if task_id else None
        if task and task.status in (TaskStatus.COMPLETED, TaskStatus.DLQ):
            p.unlink(missing_ok=True)
            removed.append(entry.get("worker_id", p.stem))
            continue

        # Remove if the entry is older than max_age_seconds
        if registered_at:
            try:
                reg_dt = parse_iso(registered_at).timestamp()
                if reg_dt < cutoff_dt:
                    p.unlink(missing_ok=True)
                    removed.append(entry.get("worker_id", p.stem))
            except Exception:
                pass

    return removed


def unregister_worker(worker_id: str) -> None:
    """Removes a worker registry entry after the task reaches a terminal state."""
    path = WORKERS_DIR / f"{worker_id}.json"
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def get_active_workers() -> list[dict[str, Any]]:
    """
    Returns all registry entries from .orch/workers/.

    Used by on_subagent_stop to find orphaned workers when env vars are absent.
    """
    if not WORKERS_DIR.exists():
        return []
    result: list[dict[str, Any]] = []
    for p in WORKERS_DIR.glob("*.json"):
        try:
            result.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return result


# ---------------------------------------------------------------------------
# Orchestrator report validation — C9
# ---------------------------------------------------------------------------

_REPORT_REQUIRED_FIELDS: dict[str, type] = {
    "status": str,
    "workflow_id": (str, type(None)),  # type: ignore[assignment]
    "current_phase": (str, type(None)),  # type: ignore[assignment]
    "last_seq": int,
    "tasks": dict,
    "dispatched": list,
    "next_actions": list,
    "issues": list,
}

_VALID_STATUSES = {"empty", "ready", "running", "blocked", "completed", "escalated", "error"}
_VALID_SEVERITIES = {"critical", "warning", "info"}


def validate_orchestrator_report(report: dict[str, Any]) -> list[str]:
    """
    Validates the structured report emitted by the orchestrator in Step 8.

    Returns a list of validation errors. Empty list means report is valid.

    Checks:
      - All required top-level fields present
      - Field types correct
      - status is a known value
      - tasks dict contains by_status sub-dict
      - Each issue has code, severity, detail fields
      - Each dispatched entry has task_id, worker_id, result fields
    """
    errors: list[str] = []

    for field, expected_type in _REPORT_REQUIRED_FIELDS.items():
        if field not in report:
            errors.append(f"missing field: {field!r}")
            continue
        if not isinstance(report[field], expected_type):
            errors.append(
                f"field {field!r}: expected {expected_type}, got {type(report[field]).__name__}"
            )

    status = report.get("status")
    if isinstance(status, str) and status not in _VALID_STATUSES:
        errors.append(f"status {status!r} not in {sorted(_VALID_STATUSES)}")

    tasks = report.get("tasks")
    if isinstance(tasks, dict) and "by_status" not in tasks:
        errors.append("tasks dict missing 'by_status' sub-key")

    for i, issue in enumerate(report.get("issues", [])):
        if not isinstance(issue, dict):
            errors.append(f"issues[{i}] is not a dict")
            continue
        for k in ("code", "severity", "detail"):
            if k not in issue:
                errors.append(f"issues[{i}] missing field {k!r}")
        sev = issue.get("severity")
        if isinstance(sev, str) and sev not in _VALID_SEVERITIES:
            errors.append(f"issues[{i}].severity {sev!r} not in {sorted(_VALID_SEVERITIES)}")

    for i, entry in enumerate(report.get("dispatched", [])):
        if not isinstance(entry, dict):
            errors.append(f"dispatched[{i}] is not a dict")
            continue
        for k in ("task_id", "worker_id", "result"):
            if k not in entry:
                errors.append(f"dispatched[{i}] missing field {k!r}")

    return errors


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    # Exceptions
    "OrchError",
    "LockTimeoutError",
    "EventValidationError",
    "CorruptedLogError",
    "IllegalTransition",
    "UnknownEventType",
    "BlobIntegrityError",
    "BlobNotFoundError",
    "ConfigError",
    "PreconditionViolation",
    # Paths and constants
    "ORCH_DIR", "LOG_PATH", "LOCK_PATH", "STATE_DIR", "DLQ_DIR",
    "AUDIT_DIR", "METRICS_DIR", "BLOBS_DIR", "WORKERS_DIR", "CONFIG_PATH",
    "MAX_INLINE_PAYLOAD", "LOCK_TIMEOUT_S", "SNAPSHOT_EVERY_N_EVENTS",
    # Helpers
    "ensure_dirs",
    "new_event_id",
    "now_iso",
    "parse_iso",
    "sha256_hex",
    "canonical_json",
    # Append-time preconditions (prod-hardening task 00)
    "register_precondition",
    "clear_preconditions",
    "last_event_where",
    "any_event_where",
    # Enums
    "EventType",
    "TaskStatus",
    "PhaseStatus",
    "Tier",
    # Dataclasses
    "Event",
    "TaskState",
    "PhaseState",
    "OrchState",
    # Locking
    "LogLock",
    # Verification
    "VerifyResult",
    "verify_chain",
    "verify_chain_cached",
    # Blob externalization
    "is_blob_ref",
    "externalize_blob",
    "load_blob_data",
    # Log I/O
    "append_event",
    "claim_task",
    "split_porcelain_by_allowlist",
    "scoped_phase_tasks",
    "read_events",
    "last_event",
    "read_events_filtered",
    # Reducer
    "apply_event",
    "reduce_all",
    "compute_progress",
    "stale_tasks",
    "stale_threshold_seconds",
    "worker_liveness_expired",
    "reap_stale_tasks",
    "slugify_workflow_id",
    "resolve_workflow_id",
    "consumed_manifest_ids",
    # Config and retry
    "default_config",
    "load_config",
    "RetryPolicy",
    "backoff_seconds",
    "load_retry_policy",
    "should_retry",
    "tasks_ready_for_retry",
    # Circuit breaker
    "evaluate_circuit_state",
    "trip_circuit_if_due",
    # Recovery
    "verify_and_recover",
    # Dependency helpers
    "get_orphaned_dep_ids",
    # Escalation detection
    "detect_dependency_cycle",
    "detect_deadlock",
    "detect_critical_dlq",
    # Worker registry
    "register_worker",
    "unregister_worker",
    "cleanup_stale_workers",
    "get_active_workers",
    # Report validation
    "validate_orchestrator_report",
    # Failure / skip reason enumerations
    "VALID_FAILURE_REASONS",
    "VALID_SKIP_REASONS",
    # State machine (sm-refactor)
    "Action",
    "StateMachine",
    "TEST_TRANSITIONS",
    "TestPhaseStateMachine",
    "META_TRANSITIONS",
    "MetaStateMachine",
    "DEV_TRANSITIONS",
    "DevStateMachine",
    "REVIEW_TRANSITIONS",
    "ReviewStateMachine",
    "SDD_TRANSITIONS",
    "SddStateMachine",
]


# Public aliases — orchestrators and workers should reference these to stay in sync
# with the validator. Adding a new reason: update the frozenset above.
VALID_FAILURE_REASONS: frozenset[str] = _VALID_FAILURE_REASONS
VALID_SKIP_REASONS: frozenset[str] = _VALID_SKIP_REASONS


# ---------------------------------------------------------------------------
# State Machine — pure-function routing decisions
# ---------------------------------------------------------------------------
# Orchestrators delegate all conditional routing to a StateMachine in this module.
# Transition tables are dicts where each key is (state_str, predicate_fn) and the
# value is the Action returned when the predicate matches. First match (in dict
# insertion order) wins. Predicate signature: (inputs: dict) -> bool. If the
# predicate raises (KeyError, TypeError, AttributeError), the transition is
# silently skipped — protects against missing input fields.
#
# CLI entry point: dist/.claude/lib/sm_runner.py.

@dataclass
class Action:
    """A routing decision produced by a StateMachine.

    `name` is the action identifier consumed by the orchestrator.
    `params` carries any data the orchestrator needs to execute the action.
    """
    name: str
    params: dict[str, Any] = field(default_factory=dict)


class StateMachine:
    """Pure-function state machine: (state, inputs) -> Action.

    Transitions are evaluated in dict insertion order; first matching predicate
    wins. Predicates that raise are skipped (treated as non-match). When no
    transition matches, returns Action("no_match", {...diagnostic info}).
    """

    def __init__(self, transitions: dict[tuple[str, Callable[[dict], bool]], Action]):
        self._transitions = transitions

    def evaluate(self, state: str, inputs: dict) -> Action:
        for (st, pred), action in self._transitions.items():
            if st != state:
                continue
            try:
                matched = pred(inputs)
            except (KeyError, TypeError, AttributeError):
                continue
            if matched:
                return action
        return Action(
            "no_match",
            {"state": state, "inputs_keys": sorted(inputs.keys())},
        )


# ---------------------------------------------------------------------------
# orchestrator-test transitions (T1-T4)
# ---------------------------------------------------------------------------

TEST_TRANSITIONS: dict[tuple[str, Callable[[dict], bool]], Action] = {
    # T1 — nesting depth guard
    ("entry", lambda i: i.get("nesting_depth", 0) >= 3):
        Action("block", {"reason": "nesting_depth_exceeded", "code": "blocked"}),
    ("entry", lambda i: True):
        Action("proceed", {"to": "infra_check"}),

    # T2 — state reduction E12
    ("post_infra", lambda i: i.get("reduce_exit_code") == 1):
        Action(
            "escalate_e12",
            {"code": "E12_state_reduction_failed", "severity": "critical"},
        ),
    ("post_infra", lambda i: True):
        Action("proceed", {"to": "step_2_state"}),

    # T3 — no delivery artifacts gate
    ("post_state", lambda i: i.get("dev_completed_tasks_with_delivery", 0) == 0):
        Action(
            "block",
            {"reason": "no_delivery_artifacts", "needs": "dev_phase_complete"},
        ),
    ("post_state", lambda i: True):
        Action("proceed", {"to": "step_3_task_creation"}),

    # T4 — stack worker routing (dynamic params populated by TestPhaseStateMachine)
    (
        "dispatch",
        lambda i: i.get("task_type") and i.get("stack") in ("be", "fe", "fullstack"),
    ):
        Action("select_worker", {}),

    # A6-F2 (task 09): batch ceiling in Python (mirror REVIEW R9).
    ("select_batch", lambda i: True):
        Action("set_max_concurrent", {"max_concurrent": 2}),
}


class TestPhaseStateMachine(StateMachine):
    """Subclass for orchestrator-test that populates T4's dynamic params."""

    __test__ = False  # exclude from pytest collection (class name starts with 'Test')

    def evaluate(self, state: str, inputs: dict) -> Action:
        action = super().evaluate(state, inputs)
        if state == "dispatch" and action.name == "select_worker":
            return Action(
                "select_worker",
                {
                    "task_type": inputs.get("task_type"),
                    "stack": inputs.get("stack"),
                },
            )
        return action


# ---------------------------------------------------------------------------
# meta-orchestrator transitions (M1, M2, M3, M9)
# ---------------------------------------------------------------------------

def _m3_derive_run_status(inputs: dict) -> str:
    """M3 — derive run_status from raw_run_status + phases[]."""
    raw = inputs.get("raw_run_status")
    if raw == "escalated":
        return "escalated"
    phases = inputs.get("phases") or []
    required = [p for p in phases if p.get("required")]
    if required and all(p.get("status") == "completed" for p in required):
        return "completed"
    if not phases:
        return "pending"
    return "active"


META_TRANSITIONS: dict[tuple[str, Callable[[dict], bool]], Action] = {
    # M1 — infra check gate
    ("post_infra", lambda i: i.get("preflight_status") == "blocked"):
        Action("block", {"reason": "preflight_failed"}),
    ("post_infra", lambda i: i.get("integrity_status") == "blocked"):
        Action("block", {"reason": "integrity_failed"}),
    ("post_infra", lambda i: i.get("circuit_status") == "blocked"):
        Action("block", {"reason": "circuit_failed"}),
    ("post_infra", lambda i: True):
        Action("proceed", {"to": "step_2_state"}),

    # M2 — state derivation error
    ("post_state", lambda i: i.get("reduce_status") == "error"):
        Action("error", {"reason": "state_derivation_failed", "source": "reduce.py"}),
    ("post_state", lambda i: i.get("current_phase_status") == "error"):
        Action(
            "error",
            {"reason": "state_derivation_failed", "source": "current_phase.py"},
        ),
    ("post_state", lambda i: True):
        Action("proceed", {"to": "step_3_terminal"}),

    # M3 — run_status derivation (params populated by MetaStateMachine wrapper)
    ("derive_run_status", lambda i: True):
        Action("set_run_status", {}),

    # M9 — E13 retry escalation
    ("subagent_invalid", lambda i: i.get("e13_retry_count", 0) == 0):
        Action(
            "retry_with_backoff",
            {"backoff_seconds": 30, "severity": "warning", "code": "E13"},
        ),
    ("subagent_invalid", lambda i: i.get("e13_retry_count", 0) == 1):
        Action(
            "retry_with_backoff",
            {"backoff_seconds": 60, "severity": "warning", "code": "E13"},
        ),
    ("subagent_invalid", lambda i: i.get("e13_retry_count", 0) >= 2):
        Action(
            "escalate_critical",
            {"severity": "critical", "code": "E13"},
        ),

    # M5 — Escalation decision gate
    (
        "escalation_active",
        lambda i: i.get("escalation_severity") == "info"
                  and bool(i.get("escalation_options")),
    ):
        Action("ask_user", {}),  # options populated by MetaStateMachine wrapper
    ("escalation_active", lambda i: True):
        Action("surface_error", {}),

    # M7 — Phase routing
    ("phase_entry", lambda i: i.get("current_phase") == "sdd"):
        Action("spawn_phase_orchestrator", {"subagent_type": "orchestrator-sdd"}),
    ("phase_entry", lambda i: i.get("current_phase") == "dev"):
        Action("spawn_phase_orchestrator", {"subagent_type": "orchestrator-dev"}),
    ("phase_entry", lambda i: i.get("current_phase") == "review"):
        Action("spawn_phase_orchestrator", {"subagent_type": "orchestrator-review"}),
    ("phase_entry", lambda i: i.get("current_phase") == "test"):
        Action("spawn_phase_orchestrator", {"subagent_type": "orchestrator-test"}),
    # Terminal marker: "done" is the to_phase of the final phase_transitioned
    # (orchestrator-test exit). It is never a dispatchable phase — re-entering
    # phase routing with it means the workflow already completed.
    ("phase_entry", lambda i: i.get("current_phase") == "done"):
        Action("workflow_complete", {}),
    ("phase_entry", lambda i: True):
        Action("error", {"reason": "unknown_phase"}),  # phase populated by wrapper
}


class MetaStateMachine(StateMachine):
    """Subclass for the meta-orchestrator that populates dynamic params."""

    def evaluate(self, state: str, inputs: dict) -> Action:
        action = super().evaluate(state, inputs)
        if state == "derive_run_status" and action.name == "set_run_status":
            return Action(
                "set_run_status",
                {"run_status": _m3_derive_run_status(inputs)},
            )
        if state == "escalation_active" and action.name == "ask_user":
            return Action(
                "ask_user",
                {"options": list(inputs.get("escalation_options", []))},
            )
        if state == "phase_entry" and action.name == "error":
            return Action(
                "error",
                {
                    "reason": "unknown_phase",
                    "phase": inputs.get("current_phase"),
                },
            )
        return action


# ---------------------------------------------------------------------------
# orchestrator-dev transitions (D6, D7)
# ---------------------------------------------------------------------------

DEV_TRANSITIONS: dict[tuple[str, Callable[[dict], bool]], Action] = {
    # D6 — dev_impact: no_action short-circuit
    (
        "post_manifest",
        lambda i: i.get("handoff_type") in ("fast_track", "major_evolution")
                  and i.get("dev_impact") == "no_action",
    ):
        Action(
            "exit_vacuous",
            {
                "next_phase": "review",
                "reason": "dev_impact_no_action",
                "criteria_vacuously_met": True,
            },
        ),
    ("post_manifest", lambda i: True):
        Action("proceed", {"to": "step_3_planning"}),

    # D7 — planner_required skip in improve flow
    # Most specific predicate must come first (escalate when triage missing).
    (
        "planning_dispatch",
        lambda i: i.get("workflow_type") == "improve"
                  and i.get("planner_required") is False
                  and not i.get("triage_present", False),
    ):
        Action(
            "escalate_e13",
            {
                "code": "E13_improve_scope_unusable",
                "severity": "critical",
                "reason": "triage_missing — cannot synthesize backlog without triage.json",
            },
        ),
    (
        "planning_dispatch",
        lambda i: i.get("workflow_type") == "improve"
                  and i.get("planner_required") is False,
    ):
        Action(
            "synthesize_backlog_from_triage",
            {
                "skip_planner": True,
                "reason": "implementation_only_no_spec_change",
            },
        ),
    ("planning_dispatch", lambda i: True):
        Action("dispatch_planner", {}),

    # D8 — Stack-conditional planning dispatch
    ("dispatch_planner_stack", lambda i: i.get("stack") == "fullstack"):
        Action(
            "dispatch_parallel_planners",
            {
                "workers": ["u-be-planner", "u-fe-planner"],
                # tasks are namespaced by the DevStateMachine wrapper when the
                # orchestrator passes workflow_id (5-a); this static value is the
                # legacy fallback for callers that do not.
                "tasks": ["dev_planning_be", "dev_planning_fe"],
            },
        ),
    ("dispatch_planner_stack", lambda i: i.get("stack") == "be"):
        Action("dispatch_single_planner", {"stack": "be", "worker": "u-be-planner"}),
    ("dispatch_planner_stack", lambda i: i.get("stack") == "fe"):
        Action("dispatch_single_planner", {"stack": "fe", "worker": "u-fe-planner"}),
    ("dispatch_planner_stack", lambda i: True):
        Action("error", {"reason": "unknown_stack"}),  # stack populated by wrapper

    # D9 — Stack propagation per task (params populated by DevStateMachine wrapper)
    (
        "dispatch_impl_task",
        lambda i: i.get("task_stack") in ("be", "fe")
                  or i.get("project_stack") in ("be", "fe"),
    ):
        Action("select_worker", {}),
    ("dispatch_impl_task", lambda i: True):
        Action("error", {"reason": "no_resolvable_stack"}),

    # A6-F2 (task 09): per-phase batch ceiling in Python (mirror REVIEW R9) — the
    # concurrency cap is returned by the SM, not a prose literal in the prompt.
    ("select_batch", lambda i: True):
        Action("set_max_concurrent", {"max_concurrent": 2}),
}


def _dev_max_concurrent(dispatch_policy: dict[str, Any]) -> int:
    """SIEGARD-02 — config-driven dev batch ceiling. Pure: reads the policy dict
    passed in the SM inputs (the orchestrator loads it via load_config). Falls back
    to 2 on missing/invalid value; clamps to >= 1."""
    try:
        v = int((dispatch_policy or {}).get("dev", {}).get("max_concurrent", 2))
    except (TypeError, ValueError, AttributeError):
        return 2
    return v if v >= 1 else 2


class DevStateMachine(StateMachine):
    """Subclass for orchestrator-dev that populates dynamic params for D8/D9."""

    def evaluate(self, state: str, inputs: dict) -> Action:
        action = super().evaluate(state, inputs)
        # 5-a: task IDs are namespaced by workflow so a shared log never
        # collides across workflows (dev_{workflow_id}_planning_be/fe).
        # Without workflow_id in inputs the legacy un-namespaced ids stand.
        if state == "dispatch_planner_stack" and action.name == "dispatch_parallel_planners":
            wf = inputs.get("workflow_id")
            if wf:
                return Action(
                    "dispatch_parallel_planners",
                    {
                        "workers": action.params["workers"],
                        "tasks": [f"dev_{wf}_planning_be", f"dev_{wf}_planning_fe"],
                    },
                )
        if state == "dispatch_planner_stack" and action.name == "error":
            return Action(
                "error",
                {"reason": "unknown_stack", "stack": inputs.get("stack")},
            )
        if state == "dispatch_impl_task" and action.name == "select_worker":
            ts = inputs.get("task_stack")
            stack = ts if ts in ("be", "fe") else inputs.get("project_stack")
            return Action(
                "select_worker",
                {"stack": stack, "task_type": inputs.get("task_type")},
            )
        # SIEGARD-02: config-driven batch ceiling (mirrors REVIEW R9). The table's
        # set_max_concurrent default (2) is overridden by dispatch_policy.dev when
        # the orchestrator passes it in inputs; absent/invalid → unchanged (2).
        if state == "select_batch" and action.name == "set_max_concurrent":
            return Action(
                "set_max_concurrent",
                {"max_concurrent": _dev_max_concurrent(inputs.get("dispatch_policy", {}))},
            )
        return action


# ---------------------------------------------------------------------------
# orchestrator-review transitions (R4, R9)
# ---------------------------------------------------------------------------

QA_MODE_CONCURRENCY: dict[str, int] = {
    "micro": 5,
    "standard": 3,
    "full": 2,
    "unknown": 2,
}


def _r9_compute_max_concurrent(qa_modes: list[str]) -> int:
    """R9 — min CONCURRENCY across qa_modes_in_window (defaults 2 for empty/unknown)."""
    if not qa_modes:
        return 2
    return min(QA_MODE_CONCURRENCY.get(m, 2) for m in qa_modes)


REVIEW_TRANSITIONS: dict[tuple[str, Callable[[dict], bool]], Action] = {
    # R4 — qa_mode classification routing
    # Most specific first: classifier_failed forces standard fallback.
    ("classify_qa_mode_done", lambda i: i.get("classifier_failed")):
        Action(
            "create_qa_task",
            {
                "qa_mode": "standard",
                "concurrency_hint": 3,
                "warn_emitted": True,
                "code": "E19_qa_mode_classifier_failed",
            },
        ),
    ("classify_qa_mode_done", lambda i: i.get("qa_mode") in QA_MODE_CONCURRENCY):
        Action("create_qa_task", {}),  # populated by ReviewStateMachine wrapper

    # R9 — Dynamic concurrency by qa_mode window
    ("select_batch", lambda i: True):
        Action("set_max_concurrent", {}),  # populated by wrapper

    # R10 — Auto-approval gate (4 strict rules, most specific failure first)
    # prod-hardening task 02 (C2/A4-F2): bind the SM to the script's own `qualifies`
    # verdict. When the orchestrator passes qualifies=False (script exit!=0), short-
    # circuit to the manual gate — do not trust LLM-retyped booleans. R1-R4 below
    # remain as defense-in-depth for the positive path.
    ("approval_gate", lambda i: i.get("qualifies") is False):
        Action("manual_gate", {"disqualified_by": "script_qualifies_false"}),
    ("approval_gate", lambda i: i.get("completed_review_tasks_count", 0) == 0):
        Action("manual_gate", {"disqualified_by": "R1_no_completed_tasks"}),
    ("approval_gate", lambda i: not i.get("all_qa_mode_micro")):
        Action("manual_gate", {"disqualified_by": "R2_non_micro_qa_mode"}),
    ("approval_gate", lambda i: not i.get("all_verdicts_approved")):
        Action("manual_gate", {"disqualified_by": "R3_verdict_not_approved"}),
    ("approval_gate", lambda i: i.get("any_severe_findings")):
        Action("manual_gate", {"disqualified_by": "R4_severe_findings_present"}),
    ("approval_gate", lambda i: True):
        Action(
            "auto_approve",
            {
                "synthesized_human_response": True,
                "auto_approved": True,
                "reason": "micro_unanimous_clean",
                "audit_code": "E18_auto_approval_granted",
            },
        ),

    # R11 — human_response.action routing
    ("human_response_received", lambda i: i.get("action") == "approve"):
        Action("proceed_to_exit", {}),
    ("human_response_received", lambda i: i.get("action") == "return_to_dev"):
        Action("return_to_dev", {"scope": "full"}),
    ("human_response_received", lambda i: i.get("action") == "return_partial"):
        Action("return_to_dev", {"scope": "partial"}),  # rejected_task_ids dyn
    ("human_response_received", lambda i: True):
        Action("error", {"reason": "unknown_action"}),  # received populated by wrapper
}


class ReviewStateMachine(StateMachine):
    """Subclass for orchestrator-review that populates dynamic params for R4/R9/R11."""

    def evaluate(self, state: str, inputs: dict) -> Action:
        action = super().evaluate(state, inputs)
        if (
            state == "classify_qa_mode_done"
            and action.name == "create_qa_task"
            and not action.params.get("warn_emitted")
        ):
            mode = inputs.get("qa_mode", "standard")
            return Action(
                "create_qa_task",
                {
                    "qa_mode": mode,
                    "concurrency_hint": QA_MODE_CONCURRENCY.get(mode, 2),
                    "rationale": inputs.get("rationale", ""),
                },
            )
        if state == "select_batch" and action.name == "set_max_concurrent":
            modes = inputs.get("qa_modes_in_window", [])
            return Action(
                "set_max_concurrent",
                {"max_concurrent": _r9_compute_max_concurrent(modes)},
            )
        if (
            state == "human_response_received"
            and action.name == "return_to_dev"
            and action.params.get("scope") == "partial"
        ):
            return Action(
                "return_to_dev",
                {
                    "scope": "partial",
                    "rejected_task_ids": list(inputs.get("rejected_task_ids", [])),
                },
            )
        if state == "human_response_received" and action.name == "error":
            return Action(
                "error",
                {
                    "reason": "unknown_action",
                    "received": inputs.get("action"),
                },
            )
        return action


# ---------------------------------------------------------------------------
# orchestrator-sdd transitions (S4-S8)
# ---------------------------------------------------------------------------

def _s10_classify_path(path: str) -> str:
    """S10 — heuristic mapping path keyword → domain_task_type."""
    p = (path or "").lower()
    if "front/" in p or "component" in p:
        return "spec-front"
    if "back/" in p or p.endswith(".back.md"):
        return "spec-back"
    if "domains/" in p:
        return "spec-back"  # openapi.yaml + .spec.md default to back
    return "spec-front"  # ambiguous → front (UI improvements default)


SDD_TRANSITIONS: dict[tuple[str, Callable[[dict], bool]], Action] = {
    # S4 — type=implementation_only short-circuit (most specific first)
    ("triage_done", lambda i: i.get("type") == "implementation_only"):
        Action(
            "exit_no_spec_change",
            {"next_phase": "dev", "reason": "implementation_only_no_spec_change"},
        ),

    # S5 + S6 — effective_mode + bypass_e99 (combined per trigger × mode_hint)
    (
        "triage_done",
        lambda i: i.get("trigger") == "u-improve" and i.get("mode_hint") == "full",
    ):
        Action(
            "dispatch_pipeline",
            {"effective_mode": "standard", "bypass_e99": True},
        ),
    (
        "triage_done",
        lambda i: i.get("trigger") == "u-improve"
                  and isinstance(i.get("mode_hint"), str)
                  and i.get("mode_hint", "").startswith("fast-track"),
    ):
        Action(
            "dispatch_pipeline",
            {"effective_mode": "targeted", "bypass_e99": True},
        ),
    ("triage_done", lambda i: i.get("trigger") == "u-spec"):
        Action(
            "dispatch_pipeline",
            {"effective_mode": "standard", "bypass_e99": False},
        ),

    # S7 — Targeted vs Standard branch
    ("post_mode_declared", lambda i: i.get("effective_mode") == "targeted"):
        Action("goto_step", {"step": "step_4_targeted"}),
    ("post_mode_declared", lambda i: i.get("effective_mode") == "standard"):
        Action("goto_step", {"step": "step_2_assess"}),

    # S8 — Greenfield routing (params populated by SddStateMachine wrapper)
    ("assess_pipeline", lambda i: i.get("greenfield") is True):
        Action("use_triage_domains", {}),
    ("assess_pipeline", lambda i: i.get("greenfield") is False):
        Action("scan_filesystem", {}),

    # S10 — Domain worker type by path keyword (params populated by wrapper)
    ("targeted_classify_path", lambda i: True):
        Action("set_domain_worker_type", {}),

    # S11 — Structural diff routing
    ("targeted_dispatch_decision", lambda i: i.get("domain_worker_required") is True):
        Action("create_writer_and_reviewer", {}),  # pipeline populated by wrapper
    ("targeted_dispatch_decision", lambda i: i.get("domain_worker_required") is False):
        Action("create_reviewer_only", {"pipeline": ["spec-reviewer"]}),

    # S16 — Validation Repair Loop (most specific first: dispatch only if all conditions met)
    (
        "exit_criteria_failed",
        lambda i: i.get("effective_mode") == "standard"
                  and i.get("repair_cycles", 0) < 2
                  and len(i.get("invalid_domains", [])) > 0,
    ):
        Action("dispatch_repair_pipeline", {}),  # cycle_n + domains populated by wrapper
    ("exit_criteria_failed", lambda i: True):
        Action("escalate_e08", {}),  # reason populated by wrapper

    # A6-F2 (task 09): batch ceiling — standard=2 / targeted=1 (populated by wrapper).
    ("select_batch", lambda i: True):
        Action("set_max_concurrent", {}),
}


class SddStateMachine(StateMachine):
    """Subclass for orchestrator-sdd that populates dynamic params for S8/S10/S11/S16."""

    def evaluate(self, state: str, inputs: dict) -> Action:
        action = super().evaluate(state, inputs)
        if state == "assess_pipeline" and action.name == "use_triage_domains":
            return Action(
                "use_triage_domains",
                {"domains": list(inputs.get("triage_domains", []))},
            )
        if state == "targeted_classify_path" and action.name == "set_domain_worker_type":
            path = inputs.get("spec_path", "") or ""
            return Action(
                "set_domain_worker_type",
                {
                    "domain_task_type": _s10_classify_path(path),
                    "spec_path": path,
                },
            )
        if (
            state == "targeted_dispatch_decision"
            and action.name == "create_writer_and_reviewer"
        ):
            dtt = inputs.get("domain_task_type", "spec-front")
            return Action(
                "create_writer_and_reviewer",
                {"pipeline": [dtt, "spec-reviewer"], "domain_task_type": dtt},
            )
        if state == "exit_criteria_failed" and action.name == "dispatch_repair_pipeline":
            cycles = int(inputs.get("repair_cycles", 0))
            domains = list(inputs.get("invalid_domains", []))
            # Stage-granular repair (conservative). defect_origins maps each
            # INVALID domain to the pipeline stage its blocking issues point at
            # (derived from validation-result.yaml `responsible` fields by
            # identify_invalid_domains.py). Only the unambiguous back-only case
            # gets a reduced pipeline — earlier-stage artifacts were approved
            # and are reused as inputs, not regenerated. ANY other origin
            # (writer, front, mixed, missing, unparseable) falls back to the
            # full pipeline: mis-attribution must degrade to redundant work,
            # never to an under-repair loop.
            origins = inputs.get("defect_origins") or {}
            full = ["spec-writer", "spec-reviewer", "spec-back", "spec-validator"]
            reduced = {"back": ["spec-back", "spec-validator"]}
            pipelines = {
                d: reduced.get(origins.get(d), full) for d in domains
            }
            return Action(
                "dispatch_repair_pipeline",
                {
                    "repair_cycle_n": cycles + 1,
                    "domains": domains,
                    "pipeline": full,
                    "pipelines": pipelines,
                },
            )
        if state == "exit_criteria_failed" and action.name == "escalate_e08":
            cycles = int(inputs.get("repair_cycles", 0))
            invalid = inputs.get("invalid_domains", []) or []
            mode = inputs.get("effective_mode")
            if cycles >= 2:
                reason = "max_repair_cycles_reached"
            elif not invalid:
                reason = "no_repairable_invalid_domains"
            elif mode != "standard":
                reason = "non_standard_mode"
            else:
                reason = "exit_criteria_not_met"
            return Action(
                "escalate_e08",
                {
                    "code": "E08_exit_criteria_not_met",
                    "severity": "warning",
                    "repair_cycles_attempted": cycles,
                    "reason": reason,
                },
            )
        if state == "select_batch" and action.name == "set_max_concurrent":
            mode = inputs.get("effective_mode")
            return Action(
                "set_max_concurrent",
                {"max_concurrent": 1 if mode == "targeted" else 2},
            )
        return action


# ---------------------------------------------------------------------------
# Import-time enforcement install (prod-hardening)
# ---------------------------------------------------------------------------
# dist/ always enforces these guards. Reloading the module (tests) re-installs
# them idempotently. Task 01: phase-transition gate + human-approval gate.
install_transition_preconditions()
