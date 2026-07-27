"""
identify_invalid_domains.py — SDD repair Step R2 (stage-granular repair input).

Scans _validation/*-validation.md for INVALID domains (same predicate as the
old prompt-inlined R2 python) and derives each domain's defect origin from the
machine-readable {domain}-validation-result.yaml: "back" only when ALL
blocking issues have responsible: u-spec-back; anything ambiguous → null
(full-pipeline repair — mis-attribution must never under-repair).
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "dist" / ".claude" / "skills" / "phase-sdd-rules" / "scripts"
    / "identify_invalid_domains.py"
)


def run(project_dir: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True,
        env={"ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _write_report(val_dir: Path, domain: str, status: str) -> None:
    val_dir.mkdir(parents=True, exist_ok=True)
    (val_dir / f"{domain}-validation.md").write_text(
        f"# Validation — {domain}\n\nstatus: {status}\n\n| # | issue |\n", encoding="utf-8"
    )


def _write_result_yaml(val_dir: Path, domain: str, status: str, responsibles: list[str]) -> None:
    issues = "\n".join(
        f"  - id: ISSUE-{i:03d}\n"
        f"    type: cross-ref\n"
        f"    source: specs/domains/{domain}/x.md\n"
        f"    description: broken ref\n"
        f"    responsible: {r}\n"
        f"    suggested_fix: fix it"
        for i, r in enumerate(responsibles, 1)
    )
    (val_dir / f"{domain}-validation-result.yaml").write_text(
        f"validation:\n  domain: {domain}\n  mode: final_complete\n"
        f"status: {status}\nblocking_count: {len(responsibles)}\nwarning_count: 0\n"
        f"handoff_allowed: false\nblocking_issues:\n{issues}\nwarnings: []\n",
        encoding="utf-8",
    )


class TestIdentifyInvalidDomains:
    EMPTY = {
        "invalid_domains": [],
        "defect_origins": {},
        "out_of_scope_invalid": [],
        # R08: domains whose INVALID verdict predates the specs it judges — they
        # get one validator run instead of a repair pipeline built on findings
        # nobody re-checked. Empty when nothing is INVALID.
        "stale_verdicts": {},
        "scoped": False,
    }

    def test_no_validation_dir(self, tmp_path):
        assert run(tmp_path) == self.EMPTY

    def test_valid_domain_not_listed(self, tmp_path):
        val = tmp_path / "specs" / "_validation"
        _write_report(val, "chat", "VALID")
        assert run(tmp_path) == self.EMPTY

    def test_invalid_all_back_origin_back(self, tmp_path):
        val = tmp_path / "specs" / "_validation"
        _write_report(val, "chat", "INVALID")
        _write_result_yaml(val, "chat", "INVALID", ["u-spec-back", "u-spec-back"])
        out = run(tmp_path)
        assert out["invalid_domains"] == ["chat"]
        assert out["defect_origins"] == {"chat": "back"}

    def test_mixed_responsibles_origin_null(self, tmp_path):
        val = tmp_path / "specs" / "_validation"
        _write_report(val, "chat", "INVALID")
        _write_result_yaml(val, "chat", "INVALID", ["u-spec-back", "u-spec-writer"])
        assert run(tmp_path)["defect_origins"] == {"chat": None}

    def test_missing_result_yaml_origin_null(self, tmp_path):
        """No machine-readable companion → cannot attribute → full pipeline."""
        val = tmp_path / "specs" / "_validation"
        _write_report(val, "chat", "INVALID")
        assert run(tmp_path)["defect_origins"] == {"chat": None}

    def test_contradictory_yaml_status_origin_null(self, tmp_path):
        """Report .md says INVALID but companion says VALID → do not reduce."""
        val = tmp_path / "specs" / "_validation"
        _write_report(val, "chat", "INVALID")
        _write_result_yaml(val, "chat", "VALID", ["u-spec-back"])
        assert run(tmp_path)["defect_origins"] == {"chat": None}

    def test_eternal_audit_shape(self, tmp_path):
        """Two INVALID domains, one back-only and one unattributed — matches
        the eternal repair-2 incident (chat + ingestion)."""
        val = tmp_path / "specs" / "_validation"
        _write_report(val, "chat", "INVALID")
        _write_result_yaml(val, "chat", "INVALID", ["u-spec-back"])
        _write_report(val, "ingestion", "INVALID")
        out = run(tmp_path)
        assert sorted(out["invalid_domains"]) == ["chat", "ingestion"]
        assert out["defect_origins"] == {"chat": "back", "ingestion": None}
