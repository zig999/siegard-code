"""BR pair discipline — .spec.md is the single normative source.

Field report (mwoassistant, 2026-07-28): every BR number existed in both
.spec.md and .back.md across three audited domains (72/72), with 0
complementary pairs in a 12-pair sample — because TEMPLATE.back.md asked the
back writer for the same "objective and testable rule" the spec already held.
The duplication hid two real defects (8-vs-9 column count, numbering that
claimed to mirror and did not). check_br_pairs.py makes the citation contract
mechanical; these tests pin its behavior.
"""
import json
import subprocess
import sys

from conftest import get_dist_dir

SCRIPT = get_dist_dir() / "skills" / "u-spec-validation" / "scripts" / "check_br_pairs.py"

SPEC_SHORT = """# Demo -- Spec

## 4. Business Rules

### BR-01 -- Uppercase rowstate
Rowstate comparisons use uppercase literals.
"""

BACK_CITED = """# Demo -- Back-end Spec

## 3. Business Rules (BR)

### BR-01 -- Uppercase rowstate
**Related UC:** UC-01
**Source rule:** `demo.spec.md` BR-01
**Description:** Zod enum guard in assignments.dto.ts; fixture covers out-of-enum input.
**Error returned:** HTTP 422 -- error.code: `VALIDATION_INVALID_FORMAT`
"""


def _write_domain(root, domain, spec_body, back_body):
    d = root / "domains" / domain
    (d / "back").mkdir(parents=True)
    (d / f"{domain}.spec.md").write_text(spec_body, encoding="utf-8")
    (d / "back" / f"{domain}.back.md").write_text(back_body, encoding="utf-8")


def _run(specs_dir, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--specs-dir", str(specs_dir), *args],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, json.loads(proc.stdout)


class TestCitationContract:
    def test_cited_and_resolvable_passes(self, tmp_path):
        _write_domain(tmp_path, "demo", SPEC_SHORT, BACK_CITED)
        rc, out = _run(tmp_path)
        assert rc == 0
        assert out["status"] == "ok"
        assert out["brs_checked"] == 1
        assert out["violations"] == []

    def test_missing_citation_is_blocking(self, tmp_path):
        back = BACK_CITED.replace("**Source rule:** `demo.spec.md` BR-01\n", "")
        _write_domain(tmp_path, "demo", SPEC_SHORT, back)
        rc, out = _run(tmp_path)
        assert rc == 2
        assert out["status"] == "fail"
        assert out["violations"][0]["type"] == "missing_source_citation"
        assert out["violations"][0]["severity"] == "blocking"

    def test_unresolved_citation_is_blocking(self, tmp_path):
        back = BACK_CITED.replace("BR-01\n**Description", "BR-99\n**Description")
        _write_domain(tmp_path, "demo", SPEC_SHORT, back)
        rc, out = _run(tmp_path)
        assert rc == 2
        assert out["violations"][0]["type"] == "unresolved_citation"

    def test_inline_see_citation_is_accepted(self, tmp_path):
        back = BACK_CITED.replace(
            "**Source rule:** `demo.spec.md` BR-01",
            "Enforcement detail (see demo.spec.md BR-01 for the rule).",
        )
        _write_domain(tmp_path, "demo", SPEC_SHORT, back)
        rc, out = _run(tmp_path)
        assert rc == 0 and out["violations"] == []

    def test_prefixed_back_headings_are_checked(self, tmp_path):
        """Field variants BR-BE-NN / BE-BR-NN must not escape the gate."""
        back = BACK_CITED.replace("### BR-01", "### BR-BE-01").replace(
            "**Source rule:** `demo.spec.md` BR-01\n", "")
        _write_domain(tmp_path, "demo", SPEC_SHORT, back)
        rc, out = _run(tmp_path)
        assert rc == 2
        assert out["violations"][0]["back_br"] == "BR-BE-01"


class TestRestatementHeuristic:
    SPEC_LONG = """# Demo -- Spec

## 4. Business Rules

### BR-01 -- Window rule
Preventive scanning window converts timestamps between coordinated universal
time and regional offset before comparing assignment execution records against
signature predicates during batch population filtering operations.
"""

    def test_same_language_copy_is_a_warning_not_blocking(self, tmp_path):
        rule_text = self.SPEC_LONG.split("Window rule\n")[1]
        back = BACK_CITED.replace(
            "**Description:** Zod enum guard in assignments.dto.ts; fixture covers out-of-enum input.",
            f"**Description:** {rule_text}",
        )
        _write_domain(tmp_path, "demo", self.SPEC_LONG, back)
        rc, out = _run(tmp_path)
        assert rc == 0, "restatement is a warning, never blocking"
        assert out["warnings"] == 1
        assert out["violations"][0]["type"] == "restatement_suspected"

    def test_cross_language_duplicate_does_not_trigger_overlap(self, tmp_path):
        """Measured limitation: pt-BR spec vs EN back scores near zero overlap.
        The citation is the contract; the heuristic must stay silent here."""
        spec_pt = self.SPEC_LONG.replace(
            "Preventive scanning window converts timestamps between coordinated universal\n"
            "time and regional offset before comparing assignment execution records against\n"
            "signature predicates during batch population filtering operations.",
            "Janela preventiva converte carimbos temporais entre horario universal\n"
            "coordenado e deslocamento regional antes de comparar registros contra\n"
            "predicados de assinatura durante filtragem de populacao.",
        )
        _write_domain(tmp_path, "demo", spec_pt, BACK_CITED)
        rc, out = _run(tmp_path)
        assert rc == 0 and out["warnings"] == 0


class TestCli:
    def test_domain_filter(self, tmp_path):
        _write_domain(tmp_path, "alpha", SPEC_SHORT, BACK_CITED)
        bad_back = BACK_CITED.replace("**Source rule:** `demo.spec.md` BR-01\n", "")
        _write_domain(tmp_path, "beta", SPEC_SHORT, bad_back)
        rc, out = _run(tmp_path, "--domain", "alpha")
        assert rc == 0 and out["checked_domains"] == ["alpha"]

    def test_missing_specs_dir_is_script_error(self, tmp_path):
        rc, out = _run(tmp_path / "nope")
        assert rc == 1
        assert out["status"] == "error"

    def test_domain_without_back_file_is_skipped(self, tmp_path):
        d = tmp_path / "domains" / "solo"
        d.mkdir(parents=True)
        (d / "solo.spec.md").write_text(SPEC_SHORT, encoding="utf-8")
        rc, out = _run(tmp_path)
        assert rc == 0 and out["brs_checked"] == 0
