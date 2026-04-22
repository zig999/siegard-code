# API Reference — `orch_core.py`

Location: `.claude/lib/orch_core.py`
Language: Python 3.10+, stdlib only, zero external dependencies.

Import pattern:
```python
import sys
sys.path.insert(0, ".claude/lib")
import orch_core
from orch_core import append_event, reduce_all, OrchState
```

---

## Constants & Paths

```python
ORCH_DIR    = Path(".orch")
LOG_PATH    = ORCH_DIR / "log.jsonl"
LOCK_PATH   = ORCH_DIR / "log.jsonl.lock"
STATE_DIR   = ORCH_DIR / "state"
BLOBS_DIR   = ORCH_DIR / "blobs"
DLQ_DIR     = ORCH_DIR / "dlq"
METRICS_DIR = ORCH_DIR / "metrics"

MAX_INLINE_PAYLOAD   = 3500   # bytes; larger payloads externalized to blobs
LOCK_TIMEOUT_S       = 10.0
SNAPSHOT_EVERY_N     = 100    # events between snapshots
```

All paths are resolved relative to `ORCH_PROJECT_DIR` env var if set; otherwise relative to CWD.

---

## Enumerations

### `EventType`

```python
class EventType(str, Enum):
    # Task lifecycle
    TASK_CREATED          = "task_created"
    TASK_CLAIMED          = "task_claimed"
    TASK_PROGRESS         = "task_progress"
    TASK_COMPLETED        = "task_completed"
    TASK_FAILED           = "task_failed"
    TASK_SCHEDULED_RETRY  = "task_scheduled_retry"
    TASK_RETRIED          = "task_retried"
    TASK_DLQ              = "task_dlq"
    # Phase lifecycle
    PHASE_DECLARED            = "phase_declared"
    PHASE_ENTERED             = "phase_entered"
    PHASE_EXIT_CRITERION_MET  = "phase_exit_criterion_met"
    PHASE_EXIT_APPROVED       = "phase_exit_approved"
    PHASE_TRANSITIONED        = "phase_transitioned"
    PHASE_PAUSED              = "phase_paused"
    PHASE_RESUMED             = "phase_resumed"
    # Management
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    ESCALATION              = "escalation"
    HUMAN_RESPONSE          = "human_response"
    SNAPSHOT                = "snapshot"
    LOG_RECOVERED           = "log_recovered"
    PREFLIGHT_FAILED        = "preflight_failed"

    @classmethod
    def is_worker_emittable(cls, event_type: str) -> bool:
        """True only for task_progress, task_completed, task_failed."""
```

### `TaskStatus`

```python
class TaskStatus(str, Enum):
    PENDING    = "pending"
    READY      = "ready"
    RUNNING    = "running"
    SCHEDULED  = "scheduled"   # backoff scheduled
    COMPLETED  = "completed"
    FAILED     = "failed"
    DLQ        = "dlq"
    CANCELLED  = "cancelled"
```

### `PhaseStatus`

```python
class PhaseStatus(str, Enum):
    PENDING       = "pending"
    ACTIVE        = "active"
    EXIT_APPROVED = "exit_approved"
    COMPLETED     = "completed"
    PAUSED        = "paused"
```

### `Tier`

```python
class Tier(str, Enum):
    CRITICAL = "critical"
    STANDARD = "standard"
    BULK     = "bulk"

    @property
    def default_max_attempts(self) -> int: ...
    @property
    def default_stale_seconds(self) -> int: ...
    @property
    def default_base_delay_s(self) -> float: ...
```

---

## Dataclasses

### `Event`

```python
@dataclass
class Event:
    seq:        int
    event_id:   str          # "evt_..." prefix + 26-char base32
    ts:         str          # ISO 8601 UTC ms
    agent:      str
    event_type: str
    task_id:    str | None
    attempt:    int          # minimum 1
    data:       dict[str, Any]
    prev_hash:  str          # "GENESIS" or hex64
    hash:       str          # hex64

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event": ...
    def canonical_json(self) -> str:
        """Sorted keys, no whitespace, hash field excluded."""
    def compute_hash(self) -> str:
        """SHA-256 of canonical_json(). Must match self.hash."""
```

### `TaskState`

```python
@dataclass
class TaskState:
    task_id:                str
    phase:                  str
    status:                 TaskStatus
    deps:                   list[str]
    tier:                   str
    task_type:              str
    spec:                   str
    attempts:               int
    max_attempts:           int
    worker_id:              str | None
    artifacts:              list[str]
    last_error:             str | None
    last_failure_reason:    str | None
    last_failure_retryable: bool | None
    next_retry_at:          str | None
    claimed_at:             str | None
    last_event_at:          str | None
    failed_at:              str | None

    @classmethod
    def from_dict(cls, d: dict) -> "TaskState":
        """Raises ValueError with context if status is not a valid TaskStatus."""
```

