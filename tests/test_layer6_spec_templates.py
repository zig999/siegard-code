"""Layer 6 — Spec Templates: validates required sections and content in template files."""
import re
import pytest
from conftest import get_dist_dir

DIST_DIR = get_dist_dir()

FEATURE_TEMPLATE = DIST_DIR / "skills" / "u-spec-templates" / "TEMPLATE.feature.spec.md"
COMPONENT_TEMPLATE = DIST_DIR / "skills" / "u-spec-templates" / "TEMPLATE.component.spec.md"
FLOW_TEMPLATE = DIST_DIR / "skills" / "u-spec-templates" / "TEMPLATE.flow.md"
TOKENS_TEMPLATE = DIST_DIR / "skills" / "u-spec-templates" / "TEMPLATE.design-system" / "tokens.md"

_template_files = [
    ("TEMPLATE.feature.spec.md", FEATURE_TEMPLATE),
    ("TEMPLATE.component.spec.md", COMPONENT_TEMPLATE),
    ("TEMPLATE.flow.md", FLOW_TEMPLATE),
    ("TEMPLATE.design-system/tokens.md", TOKENS_TEMPLATE),
]


def _has_section(content, heading):
    return f"## {heading}" in content


def _has_section_number(content, n, name):
    return bool(re.search(rf"## {n}\.\s+{name}", content))


def _has_flow_id(content):
    return bool(re.search(r"Flow ID:\s*FLOW-\w+", content)) or "Flow ID: FLOW-NN" in content


class TestLayer6SpecTemplates:
    def test_feature_template_sections_and_content(self):
        content = FEATURE_TEMPLATE.read_text(encoding="utf-8")
        required = [
            (1, "Consumed Endpoints"),
            (2, "Feature States"),
            (3, "State Transition Table"),
            (4, "Requests, Order and Cache"),
            (5, "Input Validations"),
            (6, "API Error"),
            (7, "Shared Components Used"),
            (8, "Feature Accessibility"),
            (9, "BDD Scenarios"),
            (10, "Components to Create"),
            (11, "Out of Scope"),
        ]
        for n, name in required:
            assert _has_section_number(content, n, name), \
                f'Section "## {n}. {name}" not found in TEMPLATE.feature.spec.md'
        assert _has_section(content, "Changelog"), "Changelog section missing"

    def test_component_template_sections_and_content(self):
        content = COMPONENT_TEMPLATE.read_text(encoding="utf-8")
        required = [
            (1, "Purpose and Responsibilities"),
            (2, "When to Use"),
            (3, "Props Contract"),
            (4, "Component States"),
            (5, "Events Emitted"),
            (6, "Variants and Compositions"),
            (7, "Do / Don"),
            (8, "BDD Scenarios"),
            (9, "Accessibility Contract"),
            (10, "Internal Dependencies"),
        ]
        for n, name in required:
            assert _has_section_number(content, n, name), \
                f'Section "## {n}. {name}" not found in TEMPLATE.component.spec.md'
        assert _has_section(content, "Changelog"), "Changelog section missing"

    def test_flow_template_required_structure(self):
        content = FLOW_TEMPLATE.read_text(encoding="utf-8")
        assert _has_flow_id(content), "FLOW-NN identifier missing from header"
        assert "Involved Features" in content, "Involved Features section missing"
        assert "Happy Path" in content, "Happy Path section missing"
        assert "Alternative Flows" in content, "Alternative Flows section missing"
        assert "Navigation Rules" in content, "Navigation Rules section missing"
        assert "Deep Links" in content, "Deep Links section missing"
        assert "**Fallback:**" in content, "Navigation rules require explicit Fallback field"
        assert _has_section(content, "Changelog"), "Changelog section missing"

    def test_tokens_template_sections_and_content(self):
        content = TOKENS_TEMPLATE.read_text(encoding="utf-8")
        sections = [
            "Token Declarations",
            "3. Color Tokens",
            "4. Spacing Tokens",
            "5. Typographic Scale",
            "6. Shadows and Borders",
            "7. Animation and Motion Tokens",
            "8. Semantic Usage Rules",
        ]
        for heading in sections:
            assert f"## {heading}" in content, f'"## {heading}" not found in tokens.md'
        section7idx = content.find("## 7.")
        section8idx = content.find("## 8.")
        assert section7idx > 0, "Section 7 not found"
        assert section8idx > 0, "Section 8 not found"
        assert section7idx < section8idx, "Section 7 must appear before section 8"
