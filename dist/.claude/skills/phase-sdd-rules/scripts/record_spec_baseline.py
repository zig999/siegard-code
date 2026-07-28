#!/usr/bin/env python3
"""
record_spec_baseline.py — record the spec-tree adoption baseline (v2.35.0, A3').

Appends ONE spec_baseline_recorded event per workflow at sdd phase entry: a
{path: sha256} snapshot of every file under SPECS_DIR. The baseline is the
"inherited state accepted" mark for provenance validation (PROV):

  * pre-existing specs — reverse-spec drafts, pre-Siegard files, human edits
    between workflows — are legitimized by the baseline;
  * a manifest hash that matches neither the baseline nor a worker-notarized
    task_completed hash is divergence introduced DURING the workflow by
    something that is not a pipeline worker (the freelance class).

Idempotent BY DESIGN, enforced against the log: if a spec_baseline_recorded
event already exists for this workflow_id, the script is a no-op. This is a
correctness requirement, not a convenience — orchestrator re-invocation
(resume) re-runs phase-entry steps, and re-baselining mid-workflow would bless
whatever is on disk at that moment, freelance edits included.

Payloads above the inline limit are externalized automatically by append_event
(blob storage) — large spec trees are fine.

Usage:
    python3 record_spec_baseline.py --workflow-id <wid>

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs dir relative to project root (default: specs)

Output: {"status": "recorded" | "exists" | "skipped", ...} on stdout.
Exit 0 on recorded/exists/skipped (missing specs dir is not an error at entry
of a greenfield workflow); exit 1 on internal error.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from orch_core import (  # noqa: E402
    EventType,
    append_event,
    claude_md_specs_dir,
    load_blob_data,
    read_events,
    resolve_specs_dir,
)


def _existing_baseline_seq(workflow_id: str) -> int | None:
    for event in read_events():
        if event.event_type != EventType.SPEC_BASELINE_RECORDED.value:
            continue
        data = event.data
        try:
            from orch_core import is_blob_ref
            if is_blob_ref(data):
                data = load_blob_data(event)
        except Exception:  # noqa: BLE001
            pass
        if data.get("workflow_id") == workflow_id:
            return event.seq
    return None


def _snapshot(project_dir: Path, specs_dir: Path) -> dict[str, str]:
    """{project-relative posix path: sha256(raw bytes)} for every file in the tree.

    Raw bytes, same convention as emit.py notarization and the handoff
    generator — the three must never diverge.
    """
    artifacts: dict[str, str] = {}
    for f in sorted(specs_dir.rglob("*")):
        if not f.is_file():
            continue
        try:
            key = f.resolve().relative_to(project_dir.resolve()).as_posix()
        except ValueError:
            key = f.as_posix()
        artifacts[key] = hashlib.sha256(f.read_bytes()).hexdigest()
    return artifacts


def main() -> int:
    ap = argparse.ArgumentParser(description="Record the spec adoption baseline (stdlib only).")
    ap.add_argument("--workflow-id", required=True)
    args = ap.parse_args()

    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    # v2.35.1: canonical resolution (config override > CLAUDE.md machine-parsed
    # > env > default), shared with flow_guard/generator/checkers. The v2.35.0
    # field incident recorded an EMPTY baseline against env-default "specs"
    # while CLAUDE.md declared docs/specs — never resolve from env alone.
    specs_rel = resolve_specs_dir(project_dir)
    specs_dir = project_dir / specs_rel

    existing = _existing_baseline_seq(args.workflow_id)
    if existing is not None:
        print(json.dumps({
            "status": "exists",
            "workflow_id": args.workflow_id,
            "baseline_seq": existing,
            "note": "baseline is once-per-workflow; re-entry must not re-bless the tree",
        }))
        return 0

    if not specs_dir.is_dir():
        # Greenfield: no spec tree yet. Record an EMPTY baseline — every spec
        # file at handoff must then be worker-notarized, which is exactly right.
        artifacts: dict[str, str] = {}
    else:
        artifacts = _snapshot(project_dir, specs_dir)

    # Brownfield-poisoning guard (v2.35.1): an empty baseline is only legitimate
    # when the canonical spec tree genuinely holds no files. If resolution ever
    # regresses again, the empty snapshot would PERMANENTLY poison PROV for this
    # workflow (once-per-workflow idempotency blocks re-recording) — so when the
    # snapshot is empty but the CLAUDE.md-declared tree has files elsewhere,
    # abort loudly instead of recording.
    if not artifacts:
        declared = claude_md_specs_dir(project_dir)
        if declared and declared != specs_rel:
            declared_dir = project_dir / declared
            if declared_dir.is_dir() and any(f.is_file() for f in declared_dir.rglob("*")):
                print(json.dumps({
                    "status": "error",
                    "reason": "specs_dir_resolution_mismatch",
                    "detail": (
                        f"refusing to record an EMPTY baseline against {specs_rel!r} while "
                        f"CLAUDE.md declares a populated specs_dir {declared!r} — an empty "
                        "baseline in a brownfield project poisons PROV for the whole workflow"
                    ),
                }), file=sys.stderr)
                return 1

    event = append_event(
        agent="spec-baseline",
        event_type=EventType.SPEC_BASELINE_RECORDED.value,
        data={
            "workflow_id": args.workflow_id,
            "phase": "sdd",
            "specs_dir": specs_rel,
            "artifacts": artifacts,
            "file_count": len(artifacts),
        },
    )
    print(json.dumps({
        "status": "recorded",
        "workflow_id": args.workflow_id,
        "baseline_seq": event.seq,
        "file_count": len(artifacts),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
