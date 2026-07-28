"""flow_guard.py — PreToolUse ownership guard over pipeline-owned artifacts (v2.34.0).

Origin: a downstream host session offered to execute the SDD flow inline
("write the spec insertions, regenerate the manifest, run the five gates")
instead of routing through /u-improve. Descriptions and CLAUDE.md prose are
advisory; this guard is the deterministic layer (P7) that blocks the casual
bypass path and redirects to the entry command.

Covered here:
  - ownership classes: specs tree blocked, .orch/sessions/ allowed,
    .orch/log.jsonl always blocked, everything else untouched
  - in-flight worker semantics: shares attempt_has_terminal +
    worker_liveness_expired with the SubagentStop hook (never disagree)
  - kill-switch modes: hard | warn (audited) | off; unknown value -> hard
  - specs_dir resolution: config override > CLAUDE.md machine-parsed block
    > SPECS_DIR env > ./specs; template placeholders ignored
  - fail-open on malformed stdin (a buggy guard must never brick editing)
  - Windows guarantee: no fcntl anywhere in the hook source
  - dist settings.json actually wires the hook (a guard that ships unwired
    protects nothing)
"""
import io
import json
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
_HOOKS = dist / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import orch_core  # noqa: E402  (lib on sys.path via conftest)
import flow_guard  # noqa: E402


# ─── isolation (same pattern as test_worker_cause: monkeypatch, NO reload) ───

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


def _invoke(monkeypatch, capsys, project_dir, file_path, tool_name="Write", **extra):
    payload = {
        "session_id": "test-session",
        "cwd": str(project_dir),
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"file_path": str(file_path)},
        **extra,
    }
    monkeypatch.setenv("ORCH_PROJECT_DIR", str(project_dir))
    monkeypatch.delenv("SPECS_DIR", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = flow_guard.main()
    return rc, capsys.readouterr().err


def _write_claude_md(project_dir: Path, specs_dir: str = "docs/specs") -> None:
    (project_dir / "CLAUDE.md").write_text(
        f"# Target\n\ndomain: fullstack\nspecs_dir: {specs_dir}\n",
        encoding="utf-8",
    )


def _seed_task(task_id: str = "sdd_wf_writer-auth", agent: str = "orchestrator-sdd"):
    # Tasks only reach READY (claimable) inside an active phase.
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": "wf", "phases": [{"name": "sdd", "order": 1}]},
    )
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "sdd", "order": 1, "workflow_id": "wf"},
    )
    orch_core.append_event(
        agent=agent,
        event_type="task_created",
        task_id=task_id,
        attempt=1,
        data={"phase": "sdd", "tier": "standard", "type": "spec-writer",
              "spec": "write auth spec", "deps": []},
    )


# ─── ownership classes ────────────────────────────────────────────────────────

