#!/usr/bin/env python3
"""
check_spec_entry.py — Entry guard for `/u-spec`: is this repository greenfield?

`/u-spec` builds EVERY domain. That is correct on an empty repository and
catastrophic on a populated one: `scope.py` returns `scoped: false` for the
`u-spec` trigger, so `orchestrator-sdd` dispatches the full
writer -> reviewer -> back -> validator pipeline for every domain it scans, not
just the one the requirement is about.

Measured consequence on a 7-domain repository: 28 domain tasks plus the front
leg and compliance, dispatched at most 2 at a time. At the observed ~6 min of
wall clock per worker that is several hours, and it exceeds the per-session
subagent spawn budget long before it finishes — the run dies mid-pipeline with
no terminal event. The operator's reasonable reading of that is "`/u-spec` does
not work here".

Adding a domain to an existing project is `/u-improve`: triage records it in
`affected_specs` and `scope.py` confines the pipeline to it.

This guard is deterministic and runs BEFORE any event is appended, so a blocked
entry costs nothing.

Usage:
    python3 check_spec_entry.py --specs-dir <dir> [--project-dir <dir>]

Output (stdout, always JSON):
    {
      "entry": "greenfield" | "non_greenfield",
      "domain_count": int,
      "domains": ["<slug>", ...],
      "projected": {"workers": int, "wall_clock_minutes": int}
    }

Exit codes:
    0  greenfield — safe to proceed
    3  non_greenfield — caller MUST stop unless the human explicitly opted into
       a full re-spec of every domain
    1  usage/IO error
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Observed cost per dispatched worker across three real workflows (5.6, 5.9 and
# 6.9 min/worker over differing modes, domain counts and change sizes). Used to
# turn the projection into minutes the operator can act on, not a task count
# whose price is invisible until it has been paid.
WALL_CLOCK_MINUTES_PER_WORKER = 6

# Back leg per domain: spec-writer -> spec-reviewer -> spec-back -> spec-validator.
BACK_LEG_STAGES_PER_DOMAIN = 4
# Global, dispatched once regardless of domain count: triage + compliance.
GLOBAL_WORKERS = 2


def find_domains(specs_dir: Path) -> list[str]:
    """Domain slugs that already carry a spec — the same predicate triage uses.

    A directory under `domains/` counts only when it holds an `openapi.yaml` or
    a `*.spec.md`; an empty or scaffolded directory is not a spec.
    """
    domains_root = specs_dir / "domains"
    if not domains_root.is_dir():
        return []
    found = []
    for child in sorted(domains_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "openapi.yaml").is_file() or any(child.glob("*.spec.md")):
            found.append(child.name)
    return found


def project_cost(domain_count: int) -> dict:
    workers = domain_count * BACK_LEG_STAGES_PER_DOMAIN + GLOBAL_WORKERS
    return {
        "workers": workers,
        "wall_clock_minutes": workers * WALL_CLOCK_MINUTES_PER_WORKER,
    }


def evaluate(specs_dir: Path) -> dict:
    domains = find_domains(specs_dir)
    return {
        "entry": "greenfield" if not domains else "non_greenfield",
        "domain_count": len(domains),
        "domains": domains,
        "projected": project_cost(len(domains)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs-dir", required=True)
    ap.add_argument("--project-dir",
                    default=os.environ.get("ORCH_PROJECT_DIR", "."))
    args = ap.parse_args()

    specs_dir = Path(args.specs_dir)
    if not specs_dir.is_absolute():
        specs_dir = Path(args.project_dir) / specs_dir

    result = evaluate(specs_dir)
    result["specs_dir"] = str(specs_dir)
    print(json.dumps(result))
    sys.exit(0 if result["entry"] == "greenfield" else 3)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — always emit JSON for the caller
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
