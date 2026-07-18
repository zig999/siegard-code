"""u-drift-analysis semantic layer (Release B) — verdict guard + merge.

Asserts:
  - validate_findings fails closed on unreal evidence, missing evidence, bad enums
  - merge_semantic relocates a drifted endpoint out of aligned into a needs_human
    finding, folds business-rule verdicts in, recounts, and re-numbers ids
  - the merged report still conforms to drift-report.schema.yaml
  - the shipped drift-verdicts example validates at the value level
"""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
from conftest import get_dist_dir, load_yaml

SCRIPTS = get_dist_dir() / "skills" / "u-drift-analysis" / "scripts"
SHARED = get_dist_dir() / "skills" / "u-shared-templates"


def _run(script, args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)] + args,
        capture_output=True, text=True, timeout=30,
    )


def _make_code(root: Path) -> Path:
    c = root / "src" / "auth"
    c.mkdir(parents=True, exist_ok=True)
    (c / "user.controller.ts").write_text("\n".join(f"// {i}" for i in range(1, 101)) + "\n", encoding="utf-8")
    return root / "src"


def _verdicts(code_dir: Path) -> dict:
    return {
        "generated_by": "u-drift-analyzer",
        "code_dir": str(code_dir),
        "verdicts": [
            {"target": "endpoint", "ref": "post /users", "domain": "auth", "verdict": "drifted",
             "severity": "blocking", "detail": "extra 422",
             "spec_evidence": {"file": "auth/openapi.yaml", "anchor": "createUser"},
             "code_evidence": {"file": "auth/user.controller.ts", "line": 42},
             "fix_spec": "add 422", "fix_code": "return 400"},
            {"target": "business_rule", "ref": "pw min", "domain": "auth", "verdict": "missing_in_spec",
             "severity": "minor", "detail": "8-char min, no BR",
             "spec_evidence": None, "code_evidence": {"file": "auth/user.controller.ts", "line": 22}},
        ],
    }


def _base_report() -> dict:
    return {
        "generated_by": "match_drift.py",
        "specs_dir": "specs", "code_dir": "src",
        "spec_content_hash": "abc", "code_commit_sha": "no-git",
        "summary": {"domains_analyzed": 1, "aligned": 2, "drifted": 0,
                    "missing_in_code": 0, "missing_in_spec": 0, "undecidable": 0, "skipped_draft": 0},
        "findings": [],
        "aligned": [
            {"domain": "auth", "artifact_type": "endpoint", "artifact_ref": "post /users"},
            {"domain": "auth", "artifact_type": "error_code", "artifact_ref": "USER_EMAIL_TAKEN"},
        ],
        "skipped": [],
    }


class TestValidateFindings:
    def test_valid_passes(self, tmp_path):
        code = _make_code(tmp_path)
        vf = tmp_path / "v.json"
        vf.write_text(json.dumps(_verdicts(code)))
        r = _run("validate_findings.py", ["--verdicts", str(vf), "--code-dir", str(code)])
        assert r.returncode == 0, r.stdout

    def test_line_beyond_eof_fails(self, tmp_path):
        code = _make_code(tmp_path)
        v = _verdicts(code)
        v["verdicts"][0]["code_evidence"]["line"] = 9999
        vf = tmp_path / "v.json"
        vf.write_text(json.dumps(v))
        r = _run("validate_findings.py", ["--verdicts", str(vf), "--code-dir", str(code)])
        assert r.returncode == 1 and "exceeds file length" in r.stdout

    def test_no_evidence_fails(self, tmp_path):
        code = _make_code(tmp_path)
        v = _verdicts(code)
        v["verdicts"][1]["code_evidence"] = None  # both null now
        vf = tmp_path / "v.json"
        vf.write_text(json.dumps(v))
        r = _run("validate_findings.py", ["--verdicts", str(vf), "--code-dir", str(code)])
        assert r.returncode == 1 and "at least one" in r.stdout

    def test_bad_verdict_enum_fails(self, tmp_path):
        code = _make_code(tmp_path)
        v = _verdicts(code)
        v["verdicts"][0]["verdict"] = "sortof"
        vf = tmp_path / "v.json"
        vf.write_text(json.dumps(v))
        r = _run("validate_findings.py", ["--verdicts", str(vf), "--code-dir", str(code)])
        assert r.returncode == 1 and "verdict" in r.stdout

    def test_bad_generated_by_fails(self, tmp_path):
        code = _make_code(tmp_path)
        v = _verdicts(code)
        v["generated_by"] = "someone-else"
        vf = tmp_path / "v.json"
        vf.write_text(json.dumps(v))
        r = _run("validate_findings.py", ["--verdicts", str(vf), "--code-dir", str(code)])
        assert r.returncode == 1


