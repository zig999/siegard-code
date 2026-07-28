#!/usr/bin/env python3
"""
CLI: emit a worker event to the orchestration log.

Guard-rail: only task_progress, task_completed, and task_failed are allowed.
Any other event type is rejected unconditionally — this is a security boundary,
not a soft validation.

Agent identity is resolved in priority order:
  1. ORCH_WORKER_ID environment variable (set when env is correctly exported)
  2. Workers registry (.orch/workers/*.json) matched by task_id + attempt
     (fallback when env var is lost between separate Bash calls)
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    EventType,
    EventValidationError,
    UnknownEventType,
    WORKERS_DIR,
    append_event,
)

# The exact set of types workers are allowed to emit.
_ALLOWED_KINDS: dict[str, str] = {
    "progress":  EventType.TASK_PROGRESS.value,
    "completed": EventType.TASK_COMPLETED.value,
    "failed":    EventType.TASK_FAILED.value,
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Emit a worker event (guard-railed to worker-emittable types only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--kind",
        required=True,
        choices=list(_ALLOWED_KINDS),
        help="Event kind: progress | completed | failed",
    )
    p.add_argument("--task-id", required=True, dest="task_id", help="Task ID.")
    p.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Attempt number (default: 1).",
    )
    p.add_argument(
        "--data",
        default="{}",
        help="Event payload as a JSON object string (default: '{}').",
    )
    return p.parse_args()


def _notarize_artifacts(artifacts: list[str], data: dict) -> list[str]:
    """A1' (v2.35.0): compute sha256 per declared artifact — notarization.

    The hash is computed HERE, in deterministic code at emit time, not declared
    by the worker: a worker cannot lie about what it wrote, and the log's
    append-only hash chain then acts as a notary for artifact content.
    u-handoff-validator's PROV rules later verify that every hash pinned in
    handoff-manifest.yaml matches a log-notarized hash — the check that makes
    freelance edits + manifest regeneration detectable.

    Keys are normalized to project-root-relative posix paths when possible so
    the validator can match them against manifest paths. Raw bytes are hashed
    (same convention as generate_handoff_manifest._sha256 — the two must never
    diverge). A path that is missing or not a regular file produces a stderr
    warning and no hash entry — tolerated because artifact path conventions
    vary by worker (session-dir reports, directories); spec files that dodge
    hashing are still caught by PROV at handoff, just later.
    """
    project_root = Path(os.environ.get("ORCH_PROJECT_DIR", ".")).resolve()
    hashes: dict[str, str] = {}
    skipped: list[str] = []
    for p in artifacts:
        raw = Path(p.replace("\\", "/"))
        target = raw if raw.is_absolute() else project_root / raw
        try:
            key = target.resolve().relative_to(project_root).as_posix()
        except (ValueError, OSError):
            key = raw.as_posix()
        try:
            if target.is_file():
                hashes[key] = hashlib.sha256(target.read_bytes()).hexdigest()
            else:
                skipped.append(key)
        except OSError:
            skipped.append(key)
    if hashes:
        data["artifacts_sha256"] = hashes
    return skipped


def _registry_identity_violation(
    worker_id: str, task_id: str, attempt: int
) -> tuple[str, str] | None:
    """B2 (v2.34.0): cross-check the claimed identity against the worker registry.

    The env-var identity model is spoofable by construction: any session that can
    `export ORCH_WORKER_ID` chooses its identity (the downstream flow-discipline
    incident class). The orchestrator writes a registry entry BEFORE every spawn
    (I5 / register_worker), so a legitimate worker's identity is always backed by
    a matching entry. Two hard violations:

      * an entry exists for this worker_id but binds a DIFFERENT (task_id, attempt)
      * an entry exists for this (task_id, attempt) but under a DIFFERENT worker_id

    Missing entry on both sides is a WARNING, not an error: the reverse-spec
    pipeline dispatches workers without registry entries (off-log orchestration),
    and hard-failing would break it. The deterministic boundary against freelance
    work is flow_guard.py + artifact notarization (Pacote A) — this check only
    removes the cheap impersonation paths.

    Returns (severity, detail) — severity "error" | "warning" — or None when the
    registry confirms the identity. Registry read errors return None (fail-open:
    an unreadable registry is not evidence of forgery).
    """
    try:
        entry_path = WORKERS_DIR / f"{worker_id}.json"
        if entry_path.exists():
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            if entry.get("task_id") != task_id or entry.get("attempt") != attempt:
                return (
                    "error",
                    f"registry entry for {worker_id!r} binds "
                    f"(task_id={entry.get('task_id')!r}, attempt={entry.get('attempt')!r}), "
                    f"but this emit claims (task_id={task_id!r}, attempt={attempt}). "
                    "A worker only emits for the task it was registered for.",
                )
            return None
        if WORKERS_DIR.exists():
            for f in WORKERS_DIR.glob("*.json"):
                try:
                    other = json.loads(f.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                if (
                    other.get("task_id") == task_id
                    and other.get("attempt") == attempt
                    and other.get("worker_id") != worker_id
                ):
                    return (
                        "error",
                        f"(task_id={task_id!r}, attempt={attempt}) is registered to "
                        f"{other.get('worker_id')!r}, not to {worker_id!r}. "
                        "Do not emit for a task claimed by another worker.",
                    )
        return (
            "warning",
            f"no registry entry backs {worker_id!r} for "
            f"(task_id={task_id!r}, attempt={attempt}) — legitimate for off-registry "
            "pipelines (reverse-spec); anywhere else this means the orchestrator "
            "skipped register_worker before spawning.",
        )
    except Exception:  # noqa: BLE001
        return None


def _infer_worker_id_from_registry(task_id: str, attempt: int) -> str | None:
    """
    Fallback: find worker_id from .orch/workers/ registry when ORCH_WORKER_ID
    is not set in the environment. Handles the case where env vars are lost
    between separate Bash tool calls in Claude Code.
    """
    if not WORKERS_DIR.exists():
        return None
    for f in WORKERS_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            if entry.get("task_id") == task_id and entry.get("attempt") == attempt:
                wid = entry.get("worker_id")
                if wid:
                    return wid
        except Exception:  # noqa: BLE001
            continue
    return None


# R02c — workers whose whole purpose is judging someone else's artifact. They may
# write their own report; they may not register the reviewed artifact as output.
# `worker_id` is `<worker>-<task_id>` (orchestrator-sdd Step 5.2), so the prefix
# identifies the worker type without needing the registry.
_REVIEW_ONLY_WORKERS: tuple[str, ...] = ("u-spec-reviewer",)

# Path segments that mark a reviewed artifact rather than a review output.
# `domains/` holds the per-domain spec tree (openapi.yaml, *.spec.md, *.back.md).
_REVIEWED_ARTIFACT_SEGMENTS: tuple[str, ...] = ("domains",)


def _review_only_violation(worker_id: str, path: str) -> str | None:
    """Return an error message when a review-only worker registers a reviewed file."""
    if not any(worker_id.startswith(w) for w in _REVIEW_ONLY_WORKERS):
        return None
    segments = path.replace("\\", "/").split("/")
    for marker in _REVIEWED_ARTIFACT_SEGMENTS:
        if marker in segments:
            return (
                f"{worker_id} is a review-only worker and must not register "
                f"{path!r} as its artifact: a path under '{marker}/' is the artifact "
                "under review, not a review output. Report the issues and let the "
                "Spec Writer apply them (u-spec-reviewer, Separation of duties)."
            )
    return None


def main() -> int:
    args = _parse_args()

    worker_id = os.environ.get("ORCH_WORKER_ID") or _infer_worker_id_from_registry(
        args.task_id, args.attempt
    )
    if not worker_id:
        print(json.dumps({
            "status": "error",
            "reason": "missing_env",
            "detail": (
                "ORCH_WORKER_ID is not set and worker_id could not be inferred from "
                f"registry. task_id={args.task_id!r} attempt={args.attempt}. "
                "Export ORCH_WORKER_ID in the same shell call as emit.py."
            ),
        }))
        return 1

    # B2 (v2.34.0): identity must be backed by the registry — see
    # _registry_identity_violation for the two hard cases and the warning tier.
    identity = _registry_identity_violation(worker_id, args.task_id, args.attempt)
    if identity is not None:
        severity, detail = identity
        if severity == "error":
            print(json.dumps({
                "status": "error",
                "reason": "identity_mismatch",
                "detail": detail,
            }))
            return 1
        print(json.dumps({
            "status": "warning",
            "reason": "unregistered_worker",
            "detail": detail,
        }), file=sys.stderr)

    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "reason": "invalid_json", "detail": str(exc)}))
        return 1

    if not isinstance(data, dict):
        print(json.dumps({
            "status": "error",
            "reason": "invalid_json",
            "detail": "data must be a JSON object",
        }))
        return 1

    if args.kind == "completed":
        artifacts = data.get("artifacts")
        if artifacts is not None:
            if not isinstance(artifacts, list):
                print(json.dumps({
                    "status": "error",
                    "reason": "validation_error",
                    "detail": "artifacts must be a JSON array",
                }))
                return 1
            for path in artifacts:
                if not isinstance(path, str):
                    print(json.dumps({
                        "status": "error",
                        "reason": "validation_error",
                        "detail": f"artifacts entries must be strings, got {type(path).__name__}",
                    }))
                    return 1
                # Absolute paths are allowed — workers receive SESSION_DIR as absolute.
                # Only reject path traversal sequences.
                if ".." in path.replace("\\", "/").split("/"):
                    print(json.dumps({
                        "status": "error",
                        "reason": "validation_error",
                        "detail": f"artifact path must not contain '..': {path!r}",
                    }))
                    return 1
                # R02c: a review-only worker must not register the artifact it
                # reviewed. Enforced here, in Python, because prose did not hold: a
                # reviewer that had reported two Major issues was retried on
                # unchanged input, edited mwo-catalog.spec.md and openapi.yaml,
                # downgraded its own findings to "minor", and approved its own edit
                # — registering both spec files as its output. Separation of duties
                # is a critical guarantee, so it lives outside the LLM (P6/P7).
                violation = _review_only_violation(worker_id, path)
                if violation:
                    print(json.dumps({
                        "status": "error",
                        "reason": "separation_of_duties_violation",
                        "detail": violation,
                    }))
                    return 1
            # A1' (v2.35.0): notarize declared artifacts — sha256 computed here,
            # in deterministic code, and appended into the event data.
            skipped = _notarize_artifacts(artifacts, data)
            if skipped:
                print(json.dumps({
                    "status": "warning",
                    "reason": "artifacts_not_hashed",
                    "detail": (
                        f"declared artifacts not found as regular files (no sha256 "
                        f"recorded): {skipped}. Spec files under SPECS_DIR without a "
                        "notarized hash will fail PROV at handoff."
                    ),
                }), file=sys.stderr)

    event_type = _ALLOWED_KINDS[args.kind]

    try:
        event = append_event(
            agent=worker_id,
            event_type=event_type,
            task_id=args.task_id,
            attempt=args.attempt,
            data=data,
        )
    except (UnknownEventType, EventValidationError) as exc:
        print(json.dumps({"status": "error", "reason": "validation_error", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    print(json.dumps(event.to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
