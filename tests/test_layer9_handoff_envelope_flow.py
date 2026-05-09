"""Layer 9 — Handoff Envelope Flow Invariants (ENV-070 to ENV-079)."""
import re
from conftest import get_dist_dir

DIST = get_dist_dir()


def _read(rel_path):
    return (DIST / rel_path).read_text(encoding="utf-8")


def _run_rules(rel_path, rules):
    content = _read(rel_path)
    for code, predicate, description in rules:
        assert predicate(content), f"{code} ({rel_path}): {description}"


def _contains(substr):
    return lambda content: substr in content


def _matches(pattern):
    return lambda content: bool(re.search(pattern, content))


class TestLayer9HandoffEnvelopeFlowInvariants:
    def test_improve_handoff_envelope_schema(self):
        _run_rules("skills/u-shared-templates/improve-handoff-envelope.schema.yaml", [
            ("ENV-071a", _contains("handoff_envelope"), "schema must declare handoff_envelope"),
            ("ENV-071b", _contains("mode_hint"), "schema must declare mode_hint"),
            ("ENV-071c", _contains("return_contract"), "schema must declare return_contract"),
            ("ENV-071d", _contains("expected_terminal_states"), "schema must declare expected_terminal_states"),
            ("ENV-072", _contains('$id: "u-shared-templates/improve-handoff-envelope.schema.yaml"'),
             "$id must match canonical path"),
            ("ENV-073", _matches(r'source:[\s\S]*const:\s*"u-improve"'),
             'source must be const "u-improve"'),
            ("ENV-074", _matches(r'update_field:[\s\S]*const:\s*"spec_change_status"'),
             'update_field must be const "spec_change_status"'),
            ("ENV-075a", _contains("fast-track:minor"), "mode_hint enum must include fast-track:minor"),
            ("ENV-075b", _contains("fast-track:patch"), "mode_hint enum must include fast-track:patch"),
            ("ENV-075c", _matches(r'"full"|\'full\''), 'mode_hint enum must include "full"'),
            ("ENV-076", _contains("execution_policy"), "schema must declare execution_policy block"),
            ("ENV-077a", _matches(r'pipeline:[\s\S]*enum:\s*\[lean, full\]'),
             "execution_policy.pipeline enum must be [lean, full]"),
            ("ENV-077b", _matches(r'regression_test_required:'),
             "execution_policy must declare regression_test_required"),
            ("ENV-078", _matches(r'invocation_source:[\s\S]{0,200}?enum:\s*\[u-improve,\s*spec-triage,\s*human\]'),
             "invocation_source enum must no longer include u-bug-report"),
        ])
