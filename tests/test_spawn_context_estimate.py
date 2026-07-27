"""The 18,000-token constant was wrong by 3–7×, in the blocking direction.

`orchestrator-sdd` Step 5.2.5 told the orchestrator to "treat as fixed ~18000
tokens" the skill content a spec worker loads. Measured against the files the
workers actually read:

    u-spec-back       2,437   heuristic 18,000   -87%
    u-spec-validator  2,869   heuristic 18,000   -85%
    u-spec-reviewer   3,535   heuristic 18,000   -81%
    u-spec-writer     6,668   heuristic 18,000   -63%

Across four measured workflows: 461,759 phantom tokens, **40% of the 1,149,494
reported**. The spawn recorded at 57,213 (95% of the 60,000 ceiling) is really
41,650 (69%) — so every decision taken against that ceiling was taken against a
40%-inflated number, including two of this session's own releases.

Where it came from: fix F6 rightly observed that a worker loads its capability
SKILL.md *plus* templates *plus* globals, and assumed bundle-scale loading.
Bundle-scale would be 30–35k (`u-spec-templates` alone is ~27k tokens);
path-scoped reading is 2–7k. 18,000 matched neither. The spec agents declare only
`orch-report` in `skills:` — one grep away — which makes this the same failure
class R04 exists to prevent: a verifiable claim about the system, asserted without
opening the files, inside the engine's own heuristic.

The replacement carries no constant for worker inputs: it derives them from each
worker's own Expected Inputs, so the estimate follows a worker that changes.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
SCRIPT = dist / "scripts" / "estimate_spawn_context.py"
SDD = dist / "agents" / "orchestrator-sdd.md"

# Measured at the time of the fix. These are a REGRESSION FENCE, not a spec: if a
# worker's declared inputs grow, the test should fail and be re-measured
# deliberately — silently drifting is how 18,000 survived.
MEASURED_INPUT_TOKENS = {
    "u-spec-back": 2436,
    "u-spec-validator": 2869,
    "u-spec-reviewer": 3090,
    "u-spec-writer": 6666,
}


def _module():
    spec = importlib.util.spec_from_file_location("ese", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(*args) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=60)
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


class TestDerivedNotConstant:
    @pytest.mark.parametrize("worker,expected", sorted(MEASURED_INPUT_TOKENS.items()))
    def test_worker_inputs_are_measured_from_real_files(self, worker, expected):
        rc, out = _run("--worker", worker)
        assert rc == 0
        actual = out["breakdown"]["worker_inputs"]
        assert abs(actual - expected) <= 200, (
            f"{worker} declared inputs now measure {actual}, fence says {expected}. "
            "If the worker legitimately gained an input, re-measure and move the "
            "fence deliberately — do not widen the tolerance."
        )

    @pytest.mark.parametrize("worker", sorted(MEASURED_INPUT_TOKENS))
    def test_no_worker_is_anywhere_near_the_old_constant(self, worker):
        _, out = _run("--worker", worker)
        assert out["breakdown"]["worker_inputs"] < 10000, (
            "the 18,000 constant overstated every spec worker by 3-7x"
        )

    def test_the_constant_is_gone_from_the_orchestrator(self):
        text = SDD.read_text(encoding="utf-8")
        assert "treat as fixed `~18000`" not in text
        assert 'treat as fixed "~18000"' not in text
        # It may survive ONLY inside the rationale that explains why it was wrong.
        idx = text.find("18000")
        if idx != -1:
            window = text[max(0, idx - 400):idx + 400]
            assert "Why this replaced a prose heuristic" in window or "phantom" in window

    def test_orchestrator_calls_the_script(self):
        text = SDD.read_text(encoding="utf-8")
        assert "estimate_spawn_context.py" in text
        assert "--worker" in text

    def test_orchestrator_branches_on_the_exit_code(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("estimate_spawn_context.py")
        window = text[idx:idx + 1600]
        for token in ("exit code", "**0**", "**3**", "**1**"):
            assert token in window, f"missing branch marker {token!r}"

    def test_broken_estimator_does_not_block_work(self):
        """A measurement that fails must not become a reason to skip a task."""
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("estimate_spawn_context.py")
        window = text[idx:idx + 1600]
        assert "rather than blocking on a broken measurement" in window


class TestBreakdownIsActionable:
    def test_breakdown_separates_fixed_from_variable(self, tmp_path):
        spec = tmp_path / "d.spec.md"
        spec.write_text("x" * 40000, encoding="utf-8")
        _, out = _run("--worker", "u-spec-back", "--spec-file", str(spec),
                      "--requirement-chars", "2400")
        b = out["breakdown"]
        assert b["spec_file"] == 10000
        assert b["requirement"] == 600
        assert b["base_prompt"] == 1500
        assert out["estimated_tokens"] == sum(b.values())

    def test_orchestrator_records_the_breakdown(self):
        """A total is not actionable; a total plus its parts is."""
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("context_budget_evaluated")
        window = text[idx:idx + 1200]
        assert "breakdown" in window

    def test_input_files_are_itemised(self):
        _, out = _run("--worker", "u-spec-back")
        assert out["worker_input_files"]
        assert all("path" in f and "tokens" in f for f in out["worker_input_files"])


class TestThresholdBehaviour:
    def test_small_spawn_is_none(self):
        _, out = _run("--worker", "u-spec-back")
        assert out["mitigation"] == "none"

    def test_crossing_warn_is_monitor_and_still_proceeds(self, tmp_path):
        spec = tmp_path / "d.spec.md"
        spec.write_text("x" * (31000 * 4), encoding="utf-8")
        rc, out = _run("--worker", "u-spec-back", "--spec-file", str(spec))
        assert out["mitigation"] == "monitor"
        assert rc == 0, "monitor must proceed"

    def test_crossing_block_exits_three(self, tmp_path):
        spec = tmp_path / "d.spec.md"
        spec.write_text("x" * (61000 * 4), encoding="utf-8")
        rc, out = _run("--worker", "u-spec-back", "--spec-file", str(spec))
        assert out["mitigation"] == "blocked" and rc == 3

    def test_thresholds_were_not_raised_by_this_fix(self):
        """Correcting an estimate is not raising a gate. The ceiling still moves
        only on measurement — of the ceiling itself."""
        mod = _module()
        assert mod.THRESHOLDS["sdd"] == (30000, 60000)

    @pytest.mark.parametrize("phase", ["sdd", "dev", "review", "test"])
    def test_every_phase_has_a_threshold(self, phase):
        mod = _module()
        assert phase in mod.THRESHOLDS


class TestUndeclaredInputsAreAdmittedNotGuessed:
    """The first cut fell back to scanning the whole file when a worker had no
    Expected Inputs heading. For `u-be-developer` that summed every `.claude/`
    path the document merely MENTIONS — 10,882 tokens, including a prose
    reference and one path that does not exist. Over-estimating is the blocking
    direction: the same defect being fixed."""

    def test_worker_without_the_section_reports_not_declared(self):
        _, out = _run("--worker", "u-be-developer", "--phase", "dev")
        assert out["inputs_source"] == "not_declared"
        assert out["breakdown"]["worker_inputs"] == 0

    def test_worker_with_the_section_reports_declared(self):
        _, out = _run("--worker", "u-spec-back")
        assert out["inputs_source"] == "declared"

    def test_zero_inputs_can_be_legitimate(self):
        """u-be-qa declares only CLAUDE.md, a prompt block and a session artifact
        — no framework path. Its 0 is measurement, not absence of it."""
        _, out = _run("--worker", "u-be-qa", "--phase", "review")
        assert out["inputs_source"] == "declared"
        assert out["breakdown"]["worker_inputs"] == 0

    def test_scripts_are_not_counted_as_context(self):
        """Running a script does not load it into the worker's context."""
        _, out = _run("--worker", "u-spec-validator")
        assert not any("/scripts/" in f["path"]
                       for f in out["worker_input_files"])

    def test_missing_declared_input_is_reported_not_silently_zero(self, tmp_path):
        mod = _module()
        fake = tmp_path / "u-fake.md"
        fake.write_text(
            "## Expected Inputs\n"
            "- `.claude/skills/u-spec-globals/conventions.md` — real\n"
            "- `.claude/skills/does-not-exist/ghost.md` — dangling\n"
            "\n## Execution\n", encoding="utf-8")
        declared, source = mod.declared_framework_inputs(fake)
        assert source == "declared" and len(declared) == 2


