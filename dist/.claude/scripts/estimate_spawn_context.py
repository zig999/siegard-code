#!/usr/bin/env python3
"""
estimate_spawn_context.py — What context will this worker actually receive?

The number this replaces was wrong by 3–7×, and wrong in the direction that
blocks work. `orchestrator-sdd` Step 5.2.5 told the orchestrator to "treat as
fixed ~18000 tokens" the skill content a spec worker loads. Measured against the
files the workers actually read:

    u-spec-back       2,437 tokens   heuristic 18,000   -87%
    u-spec-validator  2,869          heuristic 18,000   -85%
    u-spec-reviewer   3,535          heuristic 18,000   -81%
    u-spec-writer     6,668          heuristic 18,000   -63%

Across the four measured workflows that is **461,759 phantom tokens — 40% of the
1,149,494 reported**. The `u-spec-back` spawn recorded at 57,213 (95% of the
60,000 ceiling) is really 41,650 (69%).

Where the error came from, because it is instructive: the F6 fix reasoned that a
worker "does not load one skill — it pulls its capability SKILL.md plus the
templates it reads by path plus the globals", and raised 6,000 to 18,000. The
reasoning was right; the arithmetic assumed **bundle-scale** loading. The
`u-spec-templates` bundle alone is 108 KB (~27k tokens), so bundle-scale would
have been 30–35k, not 18,000 — and path-scoped reading is 2–7k. 18,000 is a
midpoint between two behaviours, matching neither. The spec agents declare only
`orch-report` in `skills:`; everything else is read by path, file by file. That is
checkable in one grep, and the same failure class R04 exists to prevent — a
verifiable claim about the system, asserted without opening the files.

So this script does not carry a constant. It **derives** the payload from each
worker's own declared Expected Inputs, which means it follows the worker when the
worker changes, instead of drifting away from it.

Usage:
    python3 estimate_spawn_context.py --worker u-spec-back \\
        [--spec-file <path>] [--requirement-chars N] [--phase sdd]

Output (stdout, JSON, exit 0):
    {
      "worker": "<name>", "phase": "<phase>",
      "estimated_tokens": int,
      "breakdown": {"base_prompt": int, "worker_inputs": int,
                    "requirement": int, "spec_file": int},
      "worker_input_files": [{"path": "...", "tokens": int}],
      "missing_inputs": ["..."],
      "threshold_warn": int, "threshold_block": int,
      "mitigation": "none" | "monitor" | "blocked"
    }

Exit codes:
    0  estimate produced (mitigation none/monitor)
    3  mitigation == blocked — caller MUST NOT spawn
    1  usage/internal error
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[1]

# The orchestrator's own spawn template. Small, stable, and the one genuinely
# fixed part of a spawn.
BASE_PROMPT_TOKENS = 1500

# Chars per token. Crude but consistent with how every other estimate here is
# expressed; the point of this script is to stop inventing the INPUTS, not to
# improve the tokenizer.
CHARS_PER_TOKEN = 4

# Per-phase thresholds, mirroring the orchestrators. Kept here so a caller gets
# the policy with the estimate instead of re-deriving it from prose.
THRESHOLDS = {
    "sdd": (30000, 60000),
    "dev": (40000, 50000),
    "review": (20000, 25600),
    "test": (30000, 60000),
}


def _config_thresholds(phase: str) -> tuple[int, int]:
    """Per-phase thresholds, config-overridable (v2.36.0).

    .orch/config.json:
        {"context_budget": {"thresholds": {"sdd": {"warn": 30000, "block": 60000}}}}

    Field lesson (mwoassistant): a 234KB spec estimated 6% over the hardcoded
    block threshold and the workflow dead-ended in DLQ — the operator had no
    lever short of patching this file. Hardcoded values remain the defaults."""
    warn, block = THRESHOLDS.get(phase, THRESHOLDS["sdd"])
    cfg_path = Path(os.environ.get("ORCH_PROJECT_DIR", ".")) / ".orch" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        ph = ((cfg.get("context_budget") or {}).get("thresholds") or {}).get(phase) or {}
        warn = int(ph.get("warn", warn))
        block = int(ph.get("block", block))
    except Exception:  # noqa: BLE001 — absent/broken config keeps defaults
        pass
    return warn, block


def _section_tokens(spec_path: Path, sections: str) -> int | None:
    """Token estimate for ONLY the requested sections (R16, v2.36.0).

    Delegates to read_spec_sections.py — the same scoping the workers use, so
    the estimate and the worker's actual read can never diverge. Returns None
    (caller falls back to whole-file, the conservative floor) when extraction
    fails or any selector goes unmatched — a silent partial match would
    UNDER-estimate, which is the direction that overflows workers."""
    import subprocess
    reader = _CLAUDE_DIR / "skills" / "u-spec-templates" / "scripts" / "read_spec_sections.py"
    if not reader.is_file():
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(reader), "--file", str(spec_path), "--sections", sections],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        out = json.loads(proc.stdout)
        if out.get("unmatched_selectors"):
            return None
        return len(out.get("content", "")) // CHARS_PER_TOKEN
    except Exception:  # noqa: BLE001
        return None

# Framework paths a worker declares in its Expected Inputs. Project artifacts
# (`{SPECS_DIR}/...`, `domains/...`) are counted separately via --spec-file,
# because their size depends on the project, not on the framework.
_FRAMEWORK_INPUT_RE = re.compile(r"`(\.claude/[^`]+)`")

_AGENT_DIRS = ("agents/spec", "agents/dev", "agents", "agents/reverse-spec")


def find_worker(worker: str) -> Path | None:
    for d in _AGENT_DIRS:
        candidate = _CLAUDE_DIR / d / f"{worker}.md"
        if candidate.is_file():
            return candidate
    return None


def declared_framework_inputs(worker_md: Path) -> tuple[list[str], str]:
    """(framework paths, source) from the worker's own Expected Inputs section.

    Derived, not tabulated: adding an input to a worker changes its estimate
    automatically. A hardcoded table is what drifted last time.

    A worker WITHOUT an Expected Inputs heading returns `("not_declared")` and no
    paths — deliberately, rather than falling back to scanning the whole file.
    That fallback is how the first cut of this script reported 10,882 tokens for
    `u-be-developer` by summing every `.claude/` path the document *mentions*,
    including a prose reference to a feedback protocol and one path that does not
    exist. Over-estimating is the direction that blocks work, which is the exact
    defect being fixed here; guessing high is not a safer failure than admitting
    the input is undeclared.
    """
    text = worker_md.read_text(encoding="utf-8")
    m = re.search(r"^##+\s*Expected Inputs\s*$(.*?)(?=^##+\s)", text,
                  re.MULTILINE | re.DOTALL)
    if not m:
        return [], "not_declared"
    seen: list[str] = []
    for path in _FRAMEWORK_INPUT_RE.findall(m.group(1)):
        # Templates/skills only. A worker also cites scripts it RUNS; running a
        # script does not load it into context.
        if "/scripts/" in path:
            continue
        if path not in seen:
            seen.append(path)
    return seen, "declared"


def _tokens_for(path: str) -> tuple[int, bool]:
    target = _CLAUDE_DIR / path[len(".claude/"):] if path.startswith(".claude/") else _CLAUDE_DIR / path
    if target.is_file():
        return target.stat().st_size // CHARS_PER_TOKEN, True
    if target.is_dir():
        total = sum(f.stat().st_size for f in target.rglob("*")
                    if f.is_file() and "__pycache__" not in str(f))
        return total // CHARS_PER_TOKEN, True
    return 0, False


def estimate(worker: str, phase: str, spec_file: str | None,
             requirement_chars: int, sections: str | None = None) -> dict:
    worker_md = find_worker(worker)
    if worker_md is None:
        raise FileNotFoundError(f"worker definition not found: {worker}")

    declared, inputs_source = declared_framework_inputs(worker_md)
    files: list[dict] = []
    missing: list[str] = []
    worker_inputs = 0
    for path in declared:
        tokens, ok = _tokens_for(path)
        if not ok:
            missing.append(path)
            continue
        files.append({"path": path, "tokens": tokens})
        worker_inputs += tokens

    spec_tokens = 0
    sections_applied = False
    if spec_file:
        p = Path(spec_file)
        if p.is_file():
            spec_tokens = p.stat().st_size // CHARS_PER_TOKEN
            if sections:
                scoped = _section_tokens(p, sections)
                if scoped is not None:
                    spec_tokens = scoped
                    sections_applied = True

    requirement_tokens = max(0, requirement_chars) // CHARS_PER_TOKEN
    total = BASE_PROMPT_TOKENS + worker_inputs + requirement_tokens + spec_tokens

    warn, block = _config_thresholds(phase)
    if total >= block:
        mitigation = "blocked"
    elif total >= warn:
        mitigation = "monitor"
    else:
        mitigation = "none"

    return {
        "worker": worker,
        "phase": phase,
        "estimated_tokens": total,
        "breakdown": {
            "base_prompt": BASE_PROMPT_TOKENS,
            "worker_inputs": worker_inputs,
            "requirement": requirement_tokens,
            "spec_file": spec_tokens,
        },
        "worker_input_files": files,
        "missing_inputs": missing,
        # "not_declared" means the worker has no Expected Inputs heading, so
        # `worker_inputs` is 0 by admission rather than by measurement. The caller
        # must treat the total as a floor, never as grounds to block.
        "inputs_source": inputs_source,
        "threshold_warn": warn,
        "threshold_block": block,
        "mitigation": mitigation,
        # R16 (v2.36.0): True when spec_file was estimated section-scoped —
        # the caller uses this to know a blocked whole-file estimate can still
        # be retried with --sections before declaring the task dead.
        "sections_applied": sections_applied,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", required=True,
                    help="worker name, e.g. u-spec-back")
    ap.add_argument("--phase", default="sdd", choices=sorted(THRESHOLDS))
    ap.add_argument("--spec-file", default=None,
                    help="project artifact passed as task.spec")
    ap.add_argument("--requirement-chars", type=int, default=0,
                    help="len(triage.requirement)")
    ap.add_argument("--sections", default=None,
                    help="comma-separated section selectors (R16) — estimate only "
                         "these sections of --spec-file, matching what a "
                         "section-scoped worker will actually read")
    args = ap.parse_args()

    result = estimate(args.worker, args.phase, args.spec_file,
                      args.requirement_chars, args.sections)
    print(json.dumps(result))
    sys.exit(3 if result["mitigation"] == "blocked" else 0)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(json.dumps({
            "status": "error", "reason": "worker_not_found", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
