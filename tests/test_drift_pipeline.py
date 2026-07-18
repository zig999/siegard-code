"""u-drift-analysis pipeline — spec inventory, evidence guard, matching, render.

Exercises the four stdlib scripts through the subprocess boundary (the same
boundary /u-drift uses) and asserts:
  - deterministic extraction and matching (byte-identical on re-run)
  - planted drift is classified exactly (status, severity, action)
  - the determinism guard (validate_inventory) fails closed on unreal evidence
  - the base_path guard collapses a whole-domain path mismatch into one finding
  - the emitted drift-report.json conforms to its schema at the value level
"""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from conftest import get_dist_dir, load_yaml

SCRIPTS = get_dist_dir() / "skills" / "u-drift-analysis" / "scripts"
SHARED = get_dist_dir() / "skills" / "u-shared-templates"


def _run(script, args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)] + args,
        capture_output=True, text=True, timeout=30,
    )


# ── fixture builders ──────────────────────────────────────────────────────────

_OPENAPI = """openapi: "3.0.3"
info:
  title: Auth
  version: 1.0.0
paths:
  /users:
    post:
      operationId: createUser
      responses:
        "201":
          description: Created
        "409":
          description: Conflict
  /users/{id}:
    get:
      operationId: getUser
      responses:
        "200":
          description: OK
        "404":
          description: NotFound
"""

_BACK = """# Auth -- Back-end Spec

> Stack: node | DB: pg | Version: 1.0.0 | Status: approved | Layer: permanent

## 2. Data Model

### Table: User

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | uuid | pk | Identifier |
| email | varchar(255) | unique | Email |

## 3. Business Rules (BR)

### BR-01 -- Unique email
**Related UC:** UC-01
**Where to validate:** service
**Description:** Email must be unique.
**Error returned:** HTTP 409 -- error.code: `USER_EMAIL_TAKEN`

## 4. State Machine (ST)

### ST-01 -- User
| From | To | Event | Guard | UC |
|------|----|-------|-------|----|
| pending | active | activate | - | UC-01 |

## 5. Domain Events (EV)

### EV-01 -- user.created
**Dispatched when:** created
**Consumers:** mailer
"""

_SPEC = """# Auth -- Business Specification

> Version: 1.0.0 | Status: approved | Layer: permanent
"""


def _make_specs(root: Path, status: str = "approved") -> Path:
    d = root / "specs" / "domains" / "auth"
    (d / "back").mkdir(parents=True, exist_ok=True)
    (d / "openapi.yaml").write_text(_OPENAPI, encoding="utf-8")
    (d / "back" / "auth.back.md").write_text(_BACK.replace("Status: approved", f"Status: {status}"), encoding="utf-8")
    (d / "auth.spec.md").write_text(_SPEC.replace("Status: approved", f"Status: {status}"), encoding="utf-8")
    return root / "specs"


def _make_code(root: Path) -> Path:
    c = root / "src" / "auth"
    c.mkdir(parents=True, exist_ok=True)
    (c / "user.controller.ts").write_text("\n".join(f"// line {i}" for i in range(1, 101)) + "\n", encoding="utf-8")
    return root / "src"


def _code_inventory(code_dir: Path, base_path: str = "", drop_get: bool = True) -> dict:
    endpoints = [
        {"operation_id": "createUser", "method": "post", "path": base_path + "/users",
         "status_codes": [201, 409], "evidence": {"file": "auth/user.controller.ts", "line": 42}},
        # extra endpoint not in spec:
        {"operation_id": "deleteUser", "method": "delete", "path": base_path + "/users/{id}",
         "status_codes": [204, 404], "evidence": {"file": "auth/user.controller.ts", "line": 88}},
    ]
    if not drop_get:
        endpoints.append(
            {"operation_id": "getUser", "method": "get", "path": base_path + "/users/{id}",
             "status_codes": [200, 404], "evidence": {"file": "auth/user.controller.ts", "line": 30}})
    return {
        "generated_by": "u-reverse-spec-analyzer",
        "code_dir": str(code_dir),
        "commit_sha": "no-git",
        "base_path": "",  # already stripped in normal case
        "modules": [{
            "id": "auth",
            "endpoints": endpoints,
            "error_codes": [{"code": "USER_EMAIL_TAKEN", "http_status": 409,
                             "evidence": {"file": "auth/user.controller.ts", "line": 17}}],
            "entities": [{"name": "User", "fields": [
                {"name": "id", "type": "string"}, {"name": "email", "type": "string"},
                {"name": "lastLoginAt", "type": "Date"}],
                "evidence": {"file": "auth/user.controller.ts", "line": 5}}],
            "state_machines": [{"entity": "User", "states": ["pending", "active"],
                                "evidence": {"file": "auth/user.controller.ts", "line": 60}}],
            "events": [{"name": "user.created", "evidence": {"file": "auth/user.controller.ts", "line": 55}}],
            "business_rules": [{"description": "dup email", "evidence": {"file": "auth/user.controller.ts", "line": 14}}],
        }],
    }


