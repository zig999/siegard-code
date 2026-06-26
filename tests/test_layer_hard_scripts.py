"""Layer Hard Scripts — coverage for destructive/operational scripts (task 11).

A5-F4: purge.py can archive+truncate/delete the log (P1) and had ZERO tests.
A5-F5: recover_retry_sequence.py used input() (no non-interactive path).
A5-F6: validate_dist.py was a name-linter, not a structural validator.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "dist" / ".claude" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))

PURGE = SCRIPTS / "purge.py"
RECOVER = SCRIPTS / "recover_retry_sequence.py"
FIX_STUCK = SCRIPTS / "fix_stuck_improve.py"
VALIDATE = SCRIPTS / "validate_dist.py"


def _env(d):
    return {**os.environ, "ORCH_PROJECT_DIR": str(d)}


def _seed_log(d, n=3):
    orch = d / ".orch"
    orch.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps({"seq": i, "event_type": "task_progress", "hash": f"h{i}"}) + "\n"
                      for i in range(1, n + 1))
    log = orch / "log.jsonl"
    log.write_text(content, encoding="utf-8")
    return log


class TestPurgeSafety:  # A5-F4
    def test_reset_log_dry_run_makes_no_change(self, tmp_path):
        log = _seed_log(tmp_path)
        before = log.read_text()
        subprocess.run([sys.executable, str(PURGE), "--reset-log", "--operator", "t"],
                       env=_env(tmp_path), capture_output=True, text=True)  # no --confirm
        assert log.read_text() == before

    def test_reset_log_without_confirm_keeps_content(self, tmp_path):
        log = _seed_log(tmp_path)
        subprocess.run([sys.executable, str(PURGE), "--reset-log", "--operator", "t"],
                       env=_env(tmp_path), capture_output=True, text=True)
        assert log.read_text().strip() != ""

    def test_reset_log_confirm_archives_before_truncate(self, tmp_path):
        log = _seed_log(tmp_path)
        orig = log.read_text()
        subprocess.run([sys.executable, str(PURGE), "--reset-log", "--confirm", "--operator", "t"],
                       env=_env(tmp_path), capture_output=True, text=True)
        archives = list((tmp_path / ".orch").glob("log.jsonl.*"))
        assert archives, "an archive must exist before truncation"
        assert any(a.read_text() == orig for a in archives), "archive must be byte-identical to pre-truncate log"
        assert log.read_text().strip() == "", "log must be truncated after reset"

    def test_delete_log_requires_operator(self, tmp_path):
        _seed_log(tmp_path)
        p = subprocess.run([sys.executable, str(PURGE), "--delete-log", "--confirm"],
                           env=_env(tmp_path), capture_output=True, text=True)
        assert p.returncode != 0


class TestRecoverNonInteractive:  # A5-F5
    def test_yes_flag_exists(self):
        p = subprocess.run([sys.executable, str(RECOVER), "--help"], capture_output=True, text=True)
        assert p.returncode == 0
        assert "--yes" in p.stdout


class TestFixStuckSmoke:  # A5-F5
    def test_help_runs(self):
        p = subprocess.run([sys.executable, str(FIX_STUCK), "--help"], capture_output=True, text=True)
        assert p.returncode == 0


class TestValidateDistStructural:  # A5-F6
    def test_clean_on_real_dist(self):
        p = subprocess.run([sys.executable, str(VALIDATE)], capture_output=True, text=True)
        assert p.returncode == 0, p.stdout + p.stderr

    def test_flags_missing_criterion_script(self, tmp_path):
        import validate_dist
        skills = tmp_path / "skills" / "phase-x-rules"
        (skills / "scripts").mkdir(parents=True)
        (skills / "exit-criteria.json").write_text(
            json.dumps({"phase": "x", "criteria": [{"id": "c1", "script": "scripts/nope.py"}]}))
        errs = validate_dist._check_exit_criteria_scripts(tmp_path / "skills")
        assert any("nope.py" in e for e in errs)

    def test_flags_bad_json(self, tmp_path):
        import validate_dist
        skills = tmp_path / "skills" / "phase-y-rules"
        skills.mkdir(parents=True)
        (skills / "exit-criteria.json").write_text("{ not valid json")
        errs = validate_dist._check_exit_criteria_scripts(tmp_path / "skills")
        assert errs

    def test_passes_when_scripts_exist(self, tmp_path):
        import validate_dist
        skills = tmp_path / "skills" / "phase-z-rules"
        (skills / "scripts").mkdir(parents=True)
        (skills / "scripts" / "check_ok.py").write_text("# stub\n")
        (skills / "exit-criteria.json").write_text(
            json.dumps({"phase": "z", "criteria": [{"id": "c1", "script": "scripts/check_ok.py"}]}))
        assert validate_dist._check_exit_criteria_scripts(tmp_path / "skills") == []