class TestOwnershipClasses:
    def test_non_protected_path_allowed(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, err = _invoke(monkeypatch, capsys, tmp_path, tmp_path / "src" / "app.py")
        assert rc == 0

    def test_spec_write_blocked_without_workflow(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, err = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 2
        blocked = json.loads(err.strip())
        assert blocked["status"] == "blocked"
        assert blocked["reason"] == "pipeline_owned_artifact"
        assert "/u-improve" in blocked["action"]
        assert "/u-spec" in blocked["action"]

    def test_handoff_manifest_blocked(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, err = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "handoff-manifest.yaml", tool_name="Edit",
        )
        assert rc == 2
        assert json.loads(err.strip())["reason"] == "pipeline_owned_artifact"

    def test_sessions_dir_allowed_without_workers(self, tmp_path, monkeypatch, capsys):
        """Entry commands write improve-scope.json from the main session by design."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, _ = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / ".orch" / "sessions" / "wf-1" / "improve-scope.json",
        )
        assert rc == 0

    def test_log_jsonl_blocked_even_with_inflight_worker(self, tmp_path, monkeypatch, capsys):
        """The log is append-only + hash-chained; no in-flight state legitimizes
        a Write/Edit tool call on it — append.py is the only write path."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        _seed_task()
        orch_core.register_worker("u-spec-writer-sdd_wf_writer-auth",
                                  "sdd_wf_writer-auth", 1, phase="sdd")
        rc, err = _invoke(monkeypatch, capsys, tmp_path, tmp_path / ".orch" / "log.jsonl")
        assert rc == 2
        blocked = json.loads(err.strip())
        assert blocked["reason"] == "append_only_log"
        assert "append.py" in blocked["action"]

    def test_path_outside_project_allowed(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, "/somewhere/else/file.md")
        assert rc == 0


# ─── in-flight worker semantics ───────────────────────────────────────────────

class TestInFlightWorker:
    def test_allowed_while_worker_in_flight(self, tmp_path, monkeypatch, capsys):
        """Registered worker + live task (recent event, no terminal) -> the guard
        cannot attribute the calling session (correlation gap) and allows."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        _seed_task()
        orch_core.register_worker("u-spec-writer-sdd_wf_writer-auth",
                                  "sdd_wf_writer-auth", 1, phase="sdd")
        rc, _ = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 0

    def test_registered_entry_with_no_events_counts_as_in_flight(
        self, tmp_path, monkeypatch, capsys
    ):
        """The window between register_worker() and the worker's first event is a
        legitimate dispatch in progress."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        # log must exist for reduce_all; seed an unrelated event-free state
        orch_core.register_worker("u-spec-writer-sdd_wf_writer-x",
                                  "sdd_wf_writer-x", 1, phase="sdd")
        rc, _ = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "x" / "x.spec.md",
        )
        assert rc == 0

    def test_terminal_attempt_does_not_unlock(self, tmp_path, monkeypatch, capsys):
        """A stale registry entry whose attempt already completed is not proof of
        an active pipeline — the freelance window after completion stays closed."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        _seed_task()
        orch_core.register_worker("u-spec-writer-sdd_wf_writer-auth",
                                  "sdd_wf_writer-auth", 1, phase="sdd")
        # Real lifecycle: the reducer only honors a terminal after a claim
        # (v2.1.0 reducer guard) — seed the claim exactly as claim.py would.
        orch_core.append_event(
            agent="orchestrator-sdd",
            event_type="task_claimed",
            task_id="sdd_wf_writer-auth",
            attempt=1,
            data={"phase": "sdd", "worker_type": "u-spec-writer",
                  "worker_id": "u-spec-writer-sdd_wf_writer-auth"},
        )
        orch_core.append_event(
            agent="u-spec-writer-sdd_wf_writer-auth",
            event_type="task_completed",
            task_id="sdd_wf_writer-auth",
            attempt=1,
            data={"phase": "sdd", "artifacts": ["docs/specs/domains/auth/auth.spec.md"]},
        )
        rc, err = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 2
        assert json.loads(err.strip())["reason"] == "pipeline_owned_artifact"


# ─── kill-switch modes ────────────────────────────────────────────────────────

class TestGuardModes:
    def _write_config(self, tmp_path, mode):
        cfg = tmp_path / ".orch" / "config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"guard": {"enforce": mode}}), encoding="utf-8")

    def test_off_allows_spec_write(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._write_config(tmp_path, "off")
        rc, _ = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 0

    def test_warn_allows_and_audits(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._write_config(tmp_path, "warn")
        rc, err = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 0
        assert json.loads(err.strip())["status"] == "warned"
        audit = tmp_path / ".orch" / "guard_warnings.jsonl"
        assert audit.exists()
        line = json.loads(audit.read_text(encoding="utf-8").strip())
        assert line["reason"] == "pipeline_owned_artifact"

    def test_unknown_mode_is_hard(self, tmp_path, monkeypatch, capsys):
        """A typo must not silently disable the guard."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._write_config(tmp_path, "of")
        rc, _ = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 2

    def test_default_config_ships_guard_hard(self):
        assert orch_core.default_config()["guard"]["enforce"] == "hard"


# ─── specs_dir resolution ─────────────────────────────────────────────────────

class TestSpecsDirResolution:
    def test_template_placeholder_is_ignored(self, tmp_path, monkeypatch, capsys):
        """`specs_dir: {e.g. docs/specs}` is an unfilled template, not a value —
        the guard must not protect a literal '{e.g.' directory."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path, specs_dir="{e.g. docs/specs}")
        rc, _ = _invoke(
            monkeypatch, capsys, tmp_path,
            tmp_path / "docs" / "specs" / "domains" / "auth" / "auth.spec.md",
        )
        assert rc == 0

    def test_env_fallback(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)  # no CLAUDE.md at all
        payload = {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "myspecs" / "a.spec.md")},
        }
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("SPECS_DIR", "myspecs")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert flow_guard.main() == 2

    def test_config_override_wins(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path, specs_dir="docs/specs")
        cfg = tmp_path / ".orch" / "config.json"
        cfg.write_text(json.dumps({"guard": {"specs_dir": "other/specs"}}), encoding="utf-8")
        rc, _ = _invoke(monkeypatch, capsys, tmp_path,
                        tmp_path / "other" / "specs" / "a.spec.md")
        assert rc == 2
        rc, _ = _invoke(monkeypatch, capsys, tmp_path,
                        tmp_path / "docs" / "specs" / "a.spec.md")
        assert rc == 0

    def test_unresolvable_specs_dir_fails_open(self, tmp_path, monkeypatch, capsys):
        """No CLAUDE.md, no env, no ./specs: only log.jsonl stays protected."""
        _isolate_orch(tmp_path, monkeypatch)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path,
                        tmp_path / "docs" / "specs" / "a.spec.md")
        assert rc == 0


# ─── robustness ───────────────────────────────────────────────────────────────

class TestRobustness:
    def test_malformed_stdin_fails_open(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO("this is not json{{{"))
        assert flow_guard.main() == 0

    def test_empty_stdin_fails_open(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert flow_guard.main() == 0

    def test_unknown_tool_ignored(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        payload = {"cwd": str(tmp_path), "tool_name": "Bash",
                   "tool_input": {"command": "echo hi > docs/specs/a.spec.md"}}
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert flow_guard.main() == 0

    def test_no_fcntl_in_source(self):
        """Target environment is Windows (CLAUDE.md); fcntl in a hook was a
        documented audit finding — the guard must never regress into it."""
        src = (_HOOKS / "flow_guard.py").read_text(encoding="utf-8")
        assert "import fcntl" not in src


# ─── shipped wiring ───────────────────────────────────────────────────────────

class TestShippedWiring:
    def test_settings_json_declares_pretooluse_guard(self):
        settings = json.loads((dist / "settings.json").read_text(encoding="utf-8"))
        pre = settings["hooks"].get("PreToolUse", [])
        assert pre, "flow_guard ships unwired — settings.json has no PreToolUse entry"
        entry = pre[0]
        for tool in ("Write", "Edit"):
            assert tool in entry["matcher"]
        command = entry["hooks"][0]["command"]
        assert "flow_guard.py" in command
        assert "ORCH_PROJECT_DIR" in command


# ─── exact mode (v2.35.0) — capability self-detection ─────────────────────────

class TestExactMode:
    """Validated empirically (2026-07-28, CLI 2.1.220): a PreToolUse payload
    from inside a subagent carries agent_id + agent_type; one from the main
    session carries neither. Exact mode activates ONLY after this guard has
    seen agent identity in a real payload on this host (capability marker) —
    a host that never provides the field never leaves coarse mode, so a
    legitimate worker is never blocked by inference."""

    SPEC = "docs/specs/domains/auth/auth.spec.md"

    def _spec_path(self, tmp_path):
        return tmp_path / self.SPEC

    def _seed_inflight(self, tmp_path):
        _seed_task()
        orch_core.register_worker("u-spec-writer-sdd_wf_writer-auth",
                                  "sdd_wf_writer-auth", 1, phase="sdd")

    def _marker(self, tmp_path):
        return tmp_path / ".orch" / "host_capabilities.json"

    def test_matching_worker_subagent_allowed_and_marker_recorded(
        self, tmp_path, monkeypatch, capsys
    ):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._seed_inflight(tmp_path)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path),
                        agent_id="abc", agent_type="u-spec-writer")
        assert rc == 0
        caps = json.loads(self._marker(tmp_path).read_text(encoding="utf-8"))
        assert caps["pretooluse_agent_identity"] is True

    def test_unrelated_subagent_blocked(self, tmp_path, monkeypatch, capsys):
        """Freelance with extra steps: a subagent whose type matches no
        registered in-flight worker may not write specs."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._seed_inflight(tmp_path)
        rc, err = _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path),
                          agent_id="zzz", agent_type="general-purpose")
        assert rc == 2
        assert "general-purpose" in json.loads(err.strip())["detail"]

    def test_main_session_blocked_once_capability_known(
        self, tmp_path, monkeypatch, capsys
    ):
        """The in-flight window closes: after the marker exists, a payload
        without agent_id is demonstrably the main session on this host."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._seed_inflight(tmp_path)
        # 1) worker write records the capability
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path),
                        agent_id="abc", agent_type="u-spec-writer")
        assert rc == 0
        # 2) main-session write during the same in-flight window -> blocked
        rc, err = _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path))
        assert rc == 2
        assert "main session" in json.loads(err.strip())["detail"]

    def test_main_session_allowed_without_marker(self, tmp_path, monkeypatch, capsys):
        """Coarse fallback preserved: on a host that never showed agent
        identity, 'no agent_id' cannot distinguish main from worker."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._seed_inflight(tmp_path)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path))
        assert rc == 0

    def test_subagent_blocked_when_no_workflow(self, tmp_path, monkeypatch, capsys):
        """agent identity alone is not a permit — without any in-flight worker
        even a subagent write is freelance."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path),
                        agent_id="abc", agent_type="u-spec-writer")
        assert rc == 2

    def test_marker_write_is_idempotent(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        self._seed_inflight(tmp_path)
        for _ in range(2):
            _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path),
                    agent_id="abc", agent_type="u-spec-writer")
        caps = json.loads(self._marker(tmp_path).read_text(encoding="utf-8"))
        assert caps["pretooluse_agent_identity"] is True
        first_seen = caps["first_seen"]
        _invoke(monkeypatch, capsys, tmp_path, self._spec_path(tmp_path),
                agent_id="abc", agent_type="u-spec-writer")
        caps2 = json.loads(self._marker(tmp_path).read_text(encoding="utf-8"))
        assert caps2["first_seen"] == first_seen


# ─── telemetry (v2.36.0) — "is the hook firing?" as a file question ───────────

class TestGuardTelemetry:
    SPEC = "docs/specs/domains/auth/auth.spec.md"

    def _status(self, tmp_path):
        p = tmp_path / ".orch" / "guard_status.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def test_deny_writes_status(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, tmp_path / self.SPEC)
        assert rc == 2
        status = self._status(tmp_path)
        assert status["last_outcome"] == "deny"
        assert status["counts"]["deny"] == 1

    def test_allow_writes_status_and_counts_accumulate(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        _seed_task()
        orch_core.register_worker("u-spec-writer-sdd_wf_writer-auth",
                                  "sdd_wf_writer-auth", 1, phase="sdd")
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, tmp_path / self.SPEC)
        assert rc == 0
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, tmp_path / self.SPEC)
        assert rc == 0
        status = self._status(tmp_path)
        assert status["last_outcome"] == "allow"
        assert status["counts"]["allow"] == 2

    def test_unprotected_path_leaves_no_status(self, tmp_path, monkeypatch, capsys):
        """Fast path stays fast — telemetry only on protected-path adjudications."""
        _isolate_orch(tmp_path, monkeypatch)
        _write_claude_md(tmp_path)
        rc, _ = _invoke(monkeypatch, capsys, tmp_path, tmp_path / "src" / "app.py")
        assert rc == 0
        assert self._status(tmp_path) is None