# ── spec_inventory ────────────────────────────────────────────────────────────

class TestSpecInventory:
    def test_extracts_all_artifact_classes(self, tmp_path):
        specs = _make_specs(tmp_path)
        r = _run("spec_inventory.py", ["--specs-dir", str(specs)])
        assert r.returncode == 0, r.stderr
        inv = json.loads(r.stdout)
        dom = inv["domains"][0]
        assert {e["operation_id"] for e in dom["endpoints"]} == {"createUser", "getUser"}
        assert dom["error_codes"][0]["code"] == "USER_EMAIL_TAKEN"
        assert dom["entities"][0]["name"] == "User"
        assert {f["name"] for f in dom["entities"][0]["fields"]} == {"id", "email"}
        assert dom["state_machines"][0]["states"] == ["active", "pending"]
        assert dom["events"][0]["name"] == "user.created"
        assert dom["business_rules"][0]["id"] == "BR-01"

    def test_draft_domain_skipped_exit_3(self, tmp_path):
        specs = _make_specs(tmp_path, status="draft")
        out = tmp_path / "inv.json"
        skip = tmp_path / "skip.json"
        r = _run("spec_inventory.py", ["--specs-dir", str(specs), "--out", str(out), "--skipped-out", str(skip)])
        assert r.returncode == 3, r.stderr
        assert json.loads(out.read_text())["domains"] == []
        assert json.loads(skip.read_text())[0]["reason"] == "draft_status"

    def test_deterministic(self, tmp_path):
        specs = _make_specs(tmp_path)
        a = _run("spec_inventory.py", ["--specs-dir", str(specs)]).stdout
        b = _run("spec_inventory.py", ["--specs-dir", str(specs)]).stdout
        assert a == b

    def test_runtime_output_validates_against_schema(self, tmp_path):
        # QA-4: the producer contract is regression-guarded, not just the example.
        specs = _make_specs(tmp_path)
        inv = json.loads(_run("spec_inventory.py", ["--specs-dir", str(specs)]).stdout)
        schema = load_yaml(SHARED / "spec-inventory.schema.yaml")
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(inv))
        assert errors == [], "; ".join(e.message for e in errors[:5])

    def test_content_hash_portable_across_paths(self, tmp_path):
        # QA-1: identical spec content under different absolute paths -> same hash.
        d1 = tmp_path / "loc_a"
        d2 = tmp_path / "loc_b"
        s1 = _make_specs(d1)
        s2 = _make_specs(d2)
        h1 = json.loads(_run("spec_inventory.py", ["--specs-dir", str(s1)]).stdout)["spec_content_hash"]
        h2 = json.loads(_run("spec_inventory.py", ["--specs-dir", str(s2)]).stdout)["spec_content_hash"]
        assert h1 == h2

    def test_inconsistent_status_spec_approved_back_draft_skipped(self, tmp_path):
        # QA-6: business spec approved but back-spec draft -> not audited (would
        # otherwise extract from an unapproved back-spec).
        specs = _make_specs(tmp_path)
        back = specs / "domains" / "auth" / "back" / "auth.back.md"
        back.write_text(back.read_text().replace("Status: approved", "Status: draft"), encoding="utf-8")
        out = tmp_path / "inv.json"
        skip = tmp_path / "skip.json"
        r = _run("spec_inventory.py", ["--specs-dir", str(specs), "--out", str(out), "--skipped-out", str(skip)])
        assert r.returncode == 3
        assert json.loads(out.read_text())["domains"] == []
        assert any(s["reason"] == "draft_status" for s in json.loads(skip.read_text()))

    def test_openapi_parse_failure_skips_domain(self, tmp_path):
        # QA-3: unparseable openapi -> the domain is skipped (parse_failed), not
        # emitted with zero endpoints (which would fabricate drift).
        specs = _make_specs(tmp_path)
        (specs / "domains" / "auth" / "openapi.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")
        out = tmp_path / "inv.json"
        skip = tmp_path / "skip.json"
        r = _run("spec_inventory.py", ["--specs-dir", str(specs), "--out", str(out), "--skipped-out", str(skip)])
        assert r.returncode == 3  # no approved domains remain
        assert json.loads(out.read_text())["domains"] == []
        assert any(s["reason"] == "parse_failed" for s in json.loads(skip.read_text()))


