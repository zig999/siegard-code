"""R16 — spec workers load the sections they need, not whole files.

Every spec worker used to carry every section of every artifact. Measured on real
runs: 51,701 and 57,213 estimated tokens against a 60,000 block threshold — 86% to
95% of the ceiling. That ceiling is also why `targeted` mode is capped at one
concurrent worker, so context pressure is not only cost: it is why the cheap path
cannot be parallel.

**The premise that did NOT survive measurement.** The parecer proposed removing or
merging `back/*.back.md` as redundant with `.spec.md`. Measured textual similarity
between their same-named sections is 7–11% (3–4 identical long lines): the
`.back.md` states where a rule is enforced, with which error code and status,
while the `.spec.md` states the rule. It is a second layer, not a copy. Deleting
content was never an available saving; reading less of it is.

**Honest size of the win.** −20% for `u-spec-back` and `u-spec-validator`, −75%
for `u-spec-front`, 0% for `u-spec-reviewer` by design. The back/validator saving
is modest because §Business Rules is the largest section and those workers
genuinely need it — the 89% figure a naive selection produces is not a number any
real worker achieves.

**The safety property**: full awareness, partial bodies. The extractor always
returns the complete section index marked requested/omitted, so a worker knows
what exists and can ask for more. Partial loading must never become partial
awareness.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
READER = dist / "skills" / "u-spec-templates" / "scripts" / "read_spec_sections.py"
TEMPLATES = dist / "skills" / "u-spec-templates"

SCOPED_WORKERS = ["u-spec-back", "u-spec-front", "u-spec-validator"]
WHOLE_FILE_WORKERS = ["u-spec-reviewer", "u-spec-compliance"]


def _run(spec: Path, *args) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(READER), "--file", str(spec), *args],
        capture_output=True, text=True, timeout=60)
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


def _module():
    spec = importlib.util.spec_from_file_location("rss", READER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def spec_file(tmp_path):
    """A spec shaped like the shipped templates: numbered §, plus a bare Changelog."""
    p = tmp_path / "domain.spec.md"
    p.write_text(
        "# Domain — Business Specification\n"
        "\nStatus: approved\nVersion: 1.2.0\n"
        "\n## 1. Overview\nover1\nover2\n"
        "\n## 2. Actors\nact1\n"
        "\n## 3. Use Cases\nuc1\nuc2\nuc3\n"
        "\n## 4. Business Rules\nbr1\nbr2\nbr3\nbr4\n"
        "\n## 5. State Machine\nst1\n"
        "\n## 6. Error Behaviors\nerr1\n"
        "\n## 9. Local Glossary\ngl1\n"
        "\n## Changelog\nchg1\n",
        encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Full awareness, partial bodies
# ---------------------------------------------------------------------------

class TestIndexIsAlwaysComplete:
    def test_index_lists_every_section_even_when_one_is_requested(self, spec_file):
        rc, out = _run(spec_file, "--sections", "4")
        assert rc == 0
        assert out["total_sections"] == 8
        assert len(out["index"]) == 8, (
            "partial loading must never become partial awareness"
        )

    def test_omitted_sections_are_marked_not_hidden(self, spec_file):
        _, out = _run(spec_file, "--sections", "4")
        states = {s["title"]: s["state"] for s in out["index"]}
        assert states["Business Rules"] == "requested"
        assert states["Overview"] == "omitted"
        assert states["Changelog"] == "omitted"

    def test_index_carries_line_counts_so_cost_is_visible(self, spec_file):
        _, out = _run(spec_file, "--sections", "1")
        assert all(isinstance(s["lines"], int) and s["lines"] > 0
                   for s in out["index"])

    def test_body_of_omitted_sections_is_absent(self, spec_file):
        _, out = _run(spec_file, "--sections", "4")
        assert "br1" in out["content"]
        assert "over1" not in out["content"]
        assert "gl1" not in out["content"]

    def test_preamble_is_always_included(self, spec_file):
        """It carries which artifact and which version this is."""
        _, out = _run(spec_file, "--sections", "5")
        assert "Status: approved" in out["content"]
        assert "Version: 1.2.0" in out["content"]

    def test_index_only_returns_no_bodies(self, spec_file):
        rc, out = _run(spec_file, "--index-only")
        assert rc == 0 and out["content"] == ""
        assert len(out["index"]) == 8

    def test_all_is_an_explicit_opt_out(self, spec_file):
        rc, out = _run(spec_file, "--all")
        assert rc == 0
        assert out["lines_loaded"] == out["lines_total"]
        assert all(s["state"] == "requested" for s in out["index"])


class TestSelectors:
    def test_by_number(self, spec_file):
        _, out = _run(spec_file, "--sections", "4")
        assert out["requested"] == ["4"]

    @pytest.mark.parametrize("form", ["4", "4.", "§4"])
    def test_number_forms_are_equivalent(self, spec_file, form):
        _, out = _run(spec_file, "--sections", form)
        assert out["requested"] == ["4"]

    def test_by_title_substring_case_insensitive(self, spec_file):
        _, out = _run(spec_file, "--sections", "business rules")
        assert out["requested"] == ["4"]

    def test_unnumbered_section_is_addressable_by_title(self, spec_file):
        _, out = _run(spec_file, "--sections", "Changelog")
        assert out["requested"] == ["Changelog"]
        assert "chg1" in out["content"]

    def test_multiple_selectors_return_in_file_order(self, spec_file):
        _, out = _run(spec_file, "--sections", "5,3")
        assert out["content"].index("uc1") < out["content"].index("st1")

    def test_unmatched_selector_exits_two_and_is_reported(self, spec_file):
        """A silent miss would hand the worker less than it asked for."""
        rc, out = _run(spec_file, "--sections", "4,Ghost Section")
        assert rc == 2
        assert out["unmatched_selectors"] == ["Ghost Section"]
        assert "br1" in out["content"], "the matched sections are still returned"

    def test_no_selector_at_all_is_a_usage_error(self, spec_file):
        proc = subprocess.run(
            [sys.executable, str(READER), "--file", str(spec_file)],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 1
        assert json.loads(proc.stderr)["reason"] == "no_selectors"

    def test_missing_file_errors(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(READER), "--file", str(tmp_path / "nope.md"),
             "--all"], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 1
        assert json.loads(proc.stderr)["reason"] == "file_not_found"


class TestParsingIsFaithful:
    def test_reduction_is_reported(self, spec_file):
        _, out = _run(spec_file, "--sections", "5")
        assert 0 < out["reduction_pct"] < 100
        assert out["lines_loaded"] < out["lines_total"]

    def test_sections_reassemble_to_the_original(self, spec_file):
        """--all must be lossless, or scoping is unsafe at any granularity."""
        mod = _module()
        text = spec_file.read_text(encoding="utf-8")
        sections, preamble = mod.parse_sections(text)
        rebuilt = "\n".join(preamble + [l for s in sections for l in s["body"]])
        assert rebuilt.strip() == text.strip()

    def test_level_three_headings_stay_inside_their_section(self, tmp_path):
        """`### BR-01` belongs to §4, not to a section of its own."""
        p = tmp_path / "s.md"
        p.write_text("# T\n\n## 4. Business Rules\n\n### BR-01 — x\nbody\n"
                     "\n## 5. State Machine\nst\n", encoding="utf-8")
        _, out = _run(p, "--sections", "4")
        assert out["total_sections"] == 2
        assert "BR-01" in out["content"] and "st" not in out["content"]

    def test_file_with_no_sections_is_not_a_crash(self, tmp_path):
        p = tmp_path / "flat.md"
        p.write_text("# Just a title\n\nsome prose\n", encoding="utf-8")
        rc, out = _run(p, "--all")
        assert rc == 0 and out["total_sections"] == 0
        assert "some prose" in out["content"]


# ---------------------------------------------------------------------------
# Wiring — and the deliberate exceptions
# ---------------------------------------------------------------------------

class TestWorkersAreWired:
    @pytest.mark.parametrize("worker", SCOPED_WORKERS)
    def test_worker_uses_the_reader(self, worker):
        text = (dist / "agents" / "spec" / f"{worker}.md").read_text(encoding="utf-8")
        assert "read_spec_sections.py" in text

    @pytest.mark.parametrize("worker", SCOPED_WORKERS)
    def test_worker_declares_which_sections(self, worker):
        text = (dist / "agents" / "spec" / f"{worker}.md").read_text(encoding="utf-8")
        assert "--sections" in text
        assert "only (measured" in text, (
            "the declaration must state the measured effect, not just the intent"
        )

    @pytest.mark.parametrize("worker", SCOPED_WORKERS)
    def test_worker_is_told_how_to_ask_for_more(self, worker):
        """Without the escape hatch, a wrong section list silently degrades output."""
        text = (dist / "agents" / "spec" / f"{worker}.md").read_text(encoding="utf-8")
        idx = text.index("read_spec_sections.py")
        window = text[idx:idx + 1600]
        assert "re-run with it added" in window
        assert "--all" in window

    def test_spec_back_step_one_no_longer_says_read_the_complete_spec(self):
        """An instruction to read the whole file would override the scoped input."""
        text = (dist / "agents" / "spec" / "u-spec-back.md").read_text(encoding="utf-8")
        assert "Read the complete `.spec.md`" not in text

    def test_validator_evidence_check_is_unaffected(self):
        """verify_evidence.py reads from disk, so scoping must not narrow it."""
        text = (dist / "agents" / "spec" / "u-spec-validator.md").read_text(
            encoding="utf-8")
        # Match on substance, not on an exact line: the note is wrapped and uses
        # backticks, and pinning the literal makes the test brittle rather than
        # meaningful.
        assert "Evidence re-execution check is unaffected" in text, (
            "scoping the validator's inputs must not be read as scoping what "
            "verify_evidence.py checks — it reads the file from disk itself"
        )
        assert "never narrows what gets verified" in text


class TestWholeFileReadersAreDeliberate:
    @pytest.mark.parametrize("worker", WHOLE_FILE_WORKERS)
    def test_exception_is_documented_not_accidental(self, worker):
        text = (dist / "agents" / "spec" / f"{worker}.md").read_text(encoding="utf-8")
        assert "do NOT section-scope this worker" in text

    @pytest.mark.parametrize("worker", WHOLE_FILE_WORKERS)
    def test_exception_states_its_reason(self, worker):
        text = (dist / "agents" / "spec" / f"{worker}.md").read_text(encoding="utf-8")
        idx = text.index("do NOT section-scope this worker")
        window = text[idx:idx + 700]
        assert "completeness" in window or "gap" in window

    @pytest.mark.parametrize("worker", WHOLE_FILE_WORKERS)
    def test_exception_workers_do_not_call_the_reader(self, worker):
        text = (dist / "agents" / "spec" / f"{worker}.md").read_text(encoding="utf-8")
        assert "--sections" not in text


class TestSkillDeclaresTheScript:
    def test_frontmatter_no_longer_claims_no_scripts(self):
        text = (TEMPLATES / "SKILL.md").read_text(encoding="utf-8")
        assert "Resource bundle — no scripts" not in text

    def test_frontmatter_declares_allowed_tools(self):
        """LP3: a skill that ships scripts must declare its tools (P6)."""
        text = (TEMPLATES / "SKILL.md").read_text(encoding="utf-8")
        head = text[:text.index("---", 5)]
        assert "allowed-tools:" in head

    def test_measured_numbers_are_documented(self):
        text = (TEMPLATES / "SKILL.md").read_text(encoding="utf-8")
        assert "−20%" in text or "-20%" in text
        assert "−75%" in text or "-75%" in text

    def test_the_modest_saving_is_explained_not_hidden(self):
        """Overselling the win invites the reader to scope the reviewer too."""
        text = (TEMPLATES / "SKILL.md").read_text(encoding="utf-8")
        assert "modest" in text
        assert "genuinely need it" in text

    def test_whole_file_exceptions_are_named_in_the_skill(self):
        text = (TEMPLATES / "SKILL.md").read_text(encoding="utf-8")
        assert "u-spec-reviewer" in text and "u-spec-compliance" in text
