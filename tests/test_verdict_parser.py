"""SIEGARD BUG-2 — the review-phase verdict gates share ONE parser.

`read_qa_verdict.extract_verdict` is the single source of truth imported by
check_all_qa_verdicts_approved.py and check_micro_unanimous_clean.py. These tests
guard that it (a) tolerates the Markdown the QA templates emit, (b) normalises case,
and (c) collapses any ambiguous value to 'unknown' so a gate never silently
auto-approves it. The historical drift — this helper captured `(.+)$` while check_all
captured `(\\S+)`, and neither lower-cased the value — is what made a human-approved
review stall on E08.
"""
import sys
from pathlib import Path

_SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / "dist" / ".claude" / "skills" / "phase-review-rules" / "scripts"
)
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from read_qa_verdict import extract_verdict  # noqa: E402


def _wrap(line: str) -> str:
    return f"# QA Report\n\n{line}\n"


def test_bare_lowercase():
    assert extract_verdict(_wrap("verdict: approved")) == "approved"
    assert extract_verdict(_wrap("verdict: rejected")) == "rejected"


def test_capitalized_value_is_normalized():
    # The old read_qa_verdict did NOT lower-case the value, so bare `verdict: Approved`
    # — the exact value the old template taught — read as 'unknown'.
    assert extract_verdict(_wrap("verdict: Approved")) == "approved"
    assert extract_verdict(_wrap("verdict: REJECTED")) == "rejected"


def test_bold_markdown_field_and_value():
    assert extract_verdict(_wrap("**Verdict:** Approved")) == "approved"
    assert extract_verdict(_wrap('- **verdict**: "approved"')) == "approved"


def test_ambiguous_values_are_unknown():
    # Ambiguous / out-of-enum verdicts must never auto-pass a gate.
    assert extract_verdict(_wrap("verdict: Approved with caveats")) == "unknown"
    assert extract_verdict(_wrap("verdict: approved_with_reservations")) == "unknown"


def test_comment_line_does_not_match():
    assert extract_verdict(_wrap("# verdict: approved (example)")) == "unknown"


def test_missing_field_is_unknown():
    assert extract_verdict("# QA Report\n\nsummary: ok\n") == "unknown"


def test_frontmatter_is_first_match():
    # First match in document order is the frontmatter — the source of truth — even
    # when a (stale) human bold label disagrees below it.
    content = "---\nverdict: rejected\n---\n\n# QA\n\n**Verdict:** Approved\n"
    assert extract_verdict(content) == "rejected"
