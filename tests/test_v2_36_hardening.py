"""v2.36.0 hardening — the four field lessons from the mwoassistant run.

  1. Context budget: thresholds config-overridable + section-scoped estimates
     (a 234KB spec 6%% over the hardcoded ceiling dead-ended in DLQ with no
     operator lever; the reviewer path was section-scoped, spec-back was not)
  2. E26 liveness gate: recovery_tick fired "workflow left unattended" 107s
     after a live orchestrator's dispatch in another session
  3. summary.py stale-escalation flag: an old escalation must not headline as
     a live blocker when activity continued after it
  4. preflight soft checks: flow_guard wiring + template_version drift become
     preflight output instead of forensic investigations
"""
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
_SCRIPTS = dist / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import orch_core  # noqa: E402

_spec_est = importlib.util.spec_from_file_location(
    "estimate_ctx_under_test", _SCRIPTS / "estimate_spawn_context.py")
est = importlib.util.module_from_spec(_spec_est)
_spec_est.loader.exec_module(est)

import preflight  # noqa: E402
import recovery_tick  # noqa: E402


def _isolate_orch(tmp_path, monkeypatch):
    base = tmp_path / ".orch"
    paths = {
        "ORCH_DIR": base, "LOG_PATH": base / "log.jsonl",
        "LOCK_PATH": base / "log.jsonl.lock", "STATE_DIR": base / "state",
        "DLQ_DIR": base / "dlq", "AUDIT_DIR": base / "audit",
        "METRICS_DIR": base / "metrics", "BLOBS_DIR": base / "blobs",
        "WORKERS_DIR": base / "workers", "CONFIG_PATH": base / "config.json",
    }
    for name, val in paths.items():
        monkeypatch.setattr(orch_core, name, val)
    orch_core.ensure_dirs()
    return base


# ─── 1. context budget: config thresholds + sections ─────────────────────────

class TestContextBudget:
    def _big_spec(self, tmp_path, big_kb=300):
        spec = tmp_path / "big.back.md"
        spec.write_text(
            "## 1. Small\ntiny section\n\n## 2. Big\n" + ("x" * (big_kb * 1024)),
            encoding="utf-8",
        )
        return spec

    def test_default_threshold_blocks_big_spec(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        spec = self._big_spec(tmp_path)
        result = est.estimate("u-spec-back", "sdd", str(spec), 0)
        assert result["mitigation"] == "blocked"
        assert result["sections_applied"] is False

    def test_config_raises_ceiling(self, tmp_path, monkeypatch):
        """The lever the mwoassistant operator did not have."""
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        cfg = tmp_path / ".orch" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"context_budget": {"thresholds": {
            "sdd": {"warn": 90000, "block": 120000}}}}), encoding="utf-8")
        spec = self._big_spec(tmp_path)
        result = est.estimate("u-spec-back", "sdd", str(spec), 0)
        assert result["threshold_block"] == 120000
        assert result["mitigation"] != "blocked"

    def test_sections_scope_shrinks_estimate(self, tmp_path, monkeypatch):
        """R16: estimating only the affected section admits the worker that the
        whole-file estimate would kill."""
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        spec = self._big_spec(tmp_path)
        whole = est.estimate("u-spec-back", "sdd", str(spec), 0)
        scoped = est.estimate("u-spec-back", "sdd", str(spec), 0, sections="1")
        assert scoped["sections_applied"] is True
        assert scoped["breakdown"]["spec_file"] < whole["breakdown"]["spec_file"] // 100
        assert scoped["mitigation"] != "blocked"

    def test_unmatched_selector_falls_back_to_whole_file(self, tmp_path, monkeypatch):
        """A silent partial match would UNDER-estimate — the dangerous direction."""
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        spec = self._big_spec(tmp_path)
        result = est.estimate("u-spec-back", "sdd", str(spec), 0, sections="99")
        assert result["sections_applied"] is False
        assert result["mitigation"] == "blocked"

    def test_default_config_ships_thresholds(self):
        thresholds = orch_core.default_config()["context_budget"]["thresholds"]
        assert thresholds["sdd"] == {"warn": 30000, "block": 60000}


# ─── 2. E26 liveness gate ─────────────────────────────────────────────────────

def _seed_undriven_workflow():
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": "wf", "phases": [{"name": "sdd", "order": 1}]},
    )
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "sdd", "order": 1, "workflow_id": "wf"},
    )
    orch_core.append_event(
        agent="orchestrator-sdd", event_type="task_created", task_id="t1", attempt=1,
        data={"phase": "sdd", "tier": "standard", "type": "spec-writer",
              "spec": "x", "deps": []},
    )


def _escalations(base):
    lines = (base / "log.jsonl").read_text().strip().splitlines()
    return [json.loads(l) for l in lines
            if json.loads(l)["event_type"] == "escalation"]


