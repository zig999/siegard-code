"""
Orchestrator core library.

Event sourcing engine for multi-phase Claude Code workflow orchestration.
Zero external dependencies — Python 3.10+ stdlib only.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


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
    """Event would cause illegal state transition."""


class UnknownEventType(OrchError):
    """Event type not recognized."""


class BlobIntegrityError(OrchError):
    """Blob hash doesn't match _blob_hash (tampering detected)."""


class BlobNotFoundError(OrchError):
    """Blob file referenced by event doesn't exist."""


class ConfigError(OrchError):
    """Config file is missing, invalid, or has wrong schema."""


# ---------------------------------------------------------------------------
# Constants and paths
# ---------------------------------------------------------------------------

ORCH_DIR: Path = Path(".orch")
LOG_PATH: Path = ORCH_DIR / "log.jsonl"
LOCK_PATH: Path = ORCH_DIR / "log.jsonl.lock"
STATE_DIR: Path = ORCH_DIR / "state"
DLQ_DIR: Path = ORCH_DIR / "dlq"
AUDIT_DIR: Path = ORCH_DIR / "audit"
METRICS_DIR: Path = ORCH_DIR / "metrics"
BLOBS_DIR: Path = ORCH_DIR / "blobs"
CONFIG_PATH: Path = ORCH_DIR / "config.json"

MAX_INLINE_PAYLOAD: int = 3500
LOCK_TIMEOUT_S: float = 10.0
# Used by snapshots (Task 1.8 — deferred); kept for API compatibility.
SNAPSHOT_EVERY_N_EVENTS: int = 100