class TestCodeInventoryExample:
    def test_shipped_example_validates(self):
        # QA-4: code-inventory example conforms at the value level.
        schema = load_yaml(SHARED / "code-inventory.schema.yaml")
        example = load_yaml(SHARED / "code-inventory.yaml")
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(example))
        assert errors == [], "; ".join(e.message for e in errors[:5])


# ── validate_inventory (determinism guard) ────────────────────────────────────

class TestValidateInventory:
    def test_valid_passes(self, tmp_path):
        code = _make_code(tmp_path)
        inv = tmp_path / "ci.json"
        inv.write_text(json.dumps(_code_inventory(code)))
        r = _run("validate_inventory.py", ["--code-inventory", str(inv), "--code-dir", str(code)])
        assert r.returncode == 0, r.stdout

    def test_line_beyond_eof_fails(self, tmp_path):
        code = _make_code(tmp_path)
        ci = _code_inventory(code)
        ci["modules"][0]["endpoints"][0]["evidence"]["line"] = 9999
        inv = tmp_path / "ci.json"
        inv.write_text(json.dumps(ci))
        r = _run("validate_inventory.py", ["--code-inventory", str(inv), "--code-dir", str(code)])
        assert r.returncode == 1
        assert "exceeds file length" in r.stdout

    def test_missing_file_fails(self, tmp_path):
        code = _make_code(tmp_path)
        ci = _code_inventory(code)
        ci["modules"][0]["events"][0]["evidence"]["file"] = "auth/ghost.ts"
        inv = tmp_path / "ci.json"
        inv.write_text(json.dumps(ci))
        r = _run("validate_inventory.py", ["--code-inventory", str(inv), "--code-dir", str(code)])
        assert r.returncode == 1
        assert "does not exist" in r.stdout

    def test_bad_method_fails(self, tmp_path):
        code = _make_code(tmp_path)
        ci = _code_inventory(code)
        ci["modules"][0]["endpoints"][0]["method"] = "fetch"
        inv = tmp_path / "ci.json"
        inv.write_text(json.dumps(ci))
        r = _run("validate_inventory.py", ["--code-inventory", str(inv), "--code-dir", str(code)])
        assert r.returncode == 1
        assert "valid HTTP method" in r.stdout


# ── match_drift ───────────────────────────────────────────────────────────────

def _pipeline(tmp_path, base_path="", drop_get=True):
    specs = _make_specs(tmp_path)
    code = _make_code(tmp_path)
    si = tmp_path / "si.json"
    ci = tmp_path / "ci.json"
    dr = tmp_path / "dr.json"
    _run("spec_inventory.py", ["--specs-dir", str(specs), "--out", str(si)])
    ci.write_text(json.dumps(_code_inventory(code, base_path=base_path, drop_get=drop_get)))
    r = _run("match_drift.py", ["--spec-inventory", str(si), "--code-inventory", str(ci), "--out", str(dr)])
    assert r.returncode == 0, r.stderr
    return json.loads(dr.read_text())


