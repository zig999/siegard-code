"""R05c — artifact ↔ checker parity.

Three shipped artifacts once disagreed about the same contract:

  u-test-runner.md        wrote JSON to `.orch/test-reports/<task_id>.json`
  orchestrator-test.md    told the worker to register `<session>/…-report.md`
  check_all_tests_passed  matched neither `**result:** passed`

The worker obeyed the dispatch prompt — the one it actually receives — so the
gate read `field_absent` on a green suite. Nothing in the repository connected
"what the orchestrator asks for" to "what the gate can read".

This module is that connection, in both directions:

  * the path a worker registers is the path its gate parses (shape and location);
  * a template's own example, fed through the real checker parser, yields the
    value the checker is looking for.

Templates are the contract as authored; checkers are the contract as enforced.
Neither is authoritative alone.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
sys.path.insert(0, str(dist / "lib"))


def _load(path: Path, name: str):
    """Import a checker by path — they are scripts, not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fenced_blocks(text: str, lang: str | None = None) -> list[str]:
    pattern = rf"```{lang or r'[a-z]*'}\n(.*?)```"
    return [m.group(1) for m in re.finditer(pattern, text, re.DOTALL)]


# ---------------------------------------------------------------------------
# Registered path ↔ gated path
# ---------------------------------------------------------------------------

class TestRegisteredPathMatchesGatedPath:
    """The artifact a worker registers must be the artifact its gate reads."""

    def test_test_runner_registers_the_json_report(self):
        worker = (dist / "agents" / "dev" / "u-test-runner.md").read_text(
            encoding="utf-8")
        registered = re.findall(r'"artifacts":\s*\[([^\]]*)\]', worker)
        assert registered, "u-test-runner registers no artifact"
        for entry in registered:
            assert "-report.json" in entry, (
                f"u-test-runner registers {entry!r}; check_all_tests_passed parses "
                "JSON structurally — registering the .md is what produced "
                "field_absent on a green suite"
            )
            assert ".md" not in entry

    def test_orchestrator_test_asks_for_the_same_path(self):
        orch = (dist / "agents" / "orchestrator-test.md").read_text(encoding="utf-8")
        assert "-report.json" in orch
        assert "test-reports/<task_id>-report.md] when done" not in orch, (
            "the dispatch prompt is what the worker actually obeys — it must not "
            "ask for an artifact the gate cannot parse"
        )

    def test_test_report_path_is_session_scoped(self):
        """A bare `.orch/test-reports/` collides across concurrent workflows."""
        worker = (dist / "agents" / "dev" / "u-test-runner.md").read_text(
            encoding="utf-8")
        for entry in re.findall(r'"artifacts":\s*\[([^\]]*)\]', worker):
            assert "SESSION_DIR" in entry or "session" in entry.lower(), (
                f"{entry!r} is not session-scoped"
            )


# ---------------------------------------------------------------------------
# Template example ↔ checker parser
# ---------------------------------------------------------------------------

class TestTestReportTemplateIsParseable:
    @property
    def _extract(self):
        mod = _load(
            dist / "skills" / "phase-test-rules" / "scripts" / "check_all_tests_passed.py",
            "cat_passed")
        return mod._extract_result

    def test_worker_json_example_yields_passed(self):
        """The JSON shape u-test-runner documents must read as `passed`."""
        worker = (dist / "agents" / "dev" / "u-test-runner.md").read_text(
            encoding="utf-8")
        blocks = [b for b in _fenced_blocks(worker, "json") if '"result"' in b]
        assert blocks, "u-test-runner documents no JSON report example"
        example = blocks[0].replace('"passed" | "failed" | "blocked"', '"passed"')
        example = re.sub(r'null \| "critical".*', "null", example)
        example = example.replace("<task_id>", "t1").replace("<workflow_id>", "wf")
        example = example.replace("<stack>", "be").replace("<path>", "d.md")
        example = example.replace("<cmd>", "pytest")
        example = example.replace('"<last 500 chars of stdout+stderr>"', '"ok"')
        example = example.replace('"<one-line outcome>"', '"ok"')
        assert self._extract(example) == "passed", (
            "the documented JSON report is not readable by check_all_tests_passed"
        )

    def test_schema_declares_the_gated_field(self):
        schema = (dist / "skills" / "u-shared-templates"
                  / "test-report.schema.yaml").read_text(encoding="utf-8")
        assert re.search(r"^\s*result\s*:", schema, re.MULTILINE), (
            "the schema must declare the field the gate reads"
        )

    def test_markdown_fallback_is_still_tolerated(self):
        """Defence in depth: a contract slip must not invert a green verdict."""
        assert self._extract("**result:** passed") == "passed"
        assert self._extract("**Result:** PASSED") == "passed"

    def test_absent_field_is_not_silently_a_pass(self):
        assert self._extract("# report with no result field") is None


