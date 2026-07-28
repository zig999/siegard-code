#!/usr/bin/env python3
"""
PreToolUse hook: deterministic ownership guard over pipeline-owned artifacts.

Threat model (v2.34.0 flow-discipline remediation). The adversary is NOT a
malicious actor — it is the obliging host-session model taking the path of
least resistance. Observed downstream incident: the main session offered to
"write the spec insertions, regenerate the manifest and run the five gates"
inline, bypassing /u-improve entirely. The existing gates verify INTEGRITY
(manifest sha256 == file contents), not PROVENANCE (was this produced by the
pipeline?), so freelance work regenerated into the manifest is
indistinguishable from pipeline output.

This guard closes the casual path deterministically (P7 — critical guarantees
live outside the LLM): Write/Edit tool calls targeting pipeline-owned paths are
blocked unless a pipeline worker is in flight, and the denial redirects the
model to the correct entry command. It is intentionally NOT the security
boundary:

  * Bash writes (redirects, sed -i, python -c) are NOT intercepted — parsing
    arbitrary shell for write intent is undecidable. The consumption-side
    guarantee (artifact notarization in the log + PROV rules in
    u-handoff-validator — Pacote A, planned v2.35.0) is what makes evaded
    writes worthless: unnotarized artifacts never enter the next phase.
  * While a worker is in flight the guard cannot attribute the calling session
    (the same PreToolUse/SubagentStop correlation gap documented in
    on_subagent_stop.py — no payload key maps to a registry entry). A
    freelance write inside that window is allowed. Upgrade path: registry
    entries gain the worker's session_id at first checkpoint; the guard then
    compares the payload session_id and becomes exact.

Ownership classes:
  pipeline-owned  {specs_dir}/** (includes handoff-manifest.yaml, _validation/,
                  error-codes.md) — deny unless a registered worker attempt is
                  in flight (no terminal event AND liveness window not expired
                  — the SAME bounds the reaper and SubagentStop hook use).
                  .orch/log.jsonl — deny ALWAYS: the log is append-only and
                  hash-chained; append.py is the only write path (P1/P3).
  command-owned   .orch/sessions/** — always allowed (entry commands write
                  improve-scope.json etc. from the main session by design).
  unclaimed       everything else — not intercepted.

specs_dir resolution (first hit wins):
  1. .orch/config.json guard.specs_dir (explicit operator override)
  2. target CLAUDE.md machine-parsed block: `specs_dir: <value>` (the same
     contract orchestrator-dev and /u-spec parse — see
     claude-md-target-template.md "MACHINE-PARSED")
  3. SPECS_DIR environment variable
  4. "specs" when that directory exists
  Unresolvable -> only .orch/log.jsonl stays protected (fail-open, by design).

Operator kill-switch (.orch/config.json):
  {"guard": {"enforce": "hard" | "warn" | "off"}}
  hard (default) — deny with structured redirect (exit 2; stderr is fed back
                   to the model, which self-redirects to the entry command)
  warn           — allow; append an audit line to .orch/guard_warnings.jsonl
  off            — allow silently
The human owns the repo: the guard exists to stop the HOST MODEL from
freelancing pipeline artifacts, not to lock humans out.

Fail-open by design: any internal error (unreadable stdin, broken config,
reducer failure) exits 0 — a buggy guard must never brick ordinary editing.
Windows-safe: no fcntl; read-only except the best-effort warn audit file.
"""
import json
import os
import re
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (  # noqa: E402
    attempt_has_terminal,
    get_active_workers,
    load_config,
    now_iso,
    reduce_all,
    worker_liveness_expired,
)

# Tools whose input carries a file path this guard can adjudicate.
_PATH_FIELDS: dict[str, str] = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}

# Machine-parsed contract line in the target CLAUDE.md (see
# claude-md-target-template.md — "Do not rename or nest them").
_SPECS_DIR_RE = re.compile(r"^specs_dir:\s*(\S+)\s*$", re.MULTILINE)

_VALID_MODES = frozenset({"hard", "warn", "off"})


def _resolve_specs_dir(project_dir: Path, config: dict) -> str | None:
    """Returns the specs dir as a normalized project-relative posix string, or None."""
    guard_cfg = config.get("guard") or {}
    candidates: list[str] = []
    override = guard_cfg.get("specs_dir")
    if isinstance(override, str) and override.strip():
        candidates.append(override.strip())
    claude_md = project_dir / "CLAUDE.md"
    if claude_md.exists():
        try:
            m = _SPECS_DIR_RE.search(claude_md.read_text(encoding="utf-8"))
            if m:
                candidates.append(m.group(1))
        except OSError:
            pass
    env = os.environ.get("SPECS_DIR")
    if env:
        candidates.append(env)
    if (project_dir / "specs").is_dir():
        candidates.append("specs")
    for cand in candidates:
        cand = cand.replace("\\", "/").strip("/")
        # A template placeholder ({e.g. docs/specs}) is not a real value.
        if not cand or "{" in cand or "}" in cand:
            continue
        return cand
    return None


def _guard_mode(config: dict) -> str:
    mode = (config.get("guard") or {}).get("enforce", "hard")
    # Unknown value -> hard (a typo must not silently disable the guard; the
    # operator escapes by writing a VALID mode, which is the documented switch).
    return mode if mode in _VALID_MODES else "hard"