### `PhaseState`

```python
@dataclass
class PhaseState:
    name:         str
    order:        int
    required:     bool
    status:       PhaseStatus
    entered_at:   str | None
    approved_at:  str | None
    completed_at: str | None
    paused_at:    str | None
    criteria_met: list[str]
    pause_reason: str | None
```

### `OrchState`

```python
@dataclass
class OrchState:
    workflow_id:        str | None
    run_status:         str   # "active" | "escalated" | "completed" | "degraded"
    current_phase:      str | None
    tasks:              dict[str, TaskState]
    phases:             dict[str, PhaseState]
    escalation:         dict | None
    circuit_breaker:    dict | None
    last_seq:           int
    last_snapshot_seq:  int

    def tasks_by_status(self, status: str) -> list[TaskState]: ...
    def tasks_by_phase(self, phase: str) -> list[TaskState]: ...
    def ready_tasks(self) -> list[TaskState]: ...
```

### `VerifyResult`

```python
@dataclass
class VerifyResult:
    ok:                  bool
    message:             str
    mode:                str   # "strict" | "audit"
    events_verified:     int
    first_error_seq:     int | None
    error_details:       list[dict]
    truncation_candidate: dict | None
```

### `RetryPolicy`

```python
@dataclass
class RetryPolicy:
    max_attempts:  int
    base_delay_s:  float
    cap_s:         float

    @classmethod
    def for_tier(cls, tier: str, config: dict) -> "RetryPolicy": ...
    @classmethod
    def for_task(cls, task_type: str, tier: str, config: dict) -> "RetryPolicy": ...
```

---

## Exceptions

All inherit from `OrchError(Exception)`:

| Exception | Raised when |
|-----------|------------|
| `EventValidationError` | Event data fails schema validation |
| `CorruptedLogError` | Hash chain broken at a non-final line |
| `IllegalTransition` | Invalid task or phase state transition |
| `UnknownEventType` | Unrecognized `event_type` string |
| `BlobIntegrityError` | Blob `_blob_hash` does not match file content |
| `BlobNotFoundError` | Blob file referenced in event is missing |
| `LockTimeoutError` | `flock` acquisition timed out (also a `TimeoutError`) |
| `ConfigError` | `.orch/config.json` malformed |

---

## Setup

```python
def ensure_dirs() -> None:
    """Create .orch/ and all subdirectories. Idempotent."""
```

---

## I/O Functions

```python
def append_event(
    agent:      str,
    event_type: str,
    task_id:    str | None = None,
    attempt:    int = 1,
    data:       dict | None = None,
) -> Event:
    """
    Atomically append event with hash chain, flock, and schema validation.
    
    Raises:
      ValueError             — invalid event_type
      EventValidationError   — data fails schema
      LockTimeoutError       — lock acquisition timeout
      OSError                — filesystem errors
    """

def read_events(from_seq: int = 0) -> Iterator[Event]:
    """
    Yield events in seq order starting from from_seq.
    Silently ignores truncated final line.
    Raises CorruptedLogError on mid-log corruption.
    """

def last_event() -> Event | None:
    """Efficient read of the last event. Returns None if log is empty."""

def read_events_filtered(
    from_seq:   int = 0,
    task_id:    str | None = None,
    event_type: str | None = None,
    phase:      str | None = None,
    tail:       int | None = None,
) -> list[Event]:
    """
    All filters are AND-combined.
    tail: return last N events after applying all filters.
    """
```

---

## Verification & Recovery

```python
def verify_chain(mode: Literal["strict", "audit"] = "strict") -> VerifyResult:
    """
    Verify SHA-256 hash chain integrity.
    
    strict: stops at first error, exit 1.
    audit:  collects all errors, always returns ok=False if errors found.
    
    Note: recovery requires verify_and_recover(), not this function.
    """

def verify_and_recover(
    from_seq:  int,
    operator:  str,
    confirm:   bool = False,
) -> Event:
    """
    Truncate log at from_seq, archive corrupt tail, emit log_recovered.
    
    confirm=True required (never automatic).
    Returns the log_recovered Event on success.
    
    Raises:
      ValueError          — confirm=False, or from_seq out of range
      FileNotFoundError   — log file not found
      OSError             — filesystem errors
    """
```

---

## Blob Functions