class TestQaReportTemplateIsParseable:
    @property
    def _verdict(self):
        mod = _load(
            dist / "skills" / "phase-review-rules" / "scripts" / "read_qa_verdict.py",
            "rqv")
        return mod.extract_verdict

    @pytest.mark.parametrize("stack", ["be", "fe"])
    def test_template_frontmatter_yields_approved(self, stack):
        tmpl = (dist / "skills" / f"u-{stack}-templates" / "qa-report.md").read_text(
            encoding="utf-8")
        blocks = [b for b in _fenced_blocks(tmpl) if "verdict:" in b]
        assert blocks, f"u-{stack}-templates/qa-report.md shows no verdict example"
        filled = (blocks[0]
                  .replace("<approved|rejected>", "approved")
                  .replace("<true|false>", "true")
                  .replace("<task_id>", "review_dev_tc_001"))
        assert self._verdict(filled) == "approved", (
            f"u-{stack} qa-report frontmatter is not readable by read_qa_verdict"
        )

    @pytest.mark.parametrize("stack", ["be", "fe"])
    def test_template_declares_documentation_verified(self, stack):
        tmpl = (dist / "skills" / f"u-{stack}-templates" / "qa-report.md").read_text(
            encoding="utf-8")
        assert "documentation_verified" in tmpl

    @pytest.mark.parametrize("stack", ["be", "fe"])
    def test_documentation_verified_reads_true_from_the_template(self, stack):
        mod = _load(
            dist / "skills" / "phase-review-rules" / "scripts"
            / "check_documentation_verified.py", f"cdv_{stack}")
        tmpl = (dist / "skills" / f"u-{stack}-templates" / "qa-report.md").read_text(
            encoding="utf-8")
        blocks = [b for b in _fenced_blocks(tmpl) if "documentation_verified" in b]
        filled = blocks[0].replace("<true|false>", "true")
        # The checker's own frontmatter reader, whatever its name, must see it.
        reader = getattr(mod, "_extract_documentation_verified", None) \
            or getattr(mod, "_read_flag", None)
        if reader is None:
            assert re.search(r"^documentation_verified:\s*true\s*$", filled,
                             re.MULTILINE), "template value is not a bare boolean"
        else:
            assert reader(filled) is True


class TestDeliveryTemplateIsParseable:
    @pytest.mark.parametrize("stack", ["be", "fe"])
    def test_qa_ready_matches_the_gate_regex(self, stack):
        mod = _load(
            dist / "skills" / "phase-dev-rules" / "scripts"
            / "check_all_deliveries_qa_ready.py", f"cadq_{stack}")
        tmpl = (dist / "skills" / f"u-{stack}-templates" / "delivery.md").read_text(
            encoding="utf-8")
        assert "qa_ready" in tmpl, f"u-{stack} delivery template omits qa_ready"
        # The template shows the choice; a produced artifact commits to one value.
        assert mod._QA_READY_RE.search("qa_ready: true"), (
            "the gate cannot match the documented qa_ready form"
        )
        assert not mod._QA_READY_RE.search("qa_ready: false")


# ---------------------------------------------------------------------------
# Coverage — every gated field has a parity test
# ---------------------------------------------------------------------------

class TestParityCoverage:
    def test_every_worker_gate_field_is_covered_here(self):
        """Keeps this module honest as W08's registry grows.

        u-worker-compliance's GATE_FIELDS_BY_WORKER is the artifact -> checker
        contract; each field in it needs a parity assertion somewhere above.
        """
        sys.path.insert(0, str(dist / "skills" / "u-worker-compliance" / "scripts"))
        import importlib
        cw = importlib.import_module("check_worker")
        importlib.reload(cw)
        fields = {f for pairs in cw.GATE_FIELDS_BY_WORKER.values() for f, _ in pairs}
        covered = Path(__file__).read_text(encoding="utf-8")
        missing = [f for f in fields if f not in covered]
        assert not missing, (
            f"gate fields with no parity test in this module: {missing}"
        )
