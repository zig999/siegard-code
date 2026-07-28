"""Canonical specs_dir resolution (v2.35.1) — the mwoassistant field incident.

What happened: record_spec_baseline.py resolved specs_dir from env alone
(default "specs") while the target's CLAUDE.md declared `specs_dir: docs/specs`
— the orchestrator's export lived in a PREVIOUS Bash call (fresh shell each
call), so the baseline was recorded EMPTY against the wrong directory,
guaranteeing PROV-010 false positives at handoff. generate_handoff_manifest.py
and the sdd checkers carried the same latent env-default.

Three defenses, tested here:
  1. orch_core.resolve_specs_dir — ONE chain (config > CLAUDE.md > env >
     default) shared by guard, baseline, generator and checkers
  2. record_spec_baseline refuses to record an EMPTY baseline when the
     CLAUDE.md-declared tree is populated elsewhere (poisoning guard)
  3. validate.py degrades PROV to a diagnosed warning when the workflow's
     baseline was recorded against the wrong specs_dir (saves in-flight
     workflows contaminated before the fix)
Plus W11: env-dependent scripts must be invoked with inline env in agent
protocols (defense against the export-across-Bash-calls class).
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()

import orch_core  # noqa: E402

_BASELINE = dist / "skills" / "phase-sdd-rules" / "scripts" / "record_spec_baseline.py"
_VALIDATE = dist / "skills" / "u-handoff-validator" / "validate.py"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ─── 1. the shared resolver chain ─────────────────────────────────────────────

class TestResolverChain:
    def test_claude_md_wins_over_env(self, tmp_path, monkeypatch):
        (tmp_path / "CLAUDE.md").write_text("specs_dir: docs/specs\n", encoding="utf-8")
        monkeypatch.setenv("SPECS_DIR", "wrong/place")
        assert orch_core.resolve_specs_dir(tmp_path, {}) == "docs/specs"

    def test_config_override_wins_over_claude_md(self, tmp_path, monkeypatch):
        (tmp_path / "CLAUDE.md").write_text("specs_dir: docs/specs\n", encoding="utf-8")
        monkeypatch.delenv("SPECS_DIR", raising=False)
        cfg = {"guard": {"specs_dir": "other/specs"}}
        assert orch_core.resolve_specs_dir(tmp_path, cfg) == "other/specs"

    def test_env_when_no_claude_md(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECS_DIR", "my/specs")
        assert orch_core.resolve_specs_dir(tmp_path, {}) == "my/specs"

    def test_default_last(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SPECS_DIR", raising=False)
        assert orch_core.resolve_specs_dir(tmp_path, {}) == "specs"

    def test_template_placeholder_is_not_a_value(self, tmp_path, monkeypatch):
        (tmp_path / "CLAUDE.md").write_text(
            "specs_dir: {e.g. docs/specs}\n", encoding="utf-8"
        )
        monkeypatch.delenv("SPECS_DIR", raising=False)
        assert orch_core.claude_md_specs_dir(tmp_path) is None
        assert orch_core.resolve_specs_dir(tmp_path, {}) == "specs"


# ─── 2. baseline: field-incident regression + poisoning guard ─────────────────

def _run_baseline(project_dir: Path, wid: str = "wf-1", env_specs: str | None = None):
    env = {k: v for k, v in os.environ.items() if k != "SPECS_DIR"}
    env["ORCH_PROJECT_DIR"] = str(project_dir)
    if env_specs is not None:
        env["SPECS_DIR"] = env_specs
    return subprocess.run(
        [sys.executable, str(_BASELINE), "--workflow-id", wid],
        capture_output=True, text=True, env=env,
    )


class TestBaselineResolution:
    def test_field_incident_regression(self, tmp_path):
        """EXACT reproduction of mwoassistant: CLAUDE.md declares docs/specs
        (populated), no SPECS_DIR export reaches the call. Pre-fix: empty
        baseline against 'specs'. Post-fix: full baseline against docs/specs."""
        (tmp_path / "CLAUDE.md").write_text(
            "# Target\n\ndomain: backend\nspecs_dir: docs/specs\n", encoding="utf-8"
        )
        spec = tmp_path / "docs" / "specs" / "domains" / "fsm" / "back" / "fsm.back.md"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"# fsm back spec\n")
        proc = _run_baseline(tmp_path)  # note: NO SPECS_DIR in env
        result = json.loads(proc.stdout.strip())
        assert result["status"] == "recorded"
        assert result["file_count"] == 1, "baseline must see the CLAUDE.md-declared tree"
        line = (tmp_path / ".orch" / "log.jsonl").read_text().strip().splitlines()[-1]
        event = json.loads(line)
        assert event["data"]["specs_dir"] == "docs/specs"
        assert "docs/specs/domains/fsm/back/fsm.back.md" in event["data"]["artifacts"]

    def test_refuses_empty_baseline_when_declared_tree_is_populated(self, tmp_path):
        """Poisoning guard: resolution forced to an empty dir (config override)
        while CLAUDE.md declares a populated tree -> abort, record nothing."""
        (tmp_path / "CLAUDE.md").write_text("specs_dir: docs/specs\n", encoding="utf-8")
        spec = tmp_path / "docs" / "specs" / "a.spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"x")
        cfg = tmp_path / ".orch" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"guard": {"specs_dir": "empty/nowhere"}}), encoding="utf-8")
        proc = _run_baseline(tmp_path)
        assert proc.returncode == 1
        err = json.loads(proc.stderr.strip())
        assert err["reason"] == "specs_dir_resolution_mismatch"
        log = tmp_path / ".orch" / "log.jsonl"
        assert not log.exists() or "spec_baseline_recorded" not in log.read_text()

    def test_true_greenfield_still_records_empty(self, tmp_path):
        """No CLAUDE.md specs_dir, no tree anywhere: empty baseline is correct."""
        proc = _run_baseline(tmp_path)
        assert json.loads(proc.stdout.strip())["status"] == "recorded"
        assert json.loads(proc.stdout.strip())["file_count"] == 0


# ─── 3. PROV diagnostic degradation for contaminated workflows ────────────────

class TestProvDiagnosticDegradation:
    def test_wrong_specs_dir_baseline_degrades_with_diagnosis(self, tmp_path, monkeypatch):
        """The state scan-dimensionamento is in: baseline recorded against
        'specs' (empty) while CLAUDE.md declares docs/specs. PROV must skip
        with a diagnosed warning — not fail the handoff."""
        base = tmp_path / ".orch"
        for name, val in {
            "ORCH_DIR": base, "LOG_PATH": base / "log.jsonl",
            "LOCK_PATH": base / "log.jsonl.lock", "STATE_DIR": base / "state",
            "DLQ_DIR": base / "dlq", "AUDIT_DIR": base / "audit",
            "METRICS_DIR": base / "metrics", "BLOBS_DIR": base / "blobs",
            "WORKERS_DIR": base / "workers", "CONFIG_PATH": base / "config.json",
        }.items():
            monkeypatch.setattr(orch_core, name, val)
        orch_core.ensure_dirs()
        (tmp_path / "CLAUDE.md").write_text("specs_dir: docs/specs\n", encoding="utf-8")
        f1 = "docs/specs/domains/fsm/back/fsm.back.md"
        (tmp_path / f1).parent.mkdir(parents=True)
        (tmp_path / f1).write_bytes(b"v1")
        # the contaminated baseline: wrong dir, zero files
        orch_core.append_event(
            agent="spec-baseline", event_type="spec_baseline_recorded",
            data={"workflow_id": "wf-1", "phase": "sdd", "specs_dir": "specs",
                  "artifacts": {}},
        )
        digest = _sha(b"v1")
        mp = tmp_path / "docs" / "specs" / "handoff-manifest.yaml"
        mp.write_text("\n".join([
            "handoff:",
            "  id: HANDOFF-20260728-170000",
            "  delivered_by: u-spec-orchestrator",
            "  delivered_at: 2026-07-28T17:00:00Z",
            "  layer: semi-permanent",
            "  type: new_domain",
            "domains:",
            "  - name: fsm",
            "backend_package:",
            "  - artifact: openapi", f"    path: {f1}", f"    sha256: {digest}",
            "  - artifact: back-spec", f"    path: {f1}", f"    sha256: {digest}",
        ]) + "\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in ("ORCH_PROJECT_DIR", "SPECS_DIR")}
        proc = subprocess.run(
            [sys.executable, str(_VALIDATE), "--manifest", str(mp),
             "--specs-dir", str(tmp_path), "--project-dir", str(tmp_path),
             "--workflow-id", "wf-1"],
            capture_output=True, text=True, env=env,
        )
        result = json.loads(proc.stdout.strip())
        assert not [e for e in result["errors"] if e.startswith("PROV")], result
        assert any("wrong specs_dir" in w or "recorded against" in w
                   for w in result["warnings"]), result
        assert proc.returncode == 0


# ─── W11 — inline env in agent protocols ──────────────────────────────────────

_SCRIPTS = dist / "skills" / "u-worker-compliance" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import check_worker  # noqa: E402


class TestW11InlineEnv:
    def test_bare_invocation_fails(self):
        content = "```bash\npython3 .claude/skills/phase-sdd-rules/scripts/record_spec_baseline.py --workflow-id x\n```\n"
        v = check_worker._check_w11_inline_env(content, Path("orchestrator-sdd.md"))
        assert len(v) == 1 and v[0].rule == "W11"

    def test_inline_env_passes(self):
        content = (
            "```bash\nORCH_PROJECT_DIR=<ORCH_PROJECT_DIR> SPECS_DIR=<SPECS_DIR> "
            "python3 .claude/skills/phase-sdd-rules/scripts/record_spec_baseline.py --workflow-id x\n```\n"
        )
        assert not check_worker._check_w11_inline_env(content, Path("orchestrator-sdd.md"))

    def test_prose_mention_is_ignored(self):
        content = "Do NOT run `check_handoff_manifest_approved.py` in this mode.\n"
        assert not check_worker._check_w11_inline_env(content, Path("orchestrator-dev.md"))

    def test_every_shipped_agent_passes_w11(self):
        for agent in sorted((dist / "agents").rglob("*.md")):
            v = check_worker._check_w11_inline_env(
                agent.read_text(encoding="utf-8"), agent
            )
            assert not v, f"{agent.name}: {[x.detail for x in v]}"
