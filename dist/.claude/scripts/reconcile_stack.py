#!/usr/bin/env python3
"""reconcile_stack.py — recompute the front/back decision from the recorded inputs.

`triage.json` records both the stack decision and the inputs it was derived from
(`requirement`, `affected_specs`). A decision that can be recomputed from data in
the log should not depend on a worker having followed a prose step — that is the
failure this script closes.

The measured case: a backend-only `/u-improve` whose description uses domain
vocabulary ("refatorar a FSM", "remover o campo X") contains no term from either
signal list, so `classify_stack.py` sees no signals and applies its conservative
`fullstack` default. The front leg is dispatched (spec-front + front validator,
2 workers) against a repository with no front specs at all, and `/u-improve` sets
`bypass_e99`, so the `force_backend_only` correction is never offered. Triage
Step 2.1b re-runs the classifier with `--affected-specs` to prevent exactly this —
but a step the worker can skip is a guarantee the engine does not have.

Scope, deliberately narrow — this reconciles ONE transition, `fullstack -> be`:

  - `fullstack` is the only value the conservative default can produce, so it is
    the only one that can be an evidence-free guess. `fe` and `be` always rest on
    a real signal and are left untouched.
  - Restricting to `fullstack` also makes the recomputation faithful WITHOUT
    knowing the target's declared `domain:` (which triage.json does not record):
    `--project-domain` only ever moves a decision AWAY from `fullstack`, so a
    recorded `fullstack` is never the product of a domain override.
  - `stack_refinement == "human_override"` is never touched. An operator who
    answered the E99 gate outranks every classifier.

Usage:
    reconcile_stack.py --triage <path/to/triage.json> [--dry-run]

Output (stdout, JSON, exit 0):
    {"status": "reconciled", "from": "fullstack", "to": "be", "reason": "..."}
    {"status": "consistent", "stack": "be"}
    {"status": "skipped", "reason": "human_override" | "greenfield" | ...}

Exit codes:
    0  inspected (any status above)
    1  usage/IO error — the caller must treat this as "stack unverified", never
       as "stack confirmed"
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_CLASSIFIER = (Path(__file__).resolve().parent.parent
               / "skills" / "u-spec-triage-rules" / "scripts" / "classify_stack.py")


def _load_classifier():
    """Import classify_stack.py by path — one implementation, never a copy."""
    spec = importlib.util.spec_from_file_location("classify_stack", _CLASSIFIER)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"classifier not found: {_CLASSIFIER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reconcile(triage: dict) -> dict:
    """Pure function: triage envelope -> reconciliation verdict (+ patch)."""
    if triage.get("stack_refinement") == "human_override":
        return {"status": "skipped", "reason": "human_override"}
    if triage.get("greenfield") is True:
        return {"status": "skipped", "reason": "greenfield"}

    recorded = triage.get("stack")
    if recorded != "fullstack":
        return {"status": "skipped", "reason": "stack_not_fullstack",
                "stack": recorded}

    affected = triage.get("affected_specs") or []
    if not affected:
        return {"status": "skipped", "reason": "no_affected_specs"}

    result = _load_classifier().classify(
        triage.get("requirement") or "", None, affected)

    if result["stack"] != "be":
        return {"status": "consistent", "stack": recorded}

    return {
        "status": "reconciled",
        "from": recorded,
        "to": "be",
        "reason": result["rationale"],
        "patch": {
            "stack": "be",
            "ui_task": False,
            "stack_confidence": result["confidence"],
            "stack_confidence_hint": result["confidence_hint"],
            "stack_refinement": "fullstack->be (reconciled)",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recompute the triage stack decision from its recorded inputs.")
    ap.add_argument("--triage", required=True, help="path to triage.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the verdict without rewriting triage.json")
    args = ap.parse_args()

    path = Path(args.triage)
    try:
        triage = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "reason": "triage_unreadable",
                          "detail": str(exc)}), file=sys.stderr)
        return 1
    if not isinstance(triage, dict):
        print(json.dumps({"status": "error", "reason": "triage_unreadable",
                          "detail": "triage.json is not an object"}), file=sys.stderr)
        return 1

    verdict = reconcile(triage)
    patch = verdict.pop("patch", None)

    if patch and not args.dry_run:
        triage.update(patch)
        path.write_text(json.dumps(triage, indent=2), encoding="utf-8")

    print(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — surface a parseable error, never crash silently
        print(json.dumps({"status": "error", "reason": "internal_error",
                          "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
