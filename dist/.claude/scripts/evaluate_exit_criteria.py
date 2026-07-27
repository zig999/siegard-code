#!/usr/bin/env python3
"""
evaluate_exit_criteria.py — Run a phase's exit-criteria checkers and record the
verdict, deterministically, outside the LLM.

Why this exists. `orchestrator-test` once emitted
`phase_exit_criterion_met {"criterion": "all_tests_passed"}` and transitioned the
workflow to `done` while `check_all_tests_passed.py`, run against the artifact
the worker had actually registered, returned `met: false` and exit 1. The checker
was already fail-closed; the orchestrator simply did not honour it. Prose asking
an agent to respect an exit code is not a gate — P7 puts critical guarantees
outside the LLM and P11 puts exit criteria in testable code.

So the decision and the recording both move here. The orchestrator reads one
verdict and routes; it no longer composes the per-criterion events.

`phase_exit_approved` deliberately stays with the orchestrator: in `sdd` and
`review` it follows a human gate (E99), which is policy, not measurement. What
this script owns is the mechanical half — "did each checker pass, and is that
faithfully in the log".

Criteria come from `phase-{phase}-rules/exit-criteria.json`, so the set is never
hand-listed here.

Usage:
    python3 evaluate_exit_criteria.py --phase sdd|dev|review|test
                                      [--workflow-id <wid>] [--mode <mode>]
                                      [--dry-run]

Output (stdout, always JSON):
    {
      "phase": "<phase>",
      "verdict": "all_met" | "blocked",
      "criteria": [
        {"id": "...", "script": "...", "exit_code": 0, "met": true,
         "emitted_seq": 42, "evidence": {...}}
      ],
      "failing": ["<criterion id>", ...],
      "emitted": ["<criterion id>", ...],
      "skipped_not_applicable": ["<criterion id>", ...]
    }

Exit codes:
    0  all applicable criteria met (events emitted unless --dry-run)
    3  at least one criterion NOT met — nothing emitted; caller routes to E08
    1  usage/internal error
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))

VALID_PHASES = ("sdd", "dev", "review", "test")

_APPEND = _CLAUDE_DIR / "skills" / "orch-log" / "scripts" / "append.py"


def _rules_dir(phase: str) -> Path:
    return _CLAUDE_DIR / "skills" / f"phase-{phase}-rules"


def load_criteria(phase: str) -> list[dict]:
    manifest = _rules_dir(phase) / "exit-criteria.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"exit-criteria.json not found for phase {phase}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data.get("criteria", [])


def _applies(criterion: dict, mode: str | None) -> bool:
    """`applies_to_modes` absent means "always". Present means opt-in only."""
    modes = criterion.get("applies_to_modes")
    if not modes:
        return True
    if mode is None:
        # No mode declared: cannot rule the criterion out, so keep it. Dropping a
        # blocking criterion on missing input would be a silent weakening.
        return True
    return mode in modes


def run_checker(phase: str, criterion: dict, workflow_id: str | None,
                project_dir: str) -> dict:
    script = _rules_dir(phase) / criterion["script"]
    if not script.is_file():
        return {
            "id": criterion["id"], "script": criterion["script"],
            "exit_code": 1, "met": False,
            "evidence": {"error": "checker_script_missing", "path": str(script)},
        }

    env = {**os.environ, "ORCH_PROJECT_DIR": project_dir}
    if workflow_id:
        env["ORCH_WORKFLOW_ID"] = workflow_id

    cmd = [sys.executable, str(script)]
    # Scope-aware SDD checkers take the workflow on the CLI (fix F1).
    if workflow_id and "--workflow-id" in script.read_text(encoding="utf-8"):
        cmd += ["--workflow-id", workflow_id]

    proc = subprocess.run(cmd, cwd=project_dir, env=env,
                          capture_output=True, text=True, timeout=600)
    payload: dict = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"error": "checker_output_not_json",
                       "stdout": proc.stdout[:400]}

    # The exit code is authoritative. A checker whose payload says `met: true`
    # while exiting non-zero is treated as NOT met — the whole point of R01b is
    # that the code, not the narrative, decides.
    met = proc.returncode == 0
    return {
        "id": criterion["id"],
        "script": criterion["script"],
        "exit_code": proc.returncode,
        "met": met,
        "evidence": payload.get("evidence", payload),
    }


def emit_criterion(phase: str, result: dict, workflow_id: str | None,
                   project_dir: str) -> int | None:
    """Append `phase_exit_criterion_met` carrying its own execution evidence.

    `checker_exit` is what makes the claim falsifiable: `_validate_event_data`
    rejects this event when the field is present and non-zero, so a blocked gate
    can no longer be recorded as met (R01c).
    """
    data = {
        "phase": phase,
        "criterion": result["id"],
        "checker": result["script"],
        "checker_exit": result["exit_code"],
    }
    if workflow_id:
        data["workflow_id"] = workflow_id

    proc = subprocess.run(
        [sys.executable, str(_APPEND),
         "--agent", f"orchestrator-{phase}",
         "--event-type", "phase_exit_criterion_met",
         "--data", json.dumps(data)],
        cwd=project_dir, env={**os.environ, "ORCH_PROJECT_DIR": project_dir},
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"append.py failed for criterion {result['id']}: "
            f"{proc.stderr.strip()[:300]}"
        )
    try:
        return json.loads(proc.stdout).get("seq")
    except (json.JSONDecodeError, AttributeError):
        return None


def evaluate(phase: str, workflow_id: str | None, mode: str | None,
             project_dir: str, dry_run: bool) -> dict:
    criteria = load_criteria(phase)
    results, skipped = [], []

    for criterion in criteria:
        if not _applies(criterion, mode):
            skipped.append(criterion["id"])
            continue
        results.append(run_checker(phase, criterion, workflow_id, project_dir))

    failing = [r["id"] for r in results if not r["met"]]

    emitted: list[str] = []
    if not failing and not dry_run:
        # All-or-nothing: emitting a partial set would leave the log asserting
        # progress the phase has not made.
        for r in results:
            r["emitted_seq"] = emit_criterion(phase, r, workflow_id, project_dir)
            emitted.append(r["id"])

    return {
        "phase": phase,
        "verdict": "all_met" if not failing else "blocked",
        "criteria": results,
        "failing": failing,
        "emitted": emitted,
        "skipped_not_applicable": skipped,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=VALID_PHASES)
    ap.add_argument("--workflow-id", default=os.environ.get("ORCH_WORKFLOW_ID"))
    ap.add_argument("--mode", default=None,
                    help="effective_mode, matched against applies_to_modes")
    ap.add_argument("--project-dir",
                    default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and report without appending any event")
    args = ap.parse_args()

    project_dir = str(Path(args.project_dir).resolve())
    result = evaluate(args.phase, args.workflow_id, args.mode,
                      project_dir, args.dry_run)
    print(json.dumps(result))
    sys.exit(0 if result["verdict"] == "all_met" else 3)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — always emit JSON for the caller
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