def _worker_in_flight(config: dict) -> bool:
    """True when any registered worker attempt is still live.

    Uses the same two bounds as the SubagentStop hook and the stale reaper
    (attempt_has_terminal + worker_liveness_expired), so the guard never
    disagrees with them about what "in flight" means. An entry whose task has
    no events yet (registered, spawn pending) counts as in flight — the window
    between register_worker() and the worker's first event is a legitimate
    dispatch in progress.
    """
    workers = get_active_workers()
    if not workers:
        return False
    state = reduce_all()
    now = now_iso()
    for entry in workers:
        task_id = entry.get("task_id")
        attempt = entry.get("attempt")
        if not task_id or attempt is None:
            continue
        task = state.tasks.get(task_id)
        if task is None:
            return True  # registered, no events yet — dispatch in progress
        if attempt_has_terminal(task, attempt):
            continue  # this attempt already ended; stale registry entry
        if worker_liveness_expired(task, now, config):
            continue  # silent past its window — reaper's to claim, not proof of life
        return True
    return False


def _known_workflows(project_dir: Path, limit: int = 3) -> list[str]:
    sessions = project_dir / ".orch" / "sessions"
    if not sessions.is_dir():
        return []
    try:
        return sorted(p.name for p in sessions.iterdir() if p.is_dir())[:limit]
    except OSError:
        return []


def _audit_warn(project_dir: Path, record: dict) -> None:
    """Best-effort append to the warn-mode audit file. Never raises."""
    try:
        audit = project_dir / ".orch" / "guard_warnings.jsonl"
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _deny(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    return 2


def main() -> int:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        return 0  # fail-open: unreadable input must not block editing

    tool_name = hook_input.get("tool_name", "")
    path_field = _PATH_FIELDS.get(tool_name)
    if path_field is None:
        return 0
    tool_input = hook_input.get("tool_input") or {}
    file_path = tool_input.get(path_field)
    if not isinstance(file_path, str) or not file_path.strip():
        return 0

    project_dir = Path(
        os.environ.get("ORCH_PROJECT_DIR") or hook_input.get("cwd") or "."
    ).resolve()

    target = Path(file_path.replace("\\", "/"))
    if not target.is_absolute():
        target = (Path(hook_input.get("cwd") or project_dir) / target)
    try:
        target = target.resolve()
        rel = target.relative_to(project_dir).as_posix()
    except (ValueError, OSError):
        return 0  # outside the project (or unresolvable) — not ours to police

    # Command-owned: entry commands legitimately write session artifacts
    # (improve-scope.json, triage inputs) from the main session.
    if rel.startswith(".orch/sessions/"):
        return 0

    is_log = rel == ".orch/log.jsonl"

    try:
        config = load_config()
    except Exception:  # noqa: BLE001
        config = {}

    mode = _guard_mode(config)
    if mode == "off":
        return 0

    specs_dir = None
    is_spec = False
    if not is_log:
        try:
            specs_dir = _resolve_specs_dir(project_dir, config)
        except Exception:  # noqa: BLE001
            specs_dir = None
        is_spec = specs_dir is not None and (
            rel == specs_dir or rel.startswith(specs_dir + "/")
        )
        if not is_spec:
            return 0

    if is_log:
        record = {
            "status": "blocked",
            "hook": "flow_guard",
            "reason": "append_only_log",
            "path": rel,
            "policy": (
                ".orch/log.jsonl is append-only and hash-chained (P1/P3); direct "
                "edits break the chain and verify.py will flag the log as corrupt"
            ),
            "action": (
                "append events via python3 .claude/skills/orch-log/scripts/append.py "
                "(orchestrators) or .claude/skills/orch-report/scripts/emit.py (workers)"
            ),
        }
        if mode == "warn":
            record["status"] = "warned"
            _audit_warn(project_dir, {**record, "ts": now_iso(), "tool": tool_name})
            print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
            return 0
        return _deny(record)

    # Pipeline-owned spec artifact.
    if mode == "warn":
        record = {
            "status": "warned",
            "hook": "flow_guard",
            "reason": "pipeline_owned_artifact",
            "path": rel,
            "ts": now_iso(),
            "tool": tool_name,
        }
        _audit_warn(project_dir, record)
        print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
        return 0

    try:
        if _worker_in_flight(config):
            # Correlation gap: cannot attribute the calling session while a
            # worker is live — allow (documented residual; see module docstring).
            return 0
    except Exception:  # noqa: BLE001
        return 0  # fail-open: a broken reducer must not brick spec work

    return _deny({
        "status": "blocked",
        "hook": "flow_guard",
        "reason": "pipeline_owned_artifact",
        "path": rel,
        "policy": (
            "spec artifacts and handoff-manifest.yaml are produced only by pipeline "
            "workers under an active claim (triage -> writer -> reviewer -> validator); "
            "a direct edit bypasses validation and poisons the dev phase with an "
            "unreviewed spec"
        ),
        "action": (
            'run /u-improve <workflow_id> "<change description>" to route this change '
            "through the spec pipeline; for a brand-new domain or feature run /u-spec"
        ),
        "known_workflows": _known_workflows(project_dir),
        "human_override": (
            'a human operator may set {"guard": {"enforce": "warn"}} (or "off") in '
            ".orch/config.json — do not do this on the user's behalf"
        ),
    })


if __name__ == "__main__":
    sys.exit(main())