def ensure_dirs() -> None:
    """Creates all .orch/ subdirectories if missing. Idempotent."""
    for d in (ORCH_DIR, STATE_DIR, DLQ_DIR, AUDIT_DIR, METRICS_DIR, BLOBS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

class LogLock:
    """
    Exclusive POSIX lock on the log lock file.

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
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
            fcntl.flock(self._fd, fcntl.LOCK_UN)
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
    """Canonical event types. 21 total."""

    # Task lifecycle (8)
    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_SCHEDULED_RETRY = "task_scheduled_retry"
    TASK_RETRIED = "task_retried"
    TASK_DLQ = "task_dlq"

    # Phase lifecycle (7)
    PHASE_DECLARED = "phase_declared"
    PHASE_ENTERED = "phase_entered"
    PHASE_EXIT_CRITERION_MET = "phase_exit_criterion_met"
    PHASE_EXIT_APPROVED = "phase_exit_approved"
    PHASE_TRANSITIONED = "phase_transitioned"
    PHASE_PAUSED = "phase_paused"
    PHASE_RESUMED = "phase_resumed"

    # Management and operations (6)
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    ESCALATION = "escalation"
    HUMAN_RESPONSE = "human_response"
    SNAPSHOT = "snapshot"
    LOG_RECOVERED = "log_recovered"
    PREFLIGHT_FAILED = "preflight_failed"

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
    FAILED = "failed"
    DLQ = "dlq"
    CANCELLED = "cancelled"

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        # CANCELLED is reserved for future use; no handler produces it yet.
        return status in {cls.COMPLETED.value, cls.DLQ.value}


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
}

_REQUIRED_DATA_FIELDS: dict[str, set[str]] = {
    EventType.TASK_CREATED.value:              {"phase", "tier", "type", "spec", "deps"},
    EventType.TASK_CLAIMED.value:              {"phase", "worker_type", "worker_id"},
    EventType.TASK_PROGRESS.value:             {"phase", "note"},
    EventType.TASK_COMPLETED.value:            {"phase", "artifacts", "summary"},
    EventType.TASK_FAILED.value:               {"phase", "reason", "retryable"},
    EventType.TASK_SCHEDULED_RETRY.value:      {"phase", "next_retry_at", "backoff_seconds", "previous_failure_seq"},
    EventType.TASK_RETRIED.value:              {"phase", "previous_attempt", "scheduled_retry_seq"},
    EventType.TASK_DLQ.value:                  {"phase", "reason", "last_error"},
    EventType.PHASE_DECLARED.value:            {"workflow_id", "phases"},
    EventType.PHASE_ENTERED.value:             {"phase", "order"},
    EventType.PHASE_EXIT_CRITERION_MET.value:  {"phase", "criterion"},
    EventType.PHASE_EXIT_APPROVED.value:       {"phase", "criteria_met", "next_phase"},
    EventType.PHASE_TRANSITIONED.value:        {"from_phase", "to_phase", "evidence_seq"},
    EventType.PHASE_PAUSED.value:              {"phase", "reason"},
    EventType.PHASE_RESUMED.value:             {"phase", "paused_seq"},
    EventType.ESCALATION.value:                {"code", "severity", "reason", "evidence"},
}


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

    _validate_event_data(event_type, data)

    ensure_dirs()

    with LogLock():
        last = last_event()
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

        line = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"

        with open(LOG_PATH, "ab") as f:
            f.write(line.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    return event


# ---------------------------------------------------------------------------
# Reducer — state dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TaskState:
    """Derived state for a single task."""
    task_id: str
    phase: str
    status: str
    deps: list[str]
    tier: str
    task_type: str
    spec: str
    attempts: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
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
        return cls(
            task_id=d["task_id"],
            phase=d["phase"],
            status=d["status"],
            deps=d.get("deps", []),
            tier=d["tier"],
            task_type=d["task_type"],
            spec=d.get("spec", ""),
            attempts=d.get("attempts", 0),
            max_attempts=d.get("max_attempts", 3),
            worker_id=d.get("worker_id"),
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
    """Returns True if all deps of task are completed."""
    return all(
        state.tasks.get(dep_id) is not None
        and state.tasks[dep_id].status == TaskStatus.COMPLETED
        for dep_id in task.deps
    )


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
    state.escalation = event.data


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
    if task.status != TaskStatus.READY:
        raise IllegalTransition(
            f"task_claimed: task {task_id!r} is {task.status!r}, expected ready"
        )
    task.status = TaskStatus.RUNNING
    task.worker_id = event.data.get("worker_id")
    task.claimed_at = event.ts
    task.last_event_at = event.ts
    task.evidence.append(event.seq)


def _handle_task_completed(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
    if task.status == TaskStatus.COMPLETED:
        # Duplicate terminal event — raise without mutating state further.
        raise IllegalTransition(
            f"task_completed: task {task_id!r} already completed (attempt {event.attempt})"
        )
    if task.status != TaskStatus.RUNNING:
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


def _handle_task_failed(state: OrchState, event: Event) -> None:
    task_id = event.task_id
    if task_id is None or task_id not in state.tasks:
        return
    task = state.tasks[task_id]
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
    # PENDING is allowed for cascade-from-dep: dep went to DLQ, so dependent
    # can never run and goes directly to DLQ without transitioning through FAILED.
    if task.status not in (TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.PENDING):
        raise IllegalTransition(
            f"task_dlq: task {task_id!r} is {task.status!r}, expected failed, running, or pending"
        )
    task.status = TaskStatus.DLQ
    task.last_event_at = event.ts
    task.evidence.append(event.seq)


def _handle_circuit_breaker_tripped(state: OrchState, event: Event) -> None:
    state.circuit_breaker = {"status": "tripped", **event.data}


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
    EventType.TASK_COMPLETED: _handle_task_completed,
    EventType.TASK_FAILED: _handle_task_failed,
    EventType.TASK_SCHEDULED_RETRY: _handle_task_scheduled_retry,
    EventType.TASK_RETRIED: _handle_task_retried,
    EventType.TASK_DLQ: _handle_task_dlq,
    EventType.ESCALATION: _handle_escalation,
    EventType.CIRCUIT_BREAKER_TRIPPED: _handle_circuit_breaker_tripped,
}


# ---------------------------------------------------------------------------
# Reducer — public API
# ---------------------------------------------------------------------------

def apply_event(state: OrchState, event: Event) -> OrchState:
    """
    Applies a single event to state, returning updated state.

    Mutates state in-place and returns it. deepcopy before calling if you
    need to preserve the original.

    Known event types with no reducer effect (e.g. task_progress, snapshot)
    are silently skipped — last_seq is still updated.

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
        finally:
            event.data = original_data

    state.last_seq = event.seq
    return state


def reduce_all() -> OrchState:
    """
    Builds state from scratch by replaying all events from log start.

    Raises:
        IllegalTransition: Log contains illegal transition.
        CorruptedLogError: Log is corrupted.
    """
    state = OrchState()
    for event in read_events():
        apply_event(state, event)
    return state


def stale_tasks(state: OrchState, now: str) -> list[TaskState]:
    """
    Returns tasks in `running` status whose last activity exceeds the tier's
    stale threshold.

    A task is stale when (now - last_event_at) > tier.default_stale_seconds.
    `last_event_at` is updated on every event for the task, including
    task_progress, so recent heartbeats reset the staleness timer.

    Args:
        state: Current OrchState (from reduce_all or reduce_incremental).
        now:   Current UTC time as ISO 8601 string (e.g. from now_iso()).

    Returns:
        List of TaskState objects that are stale. Empty list if none.
    """
    now_dt = parse_iso(now)
    result: list[TaskState] = []
    for task in state.tasks.values():
        if task.status != TaskStatus.RUNNING:
            continue
        if task.last_event_at is None:
            continue
        try:
            tier = Tier(task.tier)
        except ValueError:
            tier = Tier.STANDARD
        threshold = tier.default_stale_seconds
        last_dt = parse_iso(task.last_event_at)
        elapsed = (now_dt - last_dt).total_seconds()
        if elapsed > threshold:
            result.append(task)
    return result


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
        "circuit_breaker": {
            "enabled": True,
            "window_minutes": 10,
            "failure_threshold": 50,
            "scope": "workflow",
            "cooldown_minutes": 30,
            "reset_on_success_count": 5,
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
    # Deep-merge loaded over defaults (top-level keys only for simplicity)
    for key, val in loaded.items():
        if isinstance(val, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(val)
        else:
            cfg[key] = val
    return cfg


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
      - attempts >= policy.max_attempts → False (max exhausted)
      - otherwise → True
    """
    if task.last_failure_retryable is False:
        return False
    if task.attempts >= policy.max_attempts:
        return False
    return True


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
        if parse_iso(task.next_retry_at) <= now_dt:
            result.append(task)
    return result


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
    # Paths and constants
    "ORCH_DIR", "LOG_PATH", "LOCK_PATH", "STATE_DIR", "DLQ_DIR",
    "AUDIT_DIR", "METRICS_DIR", "BLOBS_DIR", "CONFIG_PATH",
    "MAX_INLINE_PAYLOAD", "LOCK_TIMEOUT_S", "SNAPSHOT_EVERY_N_EVENTS",
    # Helpers
    "ensure_dirs",
    "new_event_id",
    "now_iso",
    "parse_iso",
    "sha256_hex",
    "canonical_json",
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
    # Blob externalization
    "is_blob_ref",
    "externalize_blob",
    "load_blob_data",
    # Log I/O
    "append_event",
    "read_events",
    "last_event",
    "read_events_filtered",
    # Reducer
    "apply_event",
    "reduce_all",
    "stale_tasks",
    # Config and retry
    "default_config",
    "load_config",
    "RetryPolicy",
    "backoff_seconds",
    "load_retry_policy",
    "should_retry",
    "tasks_ready_for_retry",
]
