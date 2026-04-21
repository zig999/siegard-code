# `orch_core.py` — API Pública

> Spec de referência: assinatura formal de todas as funções, classes e exceções exportadas pelo módulo `orch_core`.
> Uso: contrato para quem implementa (garante compatibilidade) e para quem consome (garante uso correto).
> Localização: `.claude/lib/orch_core.py`.

---

## Princípios de design da API

1. **Stdlib pura**: nenhuma dependência externa. `fcntl`, `hashlib`, `json`, `uuid`, `dataclasses`.
2. **Funções puras onde possível**: reducer, validators, hash. Efeitos colaterais isolados em `append_event`.
3. **Exceções sobre retornos de erro**: operações que falham lançam exceção tipada, não retornam `None` ou `False`.
4. **Type hints completos**: toda API pública tem type hints verificáveis com mypy/pyright.
5. **Imutabilidade por convenção**: dataclasses são usadas como value objects; reducer retorna novo estado.
6. **Thread e process-safe**: `append_event` é safe para chamadas concorrentes.

---

## Sumário

1. [Constantes e paths](#1-constantes-e-paths)
2. [Dataclasses](#2-dataclasses)
3. [Enumerações](#3-enumerações)
4. [Funções de I/O do log](#4-funções-de-io-do-log)
5. [Verificação de integridade](#5-verificação-de-integridade)
6. [Externalização de blobs](#6-externalização-de-blobs)
7. [Reducer e estado](#7-reducer-e-estado)
8. [Snapshots](#8-snapshots)
9. [Retry policy](#9-retry-policy)
10. [Locking](#10-locking)
11. [Exceções](#11-exceções)
12. [Helpers](#12-helpers)
13. [Convenções de uso](#13-convenções-de-uso)

---

## 1. Constantes e paths

Todos os paths são configuráveis via variáveis de módulo para permitir override em testes.

```python
from pathlib import Path

# Paths padrão
ORCH_DIR: Path = Path(".orch")
LOG_PATH: Path = ORCH_DIR / "log.jsonl"
LOCK_PATH: Path = ORCH_DIR / "log.jsonl.lock"
STATE_DIR: Path = ORCH_DIR / "state"
DLQ_DIR: Path = ORCH_DIR / "dlq"
AUDIT_DIR: Path = ORCH_DIR / "audit"
METRICS_DIR: Path = ORCH_DIR / "metrics"
BLOBS_DIR: Path = ORCH_DIR / "blobs"
CONFIG_PATH: Path = ORCH_DIR / "config.json"

# Limites
MAX_INLINE_PAYLOAD: int = 3500    # bytes, margem abaixo de PIPE_BUF
LOCK_TIMEOUT_S: float = 10.0      # segundos
SNAPSHOT_EVERY_N_EVENTS: int = 100
```

**Em testes**, use `monkeypatch` para redirecionar:

```python
monkeypatch.setattr(orch_core, "LOG_PATH", tmp_path / "log.jsonl")
```

### `ensure_dirs() -> None`

Cria todos os diretórios `.orch/` necessários. Idempotente.

```python
def ensure_dirs() -> None:
    """Creates .orch/ and all subdirectories if missing. Idempotent."""
```

**Uso**: chamado implicitamente por `append_event`. Raramente necessário chamar diretamente.

---

## 2. Dataclasses

### 2.1 `Event`

Representa um evento do log. Imutável por convenção (dataclass sem frozen=True por simplicidade, mas não mutar após criação).

```python
from dataclasses import dataclass, asdict, field
from typing import Any

@dataclass
class Event:
    """A single event in the orchestrator log."""
    seq: int
    event_id: str
    ts: str                        # ISO 8601 UTC ms
    agent: str
    event_type: str
    task_id: str | None
    attempt: int
    data: dict[str, Any]
    prev_hash: str
    hash: str = ""                 # computed after construction

    def to_dict(self) -> dict[str, Any]:
        """Converts to dict for JSON serialization."""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        """Creates Event from dict (inverse of to_dict)."""

    def canonical_json(self) -> str:
        """
        Canonical JSON representation for hashing.
        Excludes `hash` field. Keys sorted. No whitespace.
        """

    def compute_hash(self) -> str:
        """Computes SHA-256 hash of canonical representation."""
```

**Invariantes**:
- `seq >= 1`
- `event_id` matches pattern `^evt_[0-9A-HJKMNP-TV-Z]{26}$`
- `ts` matches ISO 8601 UTC ms
- `event_type` is in `EventType` enum
- `prev_hash` is `"GENESIS"` or 64 hex chars
- `hash` is 64 hex chars (após `compute_hash`)

### 2.2 `TaskState`

Estado derivado de uma task.

```python
@dataclass
class TaskState:
    """Derived state for a single task."""
    task_id: str
    phase: str
    status: str                              # TaskStatus enum value
    deps: list[str]
    tier: str                                # Tier enum value
    task_type: str
    spec: str
    attempts: int = 0
    max_attempts: int = 3                    # overridden by config per tier
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

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskState": ...
```

### 2.3 `PhaseState`

Estado derivado de uma fase.

```python
@dataclass
class PhaseState:
    """Derived state for a workflow phase."""
    name: str
    order: int
    required: bool
    status: str                              # PhaseStatus enum value
    entered_at: str | None = None
    criteria_met: list[str] = field(default_factory=list)
    approved_at: str | None = None
    completed_at: str | None = None
    paused_at: str | None = None
    pause_reason: str | None = None

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhaseState": ...
```

### 2.4 `OrchState`

Estado agregado do orquestrador. Produto do reducer.

```python
@dataclass
class OrchState:
    """Aggregate state derived from event log."""
    workflow_id: str | None = None
    run_status: str = "active"               # active | escalated | completed | degraded
    current_phase: str | None = None
    tasks: dict[str, TaskState] = field(default_factory=dict)
    phases: dict[str, PhaseState] = field(default_factory=dict)
    escalation: dict[str, Any] | None = None
    circuit_breaker: dict[str, Any] | None = None
    last_seq: int = 0
    last_snapshot_seq: int = 0

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OrchState": ...

    def tasks_by_status(self, status: str) -> list[TaskState]:
        """Returns tasks with given status."""

    def tasks_by_phase(self, phase: str) -> list[TaskState]:
        """Returns tasks belonging to given phase."""

    def ready_tasks(self) -> list[TaskState]:
        """Returns tasks in 'ready' status, ordered by (priority desc, seq asc)."""
```

### 2.5 `VerifyResult`

Resultado de `verify_chain`.

```python
@dataclass
class VerifyResult:
    """Result of chain verification."""
    ok: bool
    message: str
    mode: str                                # strict | recover | audit
    events_verified: int = 0
    first_error_seq: int | None = None
    error_details: list[dict[str, Any]] = field(default_factory=list)
    truncation_candidate: dict[str, Any] | None = None
```

### 2.6 `RetryPolicy`

```python
@dataclass
class RetryPolicy:
    """Retry configuration for a tier or task_type."""
    max_attempts: int
    base_delay_s: float
    cap_s: float

    @classmethod
    def for_tier(cls, tier: str, config: dict) -> "RetryPolicy":
        """Loads policy from config for given tier."""

    @classmethod
    def for_task(cls, task_type: str, tier: str, config: dict) -> "RetryPolicy":
        """Loads policy with task_type override precedence."""
```

---

## 3. Enumerações

```python
from enum import Enum

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
        """Returns True if this closes a task attempt."""
        return event_type in {
            cls.TASK_COMPLETED.value,
            cls.TASK_FAILED.value,
        }


class TaskStatus(str, Enum):
    """Derived task statuses."""
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
        return status in {cls.COMPLETED.value, cls.DLQ.value, cls.CANCELLED.value}


class PhaseStatus(str, Enum):
    """Derived phase statuses."""
    PENDING = "pending"
    ACTIVE = "active"
    EXIT_APPROVED = "exit_approved"
    COMPLETED = "completed"
    PAUSED = "paused"


class Tier(str, Enum):
    """Task priority tiers."""
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
```

---

## 4. Funções de I/O do log

### 4.1 `append_event`

**A função mais crítica do sistema.** Todas as escritas no log passam por ela.

```python
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
    Validates event type and basic structure before writing.
    Externalizes payloads > MAX_INLINE_PAYLOAD to .orch/blobs/.

    Args:
        agent: Emitter identity (orchestrator, worker-*, hook-*, operator).
        event_type: One of EventType enum values.
        task_id: Task identifier (t_NNNN) or None for global events.
        attempt: Current attempt number (>= 1).
        data: Type-specific payload. Must contain 'phase' for task_* events.

    Returns:
        The complete Event with assigned seq, event_id, ts, prev_hash, hash.

    Raises:
        ValueError: Invalid event_type or invalid field values.
        EventValidationError: data doesn't match type-specific schema.
        TimeoutError: Could not acquire lock within LOCK_TIMEOUT_S.
        OSError: Filesystem errors (permissions, disk full).
    """
```

**Comportamento**:
1. Valida `event_type` contra `EventType`.
2. Valida shape básico de `data` conforme tipo.
3. Adquire lock em `LOCK_PATH`.
4. Lê último evento para computar `seq` e `prev_hash`.
5. Constrói `Event` com `event_id`, `ts` atuais.
6. Se `data` serializado > `MAX_INLINE_PAYLOAD`: externaliza para blob, substitui `data` por `_blob_ref`.
7. Computa `hash`.
8. Append atômico + fsync.
9. Libera lock.
10. Retorna `Event` completo.

**Exemplo**:

```python
event = append_event(
    agent="worker-code-writer-1",
    event_type="task_completed",
    task_id="t_0042",
    attempt=1,
    data={
        "phase": "dev",
        "artifacts": ["src/auth/jwt.py"],
        "summary": "Implemented JWT with RS256"
    }
)
# event.seq = 42, event.hash = "..." etc.
```

### 4.2 `read_events`

```python
from typing import Iterator

def read_events(from_seq: int = 0) -> Iterator[Event]:
    """
    Yields events from the log with seq >= from_seq, in order.

    Tolerates a truncated last line (returns without raising).
    Raises on corruption in middle of log.

    Args:
        from_seq: Minimum seq to include. 0 returns all.

    Yields:
        Event objects in seq order.

    Raises:
        CorruptedLogError: Invalid JSON in middle of log (not last line).
    """
```

**Uso**:

```python
# Todos os eventos
for event in read_events():
    print(event.seq, event.event_type)

# Desde um snapshot
for event in read_events(from_seq=snapshot_seq + 1):
    state = apply_event(state, event)
```

### 4.3 `last_event`

```python
def last_event() -> Event | None:
    """
    Returns the last event in the log, or None if empty.

    Efficient: reads only what's needed (uses seek to end for large logs).
    """
```

**Uso**: típico em `append_event` para computar `prev_hash`. Expor publicamente para debug e tools.

### 4.4 `read_events_filtered`

```python
def read_events_filtered(
    from_seq: int = 0,
    task_id: str | None = None,
    event_type: str | None = None,
    phase: str | None = None,
    tail: int | None = None,
) -> list[Event]:
    """
    Convenience: reads events with multiple filters applied.

    All filters are AND. If tail is set, returns only last N after filtering.

    Args:
        from_seq: Minimum seq.
        task_id: Filter by task_id (exact match).
        event_type: Filter by event_type (exact match).
        phase: Filter by data.phase (exact match).
        tail: Return only last N events after filtering.

    Returns:
        List of Events (not iterator — computes full list).
    """
```

---

## 5. Verificação de integridade

### 5.1 `verify_chain`

```python
from typing import Literal

def verify_chain(
    mode: Literal["strict", "recover", "audit"] = "strict",
    log_path: Path | None = None,
) -> VerifyResult:
    """
    Verifies hash chain integrity of the log.

    Modes:
        strict:  Stops at first error. Use in orchestrator startup.
        audit:   Reports all errors without modifying. Use for investigation.
        recover: NOT implemented here. Use verify_and_recover() explicitly.

    Args:
        mode: Verification mode.
        log_path: Override default log path (for testing).

    Returns:
        VerifyResult with ok, message, details.
    """
```

**Exemplo**:

```python
result = verify_chain(mode="strict")
if not result.ok:
    raise CorruptedLogError(result.message)
```

### 5.2 `verify_and_recover`

Função separada para recovery, NUNCA invocada automaticamente.

```python
def verify_and_recover(
    from_seq: int,
    operator: str,
    confirm: bool = False,
    log_path: Path | None = None,
) -> VerifyResult:
    """
    Truncates log at last valid event, archives corrupted portion.

    Emits log_recovered event.

    Args:
        from_seq: Seq from which to truncate (inclusive).
        operator: Identity of operator executing recovery.
        confirm: Must be True; safety check to prevent accidental execution.
        log_path: Override default log path.

    Returns:
        VerifyResult describing recovery outcome.

    Raises:
        ValueError: If confirm=False.
        EventValidationError: If from_seq is invalid.
    """
```

**Invariante de design**: **nunca** chamar de código automatizado. Sempre via CLI com `--confirm` do operador.

---

## 6. Externalização de blobs

### 6.1 `externalize_blob`

```python
def externalize_blob(data: dict[str, Any], event_id: str) -> tuple[str, str]:
    """
    Persists large payload to .orch/blobs/{event_id}.json.

    Computes and returns SHA-256 hash for integrity verification.

    Args:
        data: Payload to externalize (any JSON-serializable dict).
        event_id: Event ID (used for blob filename).

    Returns:
        Tuple of (blob_path, blob_hash).
        blob_path: Relative path like ".orch/blobs/evt_XYZ.json".
        blob_hash: SHA-256 hex digest.

    Raises:
        OSError: Filesystem errors.
    """
```

### 6.2 `load_blob_data`

```python
def load_blob_data(event: Event) -> dict[str, Any]:
    """
    Returns data of event, loading from blob if externalized.

    Verifies blob hash matches _blob_hash to detect tampering.

    Args:
        event: Event to load data from.

    Returns:
        The full data dict. For inline events: event.data directly.
        For externalized events: JSON-parsed blob content.

    Raises:
        BlobIntegrityError: Blob hash mismatch (tampering detected).
        FileNotFoundError: Blob file missing.
    """
```

**Uso**:

```python
for event in read_events():
    data = load_blob_data(event)  # handles inline vs. externalized transparently
    # use data normally
```

### 6.3 `is_blob_ref`

```python
def is_blob_ref(data: dict[str, Any]) -> bool:
    """
    Returns True if data is a blob reference (has _blob_ref, _size, _blob_hash).
    """
```

---

## 7. Reducer e estado

### 7.1 `apply_event`

Função pura. Aplica um evento a um estado, retornando novo estado.

```python
def apply_event(state: OrchState, event: Event) -> OrchState:
    """
    Applies a single event to state, returning updated state.

    Pure function with no side effects.
    Raises on illegal state transitions.

    Args:
        state: Current state.
        event: Event to apply.

    Returns:
        New state with event applied. Input state may be modified
        (see Note on mutability below).

    Raises:
        IllegalTransition: Event implies an illegal state transition.
        UnknownEventType: event_type not recognized.
    """
```

**Nota sobre mutabilidade**: por performance, implementação pode mutar `state` in-place e retornar o mesmo objeto. Não confie na imutabilidade do input; se precisar preservar, `copy.deepcopy(state)` antes.

### 7.2 `reduce_all`

```python
def reduce_all() -> OrchState:
    """
    Builds state from scratch by replaying all events from log start.

    O(N) in log size. Prefer reduce_incremental() for production use.

    Returns:
        Complete derived state.

    Raises:
        IllegalTransition: Log contains illegal transition.
        CorruptedLogError: Log is corrupted.
    """
```

**Uso**: em testes ou debug. Em produção, use `reduce_incremental`.

### 7.3 `reduce_incremental`

```python
def reduce_incremental() -> OrchState:
    """
    Efficient state reconstruction: loads latest snapshot + applies events after.

    Falls back to reduce_all() if no snapshot exists.

    Returns:
        Complete derived state.

    Raises:
        IllegalTransition: Events after snapshot contain illegal transition.
        CorruptedLogError: Log is corrupted.
    """
```

### 7.4 Queries sobre estado

Funções convenience que operam sobre `OrchState`. Para ergonomia; tudo pode ser computado manualmente.

```python
def current_phase(state: OrchState) -> PhaseState | None:
    """Returns the active phase, or None if no phase is active."""

def ready_tasks_in_active_phase(state: OrchState) -> list[TaskState]:
    """Returns ready tasks belonging to the currently active phase."""

def running_tasks(state: OrchState) -> list[TaskState]:
    """Returns all tasks in 'running' status."""

def stale_tasks(state: OrchState, now_iso: str) -> list[TaskState]:
    """
    Returns running tasks whose last_event_at exceeds tier stale_seconds.

    Args:
        state: Current state.
        now_iso: Current time as ISO 8601 string.
    """

def tasks_ready_for_retry(state: OrchState, now_iso: str) -> list[TaskState]:
    """Returns scheduled tasks whose next_retry_at has passed."""
```

---

## 8. Snapshots

### 8.1 `save_snapshot`

```python
def save_snapshot(state: OrchState, state_dir: Path | None = None) -> Path:
    """
    Persists state to .orch/state/snapshot-NNNNNNNN.json.

    Filename uses state.last_seq padded to 8 digits.

    Args:
        state: State to persist.
        state_dir: Override default state directory.

    Returns:
        Path to written snapshot file.

    Raises:
        OSError: Filesystem errors.
    """
```

### 8.2 `latest_snapshot`

```python
def latest_snapshot(state_dir: Path | None = None) -> tuple[OrchState, int]:
    """
    Returns (state, starting_seq) from the latest snapshot.

    If no snapshot exists, returns (empty OrchState, 0).

    Args:
        state_dir: Override default state directory.

    Returns:
        Tuple of (OrchState, last_seq_in_snapshot).
    """
```

### 8.3 `should_snapshot`

```python
def should_snapshot(state: OrchState) -> bool:
    """
    Returns True if a snapshot should be written.

    Based on: state.last_seq - state.last_snapshot_seq >= SNAPSHOT_EVERY_N_EVENTS.
    """
```

---

## 9. Retry policy

### 9.1 `backoff_seconds`

Função pura, determinística exceto pelo jitter.

```python
import random

def backoff_seconds(
    attempts: int,
    base_delay_s: float = 30.0,
    cap_s: float = 600.0,
    jitter_range: tuple[float, float] = (0.8, 1.2),
) -> float:
    """
    Computes exponential backoff with jitter.

    formula: min(base * 2^(attempts-1), cap) * uniform(jitter_range)

    Args:
        attempts: Attempt number that just failed (>= 1).
        base_delay_s: Base delay for first attempt.
        cap_s: Maximum delay in seconds.
        jitter_range: Multiplicative jitter range.

    Returns:
        Seconds to wait before next retry.
    """
```

### 9.2 `load_retry_policy`

```python
def load_retry_policy(
    tier: str,
    task_type: str | None = None,
    config_path: Path | None = None,
) -> RetryPolicy:
    """
    Loads retry policy from config with task_type override precedence.

    Args:
        tier: Task tier.
        task_type: Optional task_type for override lookup.
        config_path: Override default config path.

    Returns:
        RetryPolicy to apply.
    """
```

### 9.3 `should_retry`

```python
def should_retry(task: TaskState, policy: RetryPolicy) -> bool:
    """
    Returns True if task should be retried.

    Rules:
      - retryable=false → False (immediate DLQ)
      - attempts >= max_attempts → False (DLQ)
      - otherwise → True
    """
```

---

## 10. Locking

### 10.1 `LogLock`

Context manager que adquire lock exclusivo via `fcntl.flock`.

```python
import fcntl
from contextlib import AbstractContextManager

class LogLock(AbstractContextManager):
    """
    Exclusive POSIX lock on .orch/log.jsonl.lock.

    Non-blocking with timeout. Releases automatically on exit (even on exception).

    Usage:
        with LogLock():
            # append to log
            ...
    """

    def __init__(
        self,
        lock_path: Path | None = None,
        timeout_s: float = LOCK_TIMEOUT_S,
    ):
        """
        Args:
            lock_path: Override default lock path.
            timeout_s: Max wait for lock acquisition.
        """

    def __enter__(self) -> "LogLock": ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
```

**Implementação chave**:

```python
def __enter__(self):
    self._fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    start = time.time()
    while True:
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() - start > self.timeout_s:
                os.close(self._fd)
                raise TimeoutError(...)
            time.sleep(0.05)
    return self
```

**Por que não blocking `fcntl.LOCK_EX` direto**: sem timeout, processo fica indefinidamente esperando. Preferimos fail-fast.

---

## 11. Exceções

Hierarquia tipada. Toda exceção herda de `OrchError`.

```python
class OrchError(Exception):
    """Base class for all orch_core exceptions."""


class EventValidationError(OrchError):
    """Event doesn't match schema (envelope or type-specific)."""


class CorruptedLogError(OrchError):
    """Log file is corrupted: invalid JSON, broken hash chain."""


class IllegalTransition(OrchError):
    """Event would cause illegal state transition."""


class UnknownEventType(OrchError):
    """Event type not recognized."""


class BlobIntegrityError(OrchError):
    """Blob hash doesn't match _blob_hash (tampering detected)."""


class BlobNotFoundError(OrchError):
    """Blob file referenced by event doesn't exist."""


class LockTimeoutError(OrchError, TimeoutError):
    """Could not acquire log lock within timeout."""


class ConfigError(OrchError):
    """Config file is missing, invalid, or has wrong schema."""
```

**Convenção**: funções que falham lançam exceção apropriada. Nunca retornam `None` ou `False` como indicador de erro, exceto quando ausência é resultado legítimo (ex: `last_event()` retorna `None` se log vazio).

---

## 12. Helpers

### 12.1 Identifiers e timestamps

```python
import uuid
from datetime import datetime, timezone

def new_event_id() -> str:
    """
    Generates a new event ID.

    Format: evt_ + 26 chars base32 (ULID-like).

    Note: not a real ULID (no time component), but meets the pattern.
    For true ULID with time ordering, use an external library.
    """
    raw = uuid.uuid4().hex[:26].upper().replace("I", "J").replace("L", "M").replace("O", "P").replace("U", "V")
    return f"evt_{raw}"


def now_iso() -> str:
    """
    Returns current UTC time as ISO 8601 with millisecond precision.

    Format: YYYY-MM-DDTHH:MM:SS.mmmZ
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def parse_iso(ts: str) -> datetime:
    """Parses ISO 8601 timestamp string to datetime."""
```

### 12.2 Hashing

```python
import hashlib

def sha256_hex(data: bytes) -> str:
    """Returns SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """
    Canonical JSON serialization for hashing.
    Sorted keys, no whitespace, ensure_ascii=False.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

### 12.3 Config loading

```python
def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    Loads .orch/config.json with defaults for missing fields.

    If file doesn't exist, returns full default config.
    If file is invalid JSON, raises ConfigError.

    Args:
        config_path: Override default config path.

    Returns:
        Complete config dict with all defaults filled in.

    Raises:
        ConfigError: File exists but is invalid.
    """


def default_config() -> dict[str, Any]:
    """Returns the default config dict (same as shown in architecture §19)."""
```

---

## 13. Convenções de uso

### 13.1 Padrão para emitir evento (orchestrator ou worker)

```python
from orch_core import append_event

event = append_event(
    agent="orchestrator",
    event_type="task_created",
    task_id="t_0042",
    attempt=1,
    data={
        "phase": "dev",
        "tier": "standard",
        "type": "implementation",
        "spec": "Implement...",
        "deps": ["t_0041"],
        "priority": 50,
        "evidence": [38, 40]
    }
)
# event.seq is now available
```

### 13.2 Padrão para reconstituir estado

```python
from orch_core import reduce_incremental, current_phase

state = reduce_incremental()
phase = current_phase(state)
if phase:
    print(f"Active phase: {phase.name} ({phase.status})")
```

### 13.3 Padrão para inspecionar eventos recentes

```python
from orch_core import read_events_filtered

recent = read_events_filtered(event_type="task_failed", tail=10)
for event in recent:
    data = load_blob_data(event)
    print(f"{event.ts} task={event.task_id} reason={data['reason']}")
```

### 13.4 Padrão para verificar integridade em startup

```python
from orch_core import verify_chain, CorruptedLogError

result = verify_chain(mode="strict")
if not result.ok:
    # Escalar E09_corrupted_log
    raise CorruptedLogError(result.message)
```

### 13.5 Thread safety

**Seguro para concorrência** (múltiplos processos ou threads):
- `append_event` (usa flock)
- `read_events` (leitura, consistência eventual aceitável)
- `last_event` (leitura)
- `verify_chain` (leitura, pode dar falso negativo se log está sendo escrito — use após quiesceing)
- `save_snapshot` (usa seu próprio filesystem atomic rename)

**Não seguro para concorrência** (requer coordenação externa):
- `reduce_all`, `reduce_incremental` (podem ler log meio-escrito — aceitável se leitor tolera)
- `verify_and_recover` (modifica log — exige quiescing total)

### 13.6 Performance esperada

Valores de referência em máquina comum (não benchmark formal):

| Operação | Latência típica |
|---|---|
| `append_event` (inline) | ~5-15ms (lock + hash + fsync) |
| `append_event` (com blob) | ~20-40ms |
| `read_events` (log 1000 eventos) | ~50ms |
| `verify_chain` (log 1000 eventos) | ~100ms |
| `reduce_incremental` (snapshot + 100 eventos) | ~30ms |
| `reduce_all` (log 10000 eventos) | ~500ms |

Se performance não bate em uma ordem de magnitude: investigue (SSD? outro processo segurando lock?).

---

## 14. Módulo expõe (API completa)

```python
# Constants
__all__ = [
    # Paths
    "ORCH_DIR", "LOG_PATH", "LOCK_PATH", "STATE_DIR", "DLQ_DIR",
    "AUDIT_DIR", "METRICS_DIR", "BLOBS_DIR", "CONFIG_PATH",
    # Limits
    "MAX_INLINE_PAYLOAD", "LOCK_TIMEOUT_S", "SNAPSHOT_EVERY_N_EVENTS",

    # Dataclasses
    "Event", "TaskState", "PhaseState", "OrchState",
    "VerifyResult", "RetryPolicy",

    # Enums
    "EventType", "TaskStatus", "PhaseStatus", "Tier",

    # Log I/O
    "append_event", "read_events", "last_event", "read_events_filtered",
    "ensure_dirs",

    # Verification
    "verify_chain", "verify_and_recover",

    # Blobs
    "externalize_blob", "load_blob_data", "is_blob_ref",

    # Reducer
    "apply_event", "reduce_all", "reduce_incremental",

    # Queries
    "current_phase", "ready_tasks_in_active_phase", "running_tasks",
    "stale_tasks", "tasks_ready_for_retry",

    # Snapshots
    "save_snapshot", "latest_snapshot", "should_snapshot",

    # Retry
    "backoff_seconds", "load_retry_policy", "should_retry",

    # Locking
    "LogLock",

    # Exceptions
    "OrchError", "EventValidationError", "CorruptedLogError",
    "IllegalTransition", "UnknownEventType",
    "BlobIntegrityError", "BlobNotFoundError",
    "LockTimeoutError", "ConfigError",

    # Helpers
    "new_event_id", "now_iso", "parse_iso",
    "sha256_hex", "canonical_json",
    "load_config", "default_config",
]
```

---

## 15. Checklist para implementador

Ao implementar `orch_core.py`, confirme:

- [ ] Todas as dataclasses têm type hints completos
- [ ] `Event.compute_hash` usa canonical_json (sorted, compact)
- [ ] `append_event` valida antes de lock (rejeição rápida)
- [ ] `append_event` faz fsync após write
- [ ] `LogLock` tem timeout e libera em exceção
- [ ] `verify_chain` modo strict para no primeiro erro
- [ ] `verify_and_recover` requer `confirm=True`
- [ ] `load_blob_data` verifica hash antes de retornar
- [ ] `apply_event` lança `IllegalTransition` em transição proibida
- [ ] `reduce_incremental` cai para `reduce_all` se snapshot ausente
- [ ] `backoff_seconds` aplica jitter após cálculo determinístico
- [ ] Todas as exceções herdam de `OrchError`
- [ ] `__all__` lista toda a API pública
- [ ] Imports no topo do módulo (não lazy)
- [ ] Docstrings estilo Google ou NumPy em todas as funções públicas
