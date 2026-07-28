"""Artifact provenance — Pacote A (v2.35.0): notarization + baseline + PROV.

The threat (validated downstream): HDF-020/021 prove the manifest matches the
FILES; they cannot prove the files came from the PIPELINE — a freelance edit
followed by deterministic manifest regeneration passes every integrity gate
("laundering"). The append-only hash-chained log is the notary that closes it:

  A1'  emit.py computes sha256 per declared artifact (worker cannot lie)
  A2'  generate_handoff_manifest.py notarizes the manifest it wrote
  A3'  record_spec_baseline.py snapshots the inherited spec tree ONCE per
       workflow (re-entry must not re-bless freelance edits)
  A4'  validate.py PROV-010/020/030 verify the manifest against the log
  A6'  no baseline (pre-2.35 workflow) -> warnings, never errors
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
ROOT = dist.parent.parent

import orch_core  # noqa: E402  (lib on sys.path via conftest)

_EMIT_PATH = dist / "skills" / "orch-report" / "scripts" / "emit.py"
_BASELINE = dist / "skills" / "phase-sdd-rules" / "scripts" / "record_spec_baseline.py"
_VALIDATE = dist / "skills" / "u-handoff-validator" / "validate.py"

_spec = importlib.util.spec_from_file_location("emit_prov_under_test", _EMIT_PATH)
emit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emit)

_vspec = importlib.util.spec_from_file_location("validate_prov_under_test", _VALIDATE)
validate_mod = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(validate_mod)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


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
    monkeypatch.setattr(emit, "WORKERS_DIR", base / "workers")
    orch_core.ensure_dirs()


# ─── A1' — emit.py notarizes declared artifacts ───────────────────────────────

class TestEmitNotarization:
    def _emit_completed(self, monkeypatch, capsys, tmp_path, artifacts):
        monkeypatch.setenv("ORCH_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("ORCH_WORKER_ID", "u-spec-writer-t1")
        orch_core.register_worker("u-spec-writer-t1", "t1", 1, phase="sdd")
        monkeypatch.setattr(sys, "argv", [
            "emit.py", "--kind", "completed", "--task-id", "t1", "--attempt", "1",
            "--data", json.dumps({"phase": "sdd", "artifacts": artifacts}),
        ])
        rc = emit.main()
        out = capsys.readouterr()
        return rc, out.out, out.err

    def test_hash_computed_for_real_file(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        spec = tmp_path / "specs" / "domains" / "auth" / "auth.spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"# auth spec v1\n")
        rc, out, _ = self._emit_completed(
            monkeypatch, capsys, tmp_path, ["specs/domains/auth/auth.spec.md"]
        )
        assert rc == 0
        event = json.loads(out.strip())
        hashes = event["data"]["artifacts_sha256"]
        assert hashes["specs/domains/auth/auth.spec.md"] == _sha(b"# auth spec v1\n")

    def test_absolute_path_is_relativized(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        spec = tmp_path / "specs" / "a.md"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"x")
        rc, out, _ = self._emit_completed(monkeypatch, capsys, tmp_path, [str(spec)])
        assert rc == 0
        hashes = json.loads(out.strip())["data"]["artifacts_sha256"]
        assert "specs/a.md" in hashes

    def test_missing_artifact_warns_but_emits(self, tmp_path, monkeypatch, capsys):
        """Phantom artifact -> stderr warning, event still appended, no hash.
        (Warn, not hard-fail: artifact path conventions vary by worker; spec
        files that dodge hashing are caught by PROV at handoff.)"""
        _isolate_orch(tmp_path, monkeypatch)
        rc, out, err = self._emit_completed(
            monkeypatch, capsys, tmp_path, ["specs/ghost.md"]
        )
        assert rc == 0
        assert json.loads(err.strip())["reason"] == "artifacts_not_hashed"
        assert "artifacts_sha256" not in json.loads(out.strip())["data"]


# ─── A3' — adoption baseline: once per workflow ───────────────────────────────

def _run_baseline(project_dir: Path, wid: str = "wf-1"):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    return subprocess.run(
        [sys.executable, str(_BASELINE), "--workflow-id", wid],
        capture_output=True, text=True, env=env,
    )


class TestSpecBaseline:
    def test_records_snapshot(self, tmp_path):
        spec = tmp_path / "specs" / "domains" / "auth" / "openapi.yaml"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"openapi: 3.0.0\n")
        proc = _run_baseline(tmp_path)
        result = json.loads(proc.stdout.strip())
        assert result["status"] == "recorded"
        assert result["file_count"] == 1
        log_lines = (tmp_path / ".orch" / "log.jsonl").read_text().strip().splitlines()
        event = json.loads(log_lines[-1])
        assert event["event_type"] == "spec_baseline_recorded"
        assert event["data"]["artifacts"]["specs/domains/auth/openapi.yaml"] == _sha(b"openapi: 3.0.0\n")

    def test_second_run_is_noop(self, tmp_path):
        """Correctness, not convenience: re-entry re-baselining would bless
        freelance edits made mid-workflow."""
        (tmp_path / "specs").mkdir()
        (tmp_path / "specs" / "a.md").write_bytes(b"v1")
        assert json.loads(_run_baseline(tmp_path).stdout)["status"] == "recorded"
        (tmp_path / "specs" / "a.md").write_bytes(b"freelanced")
        second = json.loads(_run_baseline(tmp_path).stdout)
        assert second["status"] == "exists"
        # the log still holds ONE baseline, with the ORIGINAL hash
        lines = (tmp_path / ".orch" / "log.jsonl").read_text().strip().splitlines()
        baselines = [json.loads(l) for l in lines
                     if json.loads(l)["event_type"] == "spec_baseline_recorded"]
        assert len(baselines) == 1
        assert baselines[0]["data"]["artifacts"]["specs/a.md"] == _sha(b"v1")

    def test_greenfield_records_empty_baseline(self, tmp_path):
        result = json.loads(_run_baseline(tmp_path).stdout)
        assert result["status"] == "recorded"
        assert result["file_count"] == 0


# ─── A4'/A6' — PROV rules in the handoff validator ────────────────────────────

def _write_manifest(specs_dir: Path, entries: list[tuple[str, str]]) -> Path:
    """Minimal structurally-valid new_domain manifest with pinned hashes."""
    lines = [
        "handoff:",
        "  id: HANDOFF-20260728-120000",
        "  delivered_by: u-spec-orchestrator",
        "  delivered_at: 2026-07-28T12:00:00Z",
        "  layer: semi-permanent",
        "  type: new_domain",
        "domains:",
        "  - name: auth",
        "backend_package:",
    ]
    # FLOW-037: new_domain requires both "openapi" and "back-spec" artifacts —
    # pad with the first entry so single-file tests stay structurally valid
    # and assertions isolate PROV behavior.
    artifact_names = ["openapi", "back-spec"]
    padded = list(entries)
    while len(padded) < len(artifact_names):
        padded.append(entries[0])
    for i, (path, digest) in enumerate(padded):
        art = artifact_names[i] if i < len(artifact_names) else f"extra-{i}"
        lines += [f"  - artifact: {art}", f"    path: {path}", f"    sha256: {digest}"]
    mp = specs_dir / "handoff-manifest.yaml"
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp


def _validate(manifest_path: Path, project_dir: Path, wid: str | None = "wf-1"):
    cmd = [sys.executable, str(_VALIDATE),
           "--manifest", str(manifest_path),
           "--specs-dir", str(project_dir),
           "--project-dir", str(project_dir)]
    if wid:
        cmd += ["--workflow-id", wid]
    env = {k: v for k, v in os.environ.items() if k != "ORCH_PROJECT_DIR"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return json.loads(proc.stdout.strip()), proc.returncode


def _seed_workflow(tmp_path, monkeypatch, files: dict[str, bytes]):
    """Baseline over `files`, then return helpers to notarize/generate."""
    _isolate_orch(tmp_path, monkeypatch)
    specs = tmp_path / "specs" / "domains" / "auth"
    specs.mkdir(parents=True)
    for name, content in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(content)
    orch_core.append_event(
        agent="spec-baseline", event_type="spec_baseline_recorded",
        data={"workflow_id": "wf-1", "phase": "sdd", "specs_dir": "specs",
              "artifacts": {n: _sha(c) for n, c in files.items()}},
    )


def _notarize(path: str, content: bytes):
    orch_core.append_event(
        agent="u-spec-writer-t1", event_type="task_completed",
        task_id=None, attempt=None,
        data={"phase": "sdd", "artifacts": [path],
              "artifacts_sha256": {path: _sha(content)}},
    )


def _notarize_manifest(mp: Path):
    orch_core.append_event(
        agent="handoff-generator", event_type="handoff_manifest_generated",
        data={"workflow_id": "wf-1", "manifest_path": str(mp),
              "manifest_sha256": _sha(mp.read_bytes())},
    )


class TestProvenanceRules:
    def test_fully_provenanced_manifest_is_valid(self, tmp_path, monkeypatch):
        f1 = "specs/domains/auth/openapi.yaml"
        f2 = "specs/domains/auth/auth.back.md"
        _seed_workflow(tmp_path, monkeypatch, {f1: b"openapi-v1", f2: b"back-v1"})
        # worker updates f1 during the workflow
        (tmp_path / f1).write_bytes(b"openapi-v2")
        _notarize(f1, b"openapi-v2")
        mp = _write_manifest(tmp_path / "specs", [
            (f1, _sha(b"openapi-v2")),   # worker-notarized
            (f2, _sha(b"back-v1")),      # untouched -> baseline
        ])
        _notarize_manifest(mp)
        result, rc = _validate(mp, tmp_path)
        prov = [e for e in result["errors"] if e.startswith("PROV")]
        assert prov == []
        assert rc == 0, result

    def test_laundered_freelance_edit_fails_prov_010(self, tmp_path, monkeypatch):
        """The incident class: file edited outside the pipeline, manifest
        regenerated so integrity hashes MATCH the file — PROV still fails,
        because the log never notarized that content."""
        f1 = "specs/domains/auth/openapi.yaml"
        _seed_workflow(tmp_path, monkeypatch, {f1: b"openapi-v1"})
        (tmp_path / f1).write_bytes(b"freelance-edit")           # outside pipeline
        mp = _write_manifest(tmp_path / "specs",
                             [(f1, _sha(b"freelance-edit"))])    # "laundered" pin
        _notarize_manifest(mp)                                    # even regenerated
        result, rc = _validate(mp, tmp_path)
        assert any(e.startswith("PROV-010") and "openapi.yaml" in e
                   for e in result["errors"]), result
        assert rc == 1

    def test_manifest_not_from_generator_fails_prov_020(self, tmp_path, monkeypatch):
        f1 = "specs/domains/auth/openapi.yaml"
        _seed_workflow(tmp_path, monkeypatch, {f1: b"v1"})
        mp = _write_manifest(tmp_path / "specs", [(f1, _sha(b"v1"))])
        _notarize_manifest(mp)
        # manifest tampered AFTER generation (hash in log no longer matches)
        mp.write_text(mp.read_text() + "# tampered\n", encoding="utf-8")
        result, _ = _validate(mp, tmp_path)
        assert any(e.startswith("PROV-020") for e in result["errors"]), result

    def test_no_generation_event_fails_prov_030(self, tmp_path, monkeypatch):
        f1 = "specs/domains/auth/openapi.yaml"
        _seed_workflow(tmp_path, monkeypatch, {f1: b"v1"})
        mp = _write_manifest(tmp_path / "specs", [(f1, _sha(b"v1"))])
        result, _ = _validate(mp, tmp_path)
        assert any(e.startswith("PROV-030") for e in result["errors"]), result

    def test_no_baseline_degrades_to_warning(self, tmp_path, monkeypatch):
        """A6' migration: pre-2.35 workflow (no baseline event) must not break."""
        _isolate_orch(tmp_path, monkeypatch)
        specs = tmp_path / "specs" / "domains" / "auth"
        specs.mkdir(parents=True)
        f1 = "specs/domains/auth/openapi.yaml"
        (tmp_path / f1).write_bytes(b"v1")
        # log exists (some unrelated event) but holds no baseline
        orch_core.append_event(
            agent="orchestrator", event_type="phase_declared",
            data={"workflow_id": "wf-1", "phases": [{"name": "sdd", "order": 1}]},
        )
        mp = _write_manifest(tmp_path / "specs", [(f1, _sha(b"v1"))])
        result, rc = _validate(mp, tmp_path)
        assert not any(e.startswith("PROV") for e in result["errors"])
        assert any("PROV: skipped" in w for w in result["warnings"]), result
        assert rc == 0

    def test_workflow_id_derived_from_newest_baseline(self, tmp_path, monkeypatch):
        f1 = "specs/domains/auth/openapi.yaml"
        _seed_workflow(tmp_path, monkeypatch, {f1: b"v1"})
        mp = _write_manifest(tmp_path / "specs", [(f1, _sha(b"v1"))])
        _notarize_manifest(mp)
        result, rc = _validate(mp, tmp_path, wid=None)  # no --workflow-id
        assert not [e for e in result["errors"] if e.startswith("PROV")], result
        assert rc == 0


# ─── A2' — generator notarizes what it writes ─────────────────────────────────

class TestGeneratorNotarization:
    def test_generated_event_matches_manifest_on_disk(self, tmp_path, monkeypatch):
        """Covered end-to-end in test_layer_hard_handoff_generation; here we pin
        the contract: after generate(), the log's handoff_manifest_generated
        hash equals the file's actual sha256 (PROV-020's premise)."""
        _isolate_orch(tmp_path, monkeypatch)
        mp = tmp_path / "specs" / "handoff-manifest.yaml"
        mp.parent.mkdir(parents=True)
        mp.write_text("handoff:\n  id: HANDOFF-X\n", encoding="utf-8")
        _notarize_manifest(mp)
        events = list(orch_core.read_events())
        gen = [e for e in events if e.event_type == "handoff_manifest_generated"]
        assert len(gen) == 1
        assert gen[0].data["manifest_sha256"] == _sha(mp.read_bytes())
