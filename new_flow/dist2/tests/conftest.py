import sys
import pytest
from pathlib import Path

# Add lib to path so tests can import orch_core directly
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "lib"))


@pytest.fixture
def tmp_orch(tmp_path, monkeypatch):
    """
    Redirects all orch_core paths to a temporary directory.
    Use in any test that writes to .orch/.
    """
    import orch_core

    orch_dir = tmp_path / ".orch"
    orch_dir.mkdir()

    monkeypatch.setattr(orch_core, "ORCH_DIR", orch_dir)
    monkeypatch.setattr(orch_core, "LOG_PATH", orch_dir / "log.jsonl")
    monkeypatch.setattr(orch_core, "LOCK_PATH", orch_dir / "log.jsonl.lock")
    monkeypatch.setattr(orch_core, "STATE_DIR", orch_dir / "state")
    monkeypatch.setattr(orch_core, "DLQ_DIR", orch_dir / "dlq")
    monkeypatch.setattr(orch_core, "AUDIT_DIR", orch_dir / "audit")
    monkeypatch.setattr(orch_core, "METRICS_DIR", orch_dir / "metrics")
    monkeypatch.setattr(orch_core, "BLOBS_DIR", orch_dir / "blobs")
    monkeypatch.setattr(orch_core, "WORKERS_DIR", orch_dir / "workers")
    monkeypatch.setattr(orch_core, "CONFIG_PATH", orch_dir / "config.json")

    orch_core.ensure_dirs()
    return tmp_path
