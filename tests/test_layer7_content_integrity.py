"""Layer 7 — Content Integrity Guardrails: specific content rules per GUARD codes."""
import re
import pytest
from conftest import get_dist_dir, parse_frontmatter

dist = get_dist_dir()


def _read(rel_path):
    return (dist / rel_path).read_text(encoding="utf-8")


def _walk_markdown(directory):
    results = []
    if not directory.exists():
        return results
    for entry in sorted(directory.rglob("*")):
        if entry.is_file() and entry.suffix in (".md", ".yaml"):
            results.append(entry)
    return results


class TestDevI01UiSpecGateFieldName:
    def test_guard01_u_fe_ui_no_task_contracts_covered(self):
        content = _read("agents/dev/u-fe-ui.md")
        assert "task_contracts_covered" not in content, "GUARD-01"

    def test_guard02_u_fe_development_no_task_contracts_covered(self):
        content = _read("skills/u-fe-development/SKILL.md")
        assert "task_contracts_covered" not in content, "GUARD-02"

    def test_guard03_ui_agent_output_schema_contains_tasks_covered(self):
        schema_path = dist / "skills" / "u-shared-templates" / "ui-agent-output.schema.yaml"
        if not schema_path.exists():
            pytest.skip("schema not yet in this branch")
        content = schema_path.read_text(encoding="utf-8")
        assert "tasks_covered" in content, "GUARD-03"


class TestSpecI03ReverseSpecWriterColumns:
    def test_guard12_reverse_spec_writer_no_method_path_in_s1(self):
        content = _read("agents/reverse-spec/u-reverse-spec-writer.md")
        lines = content.split("\n")
        sect1_idx = next((i for i, l in enumerate(lines) if "§1 Consumed Endpoints" in l), -1)
        if sect1_idx >= 0:
            sect1_line = lines[sect1_idx]
            assert "Method+Path" not in sect1_line, "GUARD-12a: §1 should not list Method+Path as column"
            assert "Auth required" not in sect1_line, "GUARD-12b: §1 should not list Auth required as column"


class TestSpecI04SpecValidatorModel:
    def test_guard13_spec_validator_uses_correct_model(self):
        fm = parse_frontmatter(dist / "agents" / "spec" / "u-spec-validator.md")
        assert fm.get("model") == "claude-sonnet-4-6", "GUARD-13"


class TestDevI08BeQualifiedPaths:
    def test_guard19_be_developer_qualified_path_for_spec_feedback_loop(self):
        content = _read("agents/dev/u-be-developer.md")
        lines = [l for l in content.split("\n") if "spec-feedback-loop" in l]
        for line in lines:
            assert ".claude/agents/spec/protocols/" in line, \
                f'Line should have qualified path: "{line}"'


class TestDevI09ArchReviewerGodService:
    def test_guard20_architecture_reviewer_no_gte20_for_god_service(self):
        content = _read("agents/dev/u-architecture-reviewer.md")
        lines = [l for l in content.split("\n") if "god_service" in l or "public methods" in l]
        detection_line = next((l for l in lines if "Detection" in l or "public methods" in l), None)
        if detection_line:
            assert "≥20" not in detection_line, "GUARD-20: should not use ≥20"
            assert "20 public methods" not in detection_line, "GUARD-20: should not use '20 public methods'"


class TestSpecI07AnalyzerNoDuplicateSectionNumbers:
    def test_guard24_reverse_spec_analyzer_no_duplicate_sections(self):
        content = _read("agents/reverse-spec/u-reverse-spec-analyzer.md")
        matches = re.findall(r"^## (\d+)\.", content, re.MULTILINE)
        assert len(matches) == len(set(matches)), "GUARD-24: duplicate section numbers found"


class TestSpecI08SpecValidationNoAlertSeverity:
    def test_guard25_spec_validation_no_alert_severity(self):
        content = _read("skills/u-spec-validation/SKILL.md")
        assert not re.search(r"\| `alert` \|", content), "GUARD-25a"
        assert not re.search(r"or `alert`", content), "GUARD-25b"
        assert not re.search(r"flag as alert", content), "GUARD-25c"


class TestDevI11TcTypeSchemaEnum:
    @pytest.mark.parametrize("label,rel", [
        ("u-be-standards/SKILL.md", "skills/u-be-standards/SKILL.md"),
        ("u-fe-standards/SKILL.md", "skills/u-fe-standards/SKILL.md"),
    ])
    def test_guard30_no_non_canonical_tc_type_names(self, label, rel):
        content = _read(rel)
        assert not re.search(r"\| \*\*Improvement\*\* \|", content), f"GUARD-30a: {label}"
        assert not re.search(r"\| \*\*Enhancement\*\* \|", content), f"GUARD-30b: {label}"
        assert not re.search(r"\| \*\*Visual adjustment\*\* \|", content), f"GUARD-30c: {label}"


class TestSpecI12UspecRequirementParam:
    def test_guard35_u_spec_documents_requirement_resolution(self):
        content = _read("commands/u-spec.md")
        assert "Resolving `REQUIREMENT`" in content, "GUARD-35a"

    def test_guard35d_u_spec_usage_includes_requirement(self):
        content = _read("commands/u-spec.md")
        assert '"requirement"' in content, "GUARD-35d"