class TestMergeSemantic:
    def _merge(self, tmp_path, report=None, verdicts=None):
        code = _make_code(tmp_path)
        rp = tmp_path / "r.json"
        vp = tmp_path / "v.json"
        rp.write_text(json.dumps(report or _base_report()))
        vp.write_text(json.dumps(verdicts or _verdicts(code)))
        out = tmp_path / "m.json"
        r = _run("merge_semantic.py", ["--report", str(rp), "--verdicts", str(vp), "--out", str(out)])
        assert r.returncode == 0, r.stdout
        return json.loads(out.read_text())

    def test_drifted_endpoint_leaves_aligned_becomes_finding(self, tmp_path):
        m = self._merge(tmp_path)
        assert not any(a["artifact_ref"] == "post /users" for a in m["aligned"])
        drift = [f for f in m["findings"] if f["artifact_ref"] == "post /users"][0]
        assert drift["status"] == "drifted"
        assert drift["default_action"] == "needs_human"
        assert drift["handoff"]["fix_spec"] and drift["handoff"]["fix_code"]

    def test_business_rule_folded_in(self, tmp_path):
        m = self._merge(tmp_path)
        assert any(f["artifact_type"] == "business_rule" and f["status"] == "missing_in_spec"
                   for f in m["findings"])
        assert m["summary"]["missing_in_spec"] == 1
        assert m["summary"]["drifted"] == 1

    def test_aligned_verdict_added_to_aligned(self, tmp_path):
        code = _make_code(tmp_path)
        v = _verdicts(code)
        v["verdicts"] = [{"target": "business_rule", "ref": "BR-01", "domain": "auth",
                          "verdict": "aligned", "severity": "minor", "detail": "enforced",
                          "spec_evidence": {"file": "auth/back.md", "anchor": "BR-01"},
                          "code_evidence": {"file": "auth/user.controller.ts", "line": 14}}]
        m = self._merge(tmp_path, verdicts=v)
        assert any(a["artifact_type"] == "business_rule" and a["artifact_ref"] == "BR-01"
                   for a in m["aligned"])

    def test_ids_renumbered_and_deterministic(self, tmp_path):
        a = self._merge(tmp_path)
        b = self._merge(tmp_path)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        ids = [f["id"] for f in a["findings"]]
        assert ids == [f"DRIFT-{i:03d}" for i in range(1, len(ids) + 1)]

    def test_out_of_contract_endpoint_verdict_ignored(self, tmp_path):
        # Guard: a verdict for an endpoint NOT in the structural aligned set is
        # ignored (fail-safe), not merged into a contradictory finding.
        code = _make_code(tmp_path)
        v = _verdicts(code)
        v["verdicts"] = [{"target": "endpoint", "ref": "get /ghost", "domain": "auth",
                          "verdict": "drifted", "severity": "blocking", "detail": "phantom",
                          "spec_evidence": {"file": "a", "anchor": "b"},
                          "code_evidence": {"file": "auth/user.controller.ts", "line": 1},
                          "fix_spec": "x", "fix_code": "y"}]
        m = self._merge(tmp_path, verdicts=v)
        assert not any(f["artifact_ref"] == "get /ghost" for f in m["findings"])
        assert m["summary"]["drifted"] == 0

    def test_merged_report_conforms_to_schema(self, tmp_path):
        m = self._merge(tmp_path)
        schema = load_yaml(SHARED / "drift-report.schema.yaml")
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(m))
        assert errors == [], "; ".join(e.message for e in errors[:5])


class TestVerdictsExampleConformance:
    def test_shipped_example_validates(self):
        schema = load_yaml(SHARED / "drift-verdicts.schema.yaml")
        example = load_yaml(SHARED / "drift-verdicts.yaml")
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(example))
        assert errors == [], "; ".join(e.message for e in errors[:5])
