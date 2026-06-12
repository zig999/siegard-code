"""verify_install.py — behavioral tests against simulated target installs."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import verify_install as vi


def _build_manifest(claude_dir: Path) -> dict:
    files = [
        {"path": rel, "sha256": vi.hash_file(claude_dir / rel)}
        for rel in vi.iter_managed_files(claude_dir)
    ]
    return {
        "framework": "siegard-code",
        "version": "1.0.0",
        "source": {"repository": "git@example.com:siegard-code.git"},
        "generated_at": "2026-06-12T00:00:00Z",
        "hash_normalization": "text-lf",
        "files": files,
    }


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """A minimal installed target: .claude/ with managed files + manifest."""
    claude = tmp_path / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "skills" / "u-demo").mkdir(parents=True)
    (claude / "agents" / "orchestrator.md").write_text(
        "# orchestrator\nbody line\n", encoding="utf-8")
    (claude / "skills" / "u-demo" / "SKILL.md").write_text(
        "---\nname: u-demo\n---\nbody\n", encoding="utf-8")
    manifest = _build_manifest(claude)
    (claude / vi.MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8")
    return claude


class TestVerify:
    def test_intact_install_is_ok(self, target):
        envelope, exit_code = vi.verify(target)
        assert exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["version"] == "1.0.0"
        assert envelope["summary"] == {
            "total": 2, "ok": 2, "modified": 0, "missing": 0, "unknown": 0}
        assert envelope["findings"] == []

    def test_modified_file_detected(self, target):
        (target / "skills" / "u-demo" / "SKILL.md").write_text(
            "---\nname: u-demo\n---\nlocally edited\n", encoding="utf-8")
        envelope, exit_code = vi.verify(target)
        assert exit_code == 1
        assert envelope["status"] == "modified"
        assert {"path": "skills/u-demo/SKILL.md", "state": "modified"} \
            in envelope["findings"]

    def test_missing_file_detected(self, target):
        (target / "agents" / "orchestrator.md").unlink()
        envelope, exit_code = vi.verify(target)
        assert exit_code == 1
        assert envelope["status"] == "incomplete"
        assert {"path": "agents/orchestrator.md", "state": "missing"} \
            in envelope["findings"]

    def test_missing_takes_precedence_over_modified(self, target):
        (target / "agents" / "orchestrator.md").unlink()
        (target / "skills" / "u-demo" / "SKILL.md").write_text(
            "edited", encoding="utf-8")
        envelope, _ = vi.verify(target)
        assert envelope["status"] == "incomplete"

    def test_crlf_rewrite_still_verifies_ok(self, target):
        path = target / "agents" / "orchestrator.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        envelope, exit_code = vi.verify(target)
        assert exit_code == 0, "CRLF normalization (text-lf) must absorb EOL drift"
        assert envelope["status"] == "ok"

    def test_unknown_file_in_managed_namespace_is_warning_only(self, target):
        extra = target / "skills" / "u-extra" / "SKILL.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("leftover from older version\n", encoding="utf-8")
        envelope, exit_code = vi.verify(target)
        assert exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["summary"]["unknown"] == 1
        assert {"path": "skills/u-extra/SKILL.md", "state": "unknown"} \
            in envelope["findings"]

    def test_target_own_files_never_reported(self, target):
        (target / "CLAUDE.md").write_text("# target memory\n", encoding="utf-8")
        (target / "commands").mkdir()
        (target / "commands" / "deploy.md").write_text("local\n", encoding="utf-8")
        envelope, exit_code = vi.verify(target)
        assert exit_code == 0
        assert envelope["summary"]["unknown"] == 0

    def test_no_manifest_is_error(self, target):
        (target / vi.MANIFEST_NAME).unlink()
        envelope, exit_code = vi.verify(target)
        assert exit_code == 2
        assert envelope["status"] == "error"
        assert envelope["reason"] == "manifest_not_found"

    def test_corrupt_manifest_is_error(self, target):
        (target / vi.MANIFEST_NAME).write_text("{not json", encoding="utf-8")
        envelope, exit_code = vi.verify(target)
        assert exit_code == 2
        assert envelope["reason"] == "manifest_unreadable"

    def test_claude_dir_not_found_is_error(self, tmp_path):
        envelope, exit_code = vi.verify(tmp_path / "nope" / ".claude")
        assert exit_code == 2
        assert envelope["reason"] == "claude_dir_not_found"


class TestSubprocessBoundary:
    def test_cli_emits_single_json_envelope(self, target, tmp_path):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "verify_install.py")],
            capture_output=True, text=True, timeout=15, cwd=tmp_path,
        )
        assert result.returncode == 0
        envelope = json.loads(result.stdout)
        assert envelope["status"] == "ok"

    def test_cli_exit_1_on_drift(self, target, tmp_path):
        (target / "agents" / "orchestrator.md").unlink()
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "verify_install.py")],
            capture_output=True, text=True, timeout=15, cwd=tmp_path,
        )
        assert result.returncode == 1
        assert json.loads(result.stdout)["status"] == "incomplete"