```python
def externalize_blob(data: dict, event_id: str) -> tuple[str, str]:
    """
    Write data to .orch/blobs/<event_id>.json.
    Returns (blob_path_relative_to_orch_dir, sha256_hex).
    """

def load_blob_data(event: Event) -> dict:
    """
    Return event.data, loading from blob if externalized.
    Verifies _blob_hash before returning.
    
    Raises:
      BlobNotFoundError    — blob file missing
      BlobIntegrityError   — hash mismatch (tampering detected)
    """

def is_blob_ref(data: dict) -> bool:
    """True if data has _blob_ref, _size, _blob_hash keys."""
```

---

## Reducer & State

```python
def apply_event(state: OrchState, event: Event) -> OrchState:
    """
    Pure function: apply single event to state, return updated state.
    Raises IllegalTransition on invalid state transitions.
    """

def reduce_all() -> OrchState:
    """
    O(N): replay all events from scratch.
    Use when no snapshot is available or after log recovery.
    """

def reduce_incremental() -> OrchState:
    """
    O(k): load latest snapshot + replay events since snapshot seq.
    Falls back to reduce_all() if no snapshot exists.
    Note: snapshots are deferred (task 1.8); currently always falls back.
    """

def current_phase(state: OrchState) -> PhaseState | None:
    """Return the active PhaseState, or None if no phase is active."""

def ready_tasks_in_active_phase(state: OrchState) -> list[TaskState]:
    """
    Tasks in READY status belonging to the current phase.
    Ordered: priority desc, seq asc (P5 deterministic ordering).
    """

def stale_tasks(state: OrchState, now_iso: str) -> list[TaskState]:
    """
    Running tasks whose (now - last_event_at) exceeds tier.stale_seconds.
    """

def tasks_ready_for_retry(state: OrchState, now_iso: str) -> list[TaskState]:
    """
    Scheduled tasks whose next_retry_at <= now.
    Tasks with malformed next_retry_at are treated as ready immediately.
    """

def get_orphaned_dep_ids(task: TaskState, state: OrchState) -> list[str]:
    """
    Return dep_ids that are not present in state.tasks.
    Used to detect dependency DLQ cascade after crash recovery.
    """
```

---

## Snapshot Functions

```python
def save_snapshot(state: OrchState) -> Path:
    """
    Persist state to .orch/state/snapshot-<seq>.json.
    Returns path of written file.
    """

def latest_snapshot() -> tuple[OrchState, int]:
    """
    Load most recent snapshot.
    Returns (OrchState(), 0) if no snapshot exists.
    """

def should_snapshot(state: OrchState) -> bool:
    """True if last_seq - last_snapshot_seq >= SNAPSHOT_EVERY_N."""
```

---

## Retry & Circuit Breaker

```python
def backoff_seconds(
    attempts:     int,
    base_delay_s: float = 30.0,
    cap_s:        float = 600.0,
    jitter_range: tuple[float, float] = (0.8, 1.2),
) -> float:
    """
    Exponential backoff: min(base × 2^(attempts-1), cap) × jitter.
    Deterministic calc then jitter (preserves reproducibility of core delay).
    """

def load_retry_policy(
    tier:      str,
    task_type: str | None = None,
) -> RetryPolicy:
    """
    Load from .orch/config.json.
    task_type override has precedence over tier defaults.
    """

def should_retry(task: TaskState, policy: RetryPolicy) -> bool:
    """
    False if task.last_failure_retryable=False.
    False if task.attempts >= policy.max_attempts.
    True otherwise.
    """

def evaluate_circuit_state(events: list[Event], config: dict) -> dict:
    """
    Count task_failed events in the rolling window.
    Returns:
      {"status": "ok" | "tripped", "failures_in_window": N, "window_minutes": M, ...}
    Timestamps that fail ISO parsing are skipped (treated as outside window).
    """
```

---

## Locking

```python
class LogLock:
    """
    Context manager for POSIX flock with configurable timeout.
    
    Usage:
        with LogLock():
            # exclusive access to log
    
    Raises LockTimeoutError if lock not acquired within timeout_s.
    """
    def __init__(
        self,
        lock_path: Path | None = None,
        timeout_s: float = LOCK_TIMEOUT_S,
    ): ...
```

---

## Helpers

```python
def new_event_id() -> str:
    """Return evt_<26-char base32>. Monotonically increasing, unique."""

def now_iso() -> str:
    """ISO 8601 UTC timestamp with millisecond precision."""

def sha256_hex(data: bytes) -> str:
    """SHA-256 hex digest."""

def canonical_json(obj: Any) -> str:
    """Sorted keys, no whitespace, deterministic across runs."""

def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    Load .orch/config.json, filling defaults for missing fields.
    Returns default_config() if file does not exist.
    """

def default_config() -> dict[str, Any]:
    """Full config with all defaults. See source for schema."""
```