class TestSpecI15ImproveHashEliminated:
    @pytest.mark.parametrize("rel", [
        "skills/u-improve/SKILL.md",
        "commands/u-dev.md",
    ])
    def test_guard38_no_improve_hash_reference(self, rel):
        content = _read(rel)
        assert "improve##.md" not in content, f"GUARD-38: {rel}"


class TestBeI02PaginationLocation:
    @pytest.mark.parametrize("rel", [
        "skills/u-be-development/SKILL.md",
        "agents/dev/u-be-developer.md",
        "skills/u-be-standards/SKILL.md",
        "agents/dev/u-be-qa.md",
    ])
    def test_guard40_references_pagination_ts(self, rel):
        content = _read(rel)
        assert "src/types/pagination.ts" in content, f"GUARD-40: {rel}"


class TestBeI03NullListRule:
    @pytest.mark.parametrize("rel,shapes", [
        ("skills/u-be-standards/SKILL.md", ["{ data: [], pagination:", "{ data: [], meta: { page, limit"]),
        ("agents/dev/u-be-developer.md", ["{ data: [], pagination:"]),
        ("agents/dev/u-be-qa.md", ["{ data: [], pagination:"]),
    ])
    def test_guard41_no_ad_hoc_pagination_shapes(self, rel, shapes):
        content = _read(rel)
        for shape in shapes:
            assert shape not in content, f'GUARD-41: {rel} contains banned shape "{shape}"'


class TestBeI04DiPattern:
    @pytest.mark.parametrize("rel,needle", [
        ("skills/u-be-development/SKILL.md", "manual-factory"),
        ("skills/u-be-standards/SKILL.md", "manual-factory"),
        ("agents/dev/u-be-developer.md", "## Dependency Injection"),
        ("agents/dev/u-be-qa.md", "## Dependency Injection"),
    ])
    def test_guard42_di_requirements(self, rel, needle):
        content = _read(rel)
        assert needle in content, f"GUARD-42: {rel}"


class TestBeI05DtoPattern:
    def test_guard43a_be_development_uses_zod(self):
        content = _read("skills/u-be-development/SKILL.md")
        assert "zod" in content, "GUARD-43a"
        assert "validation_library" in content, "GUARD-43a"

    def test_guard43b_be_developer_mentions_req_body_prohibition(self):
        content = _read("agents/dev/u-be-developer.md")
        assert "req.body" in content, "GUARD-43b: prohibition rule must exist"

    def test_guard43c_be_qa_docs_req_body_as_high_bug(self):
        content = _read("agents/dev/u-be-qa.md")
        assert "req.body" in content, "GUARD-43c: req.body security risk must be in QA"
        assert "High" in content, "GUARD-43c: must classify req.body as High bug"

    def test_guard43d_be_standards_has_dto_section(self):
        content = _read("skills/u-be-standards/SKILL.md")
        assert "DTO and Validation Pattern" in content, "GUARD-43d"


class TestBeI06FactoriesFolder:
    @pytest.mark.parametrize("rel", [
        "skills/u-be-development/SKILL.md",
        "agents/dev/u-be-developer.md",
    ])
    def test_guard44_factories_in_folder_structure(self, rel):
        content = _read(rel)
        assert "factories/" in content, f"GUARD-44: {rel}"


class TestDevI14UBugReportEliminated:
    def test_guard45a_u_bug_report_command_deleted(self):
        assert not (dist / "commands" / "u-bug-report.md").exists(), \
            "dist/commands/u-bug-report.md must not exist"

    def test_guard45b_u_bug_report_skill_deleted(self):
        assert not (dist / "skills" / "u-bug-report").exists(), \
            "dist/skills/u-bug-report/ must not exist"

    def test_guard45c_u_bug_mode_deleted(self):
        assert not (dist / "agents" / "dev" / "protocols" / "u-bug-mode.md").exists(), \
            "u-bug-mode.md must not exist"

    MIGRATION_HISTORY_ALLOWLIST = {
        "skills/u-improve/SKILL.md",
        "agents/dev/protocols/u-improve-mode.md",
        "skills/u-shared-templates/improve-handoff-envelope.schema.yaml",
        "agents/dev/u-be-orchestrator-protocols.md",
        "agents/dev/u-fe-orchestrator-protocols.md",
    }
    FORBIDDEN_PATTERNS = [
        (re.compile(r"bug##\.md"), "bug##.md"),
        (re.compile(r"bug\*\.md"), "bug*.md"),
        (re.compile(r"/u-bug-report\b"), "/u-bug-report"),
        (re.compile(r"u-bug-mode\.md"), "u-bug-mode.md"),
    ]

    @pytest.mark.parametrize("pattern,label", FORBIDDEN_PATTERNS, ids=[l for _, l in FORBIDDEN_PATTERNS])
    def test_guard46_no_non_allowlisted_dist_mentions(self, pattern, label):
        all_files = _walk_markdown(dist)
        violations = []
        for f in all_files:
            rel = str(f.relative_to(dist)).replace("\\", "/")
            if rel in self.MIGRATION_HISTORY_ALLOWLIST:
                continue
            content = f.read_text(encoding="utf-8")
            if pattern.search(content):
                violations.append(rel)
        assert violations == [], \
            f'Files still mention "{label}" (merged into /u-improve): {", ".join(violations)}'