class TestE26LivenessGate:
    def test_recent_activity_suppresses_e26(self, tmp_path, monkeypatch):
        """The field case: SessionStart in a second session while the log is
        seconds old — the driver is live elsewhere; do not cry unattended."""
        base = _isolate_orch(tmp_path, monkeypatch)
        _seed_undriven_workflow()
        result = recovery_tick.run(None, orch_core.now_iso(), dry_run=False)
        assert result.get("escalated") is None
        assert "e26_suppressed" in result
        assert _escalations(base) == []

    def test_quiet_log_still_escalates(self, tmp_path, monkeypatch):
        base = _isolate_orch(tmp_path, monkeypatch)
        _seed_undriven_workflow()
        future = (orch_core.parse_iso(orch_core.now_iso())
                  + timedelta(seconds=3600)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = recovery_tick.run(None, future, dry_run=False)
        assert result.get("escalated") == "E26_workflow_left_unattended"
        assert len(_escalations(base)) == 1

    def test_quiet_seconds_config_override(self, tmp_path, monkeypatch):
        base = _isolate_orch(tmp_path, monkeypatch)
        (base / "config.json").write_text(
            json.dumps({"recovery_policy": {"quiet_seconds": 7200}}), encoding="utf-8")
        _seed_undriven_workflow()
        future = (orch_core.parse_iso(orch_core.now_iso())
                  + timedelta(seconds=3600)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = recovery_tick.run(None, future, dry_run=False)
        assert result.get("escalated") is None  # 1h quiet < 2h threshold


# ─── 3. summary stale-escalation flag ─────────────────────────────────────────

class TestSummaryStaleEscalation:
    def test_activity_after_escalation_is_flagged(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _seed_undriven_workflow()
        orch_core.append_event(
            agent="recovery-tick", event_type="escalation",
            data={"code": "E26_workflow_left_unattended", "severity": "warning",
                  "reason": "test", "evidence": [1]},
        )
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="orchestrator_heartbeat",
            data={"phase": "sdd"},
        )
        _sum_spec = importlib.util.spec_from_file_location(
            "summary_under_test", dist / "skills" / "orch-state" / "scripts" / "summary.py")
        summary = importlib.util.module_from_spec(_sum_spec)
        _sum_spec.loader.exec_module(summary)
        summary.main()
        out = capsys.readouterr().out
        assert "E26_workflow_left_unattended" in out
        assert "stale?" in out and "activity continued" in out


# ─── 4. preflight soft checks ─────────────────────────────────────────────────

class TestPreflightSoftChecks:
    def _project(self, tmp_path, monkeypatch, *, wired=True, hook=True):
        monkeypatch.setattr(preflight, "ORCH_DIR", tmp_path / ".orch")
        claude = tmp_path / ".claude"
        (claude / "hooks").mkdir(parents=True)
        if hook:
            (claude / "hooks" / "flow_guard.py").write_text("# hook", encoding="utf-8")
        hooks_cfg = {"PreToolUse": [{"matcher": "Write|Edit", "hooks": [
            {"type": "command", "command": "python3 $CLAUDE_PROJECT_DIR/.claude/hooks/flow_guard.py"}
        ]}]} if wired else {}
        (claude / "settings.json").write_text(
            json.dumps({"hooks": hooks_cfg}), encoding="utf-8")
        return tmp_path

    def test_guard_wired_reports_ok_and_never_blocks(self, tmp_path, monkeypatch):
        self._project(tmp_path, monkeypatch)
        result = preflight.check_flow_guard_wired()
        assert result.ok is True
        assert "flow_guard" in result.reason and "warning" not in result.reason

    def test_guard_unwired_warns_but_never_blocks(self, tmp_path, monkeypatch):
        self._project(tmp_path, monkeypatch, wired=False)
        result = preflight.check_flow_guard_wired()
        assert result.ok is True  # SOFT: surfaces, never blocks the cycle
        assert "warning" in result.reason

    def test_template_version_drift_warns(self, tmp_path, monkeypatch):
        p = self._project(tmp_path, monkeypatch)
        (p / ".claude" / "claude-md-target-template.md").write_text(
            "template_version: 2.36.0\n", encoding="utf-8")
        (p / "CLAUDE.md").write_text("specs_dir: docs/specs\n", encoding="utf-8")
        result = preflight.check_template_version()
        assert result.ok is True
        assert "warning" in result.reason and "2.36.0" in result.reason

    def test_template_version_in_sync(self, tmp_path, monkeypatch):
        p = self._project(tmp_path, monkeypatch)
        (p / ".claude" / "claude-md-target-template.md").write_text(
            "template_version: 2.36.0\n", encoding="utf-8")
        (p / "CLAUDE.md").write_text(
            "specs_dir: docs/specs\ntemplate_version: 2.36.0\n", encoding="utf-8")
        result = preflight.check_template_version()
        assert result.ok is True
        assert "in sync" in result.reason


# ─── W12 — escalation templates must not teach forgery ────────────────────────

_CW = dist / "skills" / "u-worker-compliance" / "scripts"
if str(_CW) not in sys.path:
    sys.path.insert(0, str(_CW))
import check_worker  # noqa: E402


class TestW12EscalationNoForgery:
    FORGE = (
        "```bash\npython3 .claude/skills/orch-log/scripts/append.py \\\n"
        "  --event-type escalation \\\n"
        "  --data '{\"code\":\"E13\",\"suggested_actions\":[\"resolve DLQ tasks manually via "
        "append.py task_completed events and re-invoke\"]}'\n```\n"
    )
    CLEAN = (
        "```bash\npython3 .claude/skills/orch-log/scripts/append.py \\\n"
        "  --event-type escalation \\\n"
        "  --data '{\"code\":\"E13\",\"suggested_actions\":[\"raise context_budget.thresholds "
        "in .orch/config.json and re-invoke\",\"record via respond_escalation.py\"]}'\n```\n"
    )

    def test_forge_pattern_flagged(self):
        v = check_worker._check_w12_escalation_no_forgery(self.FORGE, Path("orchestrator-x.md"))
        assert len(v) == 1 and v[0].rule == "W12" and v[0].severity == "critical"

    def test_sanctioned_actions_pass(self):
        assert not check_worker._check_w12_escalation_no_forgery(self.CLEAN, Path("orchestrator-x.md"))

    def test_every_shipped_agent_passes_w12(self):
        for agent in sorted((dist / "agents").rglob("*.md")):
            v = check_worker._check_w12_escalation_no_forgery(
                agent.read_text(encoding="utf-8"), agent)
            assert not v, f"{agent.name}: {[x.detail for x in v]}"