class TestMatchDrift:
    def test_planted_drift_classified(self, tmp_path):
        rep = _pipeline(tmp_path)
        by_ref = {(f["status"], f["artifact_ref"]): f for f in rep["findings"]}
        # getUser in spec, not in code -> missing_in_code, blocking
        assert by_ref[("missing_in_code", "get /users/{param}")]["severity"] == "blocking"
        assert by_ref[("missing_in_code", "get /users/{param}")]["default_action"] == "create_implementation_cr"
        # deleteUser in code, not in spec -> missing_in_spec, major
        assert by_ref[("missing_in_spec", "delete /users/{param}")]["severity"] == "major"
        assert by_ref[("missing_in_spec", "delete /users/{param}")]["default_action"] == "update_spec"
        # extra field lastLoginAt -> missing_in_spec, minor
        assert by_ref[("missing_in_spec", "User.lastLoginAt")]["severity"] == "minor"

    def test_aligned_and_summary(self, tmp_path):
        rep = _pipeline(tmp_path)
        aligned = {(a["artifact_type"], a["artifact_ref"]) for a in rep["aligned"]}
        assert ("endpoint", "post /users") in aligned
        assert ("error_code", "USER_EMAIL_TAKEN") in aligned
        assert ("event", "user.created") in aligned
        assert rep["summary"]["missing_in_code"] == 1
        assert rep["summary"]["missing_in_spec"] == 2

    def test_no_drift_when_code_matches(self, tmp_path):
        rep = _pipeline(tmp_path, drop_get=False)
        # getUser now present; only deleteUser + lastLoginAt remain undocumented
        assert rep["summary"]["missing_in_code"] == 0

    def test_ids_stable_and_sequential(self, tmp_path):
        rep = _pipeline(tmp_path)
        ids = [f["id"] for f in rep["findings"]]
        assert ids == [f"DRIFT-{i:03d}" for i in range(1, len(ids) + 1)]

    def test_deterministic(self, tmp_path):
        a = json.dumps(_pipeline(tmp_path), sort_keys=True)
        b = json.dumps(_pipeline(tmp_path), sort_keys=True)
        assert a == b

    def test_base_path_guard(self, tmp_path):
        rep = _pipeline(tmp_path, base_path="/api/v1")
        bp = [f for f in rep["findings"] if f["artifact_type"] == "base_path"]
        assert len(bp) == 1
        assert bp[0]["status"] == "undecidable"
        assert bp[0]["severity"] == "blocking"
        # endpoint findings suppressed for that domain
        assert not [f for f in rep["findings"] if f["artifact_type"] == "endpoint"]

    def test_unmatched_module_skipped(self, tmp_path):
        specs = _make_specs(tmp_path)
        code = _make_code(tmp_path)
        si = tmp_path / "si.json"
        ci = tmp_path / "ci.json"
        _run("spec_inventory.py", ["--specs-dir", str(specs), "--out", str(si)])
        inv = _code_inventory(code)
        inv["modules"][0]["id"] = "billing"  # no spec domain 'billing'
        ci.write_text(json.dumps(inv))
        r = _run("match_drift.py", ["--spec-inventory", str(si), "--code-inventory", str(ci)])
        rep = json.loads(r.stdout)
        reasons = {s["domain"]: s["reason"] for s in rep["skipped"]}
        assert reasons.get("billing") == "no_spec_domain"
        assert reasons.get("auth") == "no_code_module"


# ── render_report ─────────────────────────────────────────────────────────────

class TestRenderReport:
    def test_renders_summary_and_findings(self, tmp_path):
        rep = _pipeline(tmp_path)
        dr = tmp_path / "dr.json"
        dr.write_text(json.dumps(rep))
        r = _run("render_report.py", ["--report", str(dr)])
        assert r.returncode == 0
        assert "# Spec ↔ Code Drift Report" in r.stdout
        assert "DRIFT-001" in r.stdout
        assert "## Summary" in r.stdout

    def test_deterministic(self, tmp_path):
        rep = _pipeline(tmp_path)
        dr = tmp_path / "dr.json"
        dr.write_text(json.dumps(rep))
        a = _run("render_report.py", ["--report", str(dr)]).stdout
        b = _run("render_report.py", ["--report", str(dr)]).stdout
        assert a == b

    def test_empty_findings_message(self, tmp_path):
        rep = _pipeline(tmp_path, drop_get=False)
        rep["findings"] = []
        dr = tmp_path / "dr.json"
        dr.write_text(json.dumps(rep))
        r = _run("render_report.py", ["--report", str(dr)])
        assert "No actionable drift" in r.stdout


# ── schema conformance (value level) ──────────────────────────────────────────

class TestReportSchemaConformance:
    def test_generated_report_validates_against_schema(self, tmp_path):
        rep = _pipeline(tmp_path)
        schema = load_yaml(SHARED / "drift-report.schema.yaml")
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(rep))
        assert errors == [], "; ".join(e.message for e in errors[:5])