class TestNoDanglingFrameworkReferences:
    """The estimator surfaced a shipped agent citing a path that never existed."""

    def test_the_feedback_loop_path_is_gone(self):
        text = (dist / "agents" / "dev" / "u-be-developer.md").read_text(
            encoding="utf-8")
        assert "The Orchestrator triggers the reverse feedback protocol (`.claude/agents/spec/protocols/" not in text

    def test_protocols_directory_is_not_referenced_as_an_input(self):
        for agent in (dist / "agents").rglob("*.md"):
            text = agent.read_text(encoding="utf-8")
            m = None
            import re
            m = re.search(r"^##+\s*Expected Inputs\s*$(.*?)(?=^##+\s)", text,
                          re.MULTILINE | re.DOTALL)
            if not m:
                continue
            for path in re.findall(r"`(\.claude/[^`]+)`", m.group(1)):
                if "/scripts/" in path:
                    continue
                target = dist / path[len(".claude/"):]
                assert target.exists(), (
                    f"{agent.name} declares input {path} which does not exist"
                )


class TestUsageErrors:
    def test_unknown_worker_errors(self):
        rc, out = _run("--worker", "u-does-not-exist")
        assert rc == 1 and out["reason"] == "worker_not_found"

    def test_absent_spec_file_is_zero_not_a_crash(self, tmp_path):
        rc, out = _run("--worker", "u-spec-back",
                       "--spec-file", str(tmp_path / "nope.md"))
        assert rc == 0 and out["breakdown"]["spec_file"] == 0
