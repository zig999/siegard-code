"""Layer hard — W07: SDD checkers that scan the spec tree must be scope-aware.

Meta-invariant born from the F1/F3 → L1/L3 audit cycle: the improve-scoping
bug was fixed in the dispatch loop (v2.4.0), then re-found in
check_error_codes_synced and identify_invalid_domains (v2.7.0) — the same
class leaking through checkers added or missed later. This gate prohibits
the CLASS: any phase-sdd-rules script that globs the spec tree must consume
scope.py (import + a --workflow-id CLI knob), or carry a justified
allowlist entry here.

Static, fast, zero-execution — same pattern as the W01-W06 worker gate.
"""
import re
from pathlib import Path

import pytest

SDD_SCRIPTS = (
    Path(__file__).parent.parent
    / "dist" / ".claude" / "skills" / "phase-sdd-rules" / "scripts"
)

# Scripts allowed to scan the spec tree WITHOUT scope awareness.
# Every entry needs a reason — an empty reason is a test failure.
# Empty today: every spec-tree scanner is scope-aware (v2.7.0). Adding an
# entry here is a conscious, justified decision.
GLOBAL_SCAN_ALLOWLIST: dict[str, str] = {
    "check_spec_drift_reviewed.py": (
        "R04d drift criterion. Its glob computes a content hash over the WHOLE "
        "approved spec surface, because that hash is what /u-drift pins in its "
        "report and what makes the report detectably stale. Scoping the hash to "
        "the touched domains would make it change whenever the scope changed, so "
        "an unrelated /u-improve would invalidate a perfectly current report — "
        "the opposite of what F1 protects. It gates nothing per-domain and "
        "repairs nothing: it answers 'is this report still about these specs?'."
    ),
    "check_spec_entry.py": (
        "R10 entry guard. Its whole question is 'does this repository already hold "
        "ANY domain spec?', so a scoped scan would answer the wrong question — and "
        "it runs in /u-spec Initial Validation, before triage.json exists, so no "
        "scope is derivable yet. It gates nothing per-domain and repairs nothing: "
        "it only classifies the entry point as greenfield or not."
    ),
}

_GLOB_RE = re.compile(r"\.r?glob\(")
_SCOPE_IMPORT_RE = re.compile(r"^from scope import |^import scope\b", re.MULTILINE)
_WORKFLOW_ID_RE = re.compile(r"--workflow-id")


def _spec_scanners():
    return [
        p for p in sorted(SDD_SCRIPTS.glob("*.py"))
        if _GLOB_RE.search(p.read_text(encoding="utf-8"))
    ]


class TestW07ScopeCompliance:
    def test_gate_sees_the_known_scanners(self):
        """Sanity: the detector must find the checkers this gate exists for."""
        names = {p.name for p in _spec_scanners()}
        assert {"check_all_domains_validated.py",
                "check_error_codes_synced.py",
                "identify_invalid_domains.py"} <= names

    @pytest.mark.parametrize("script", _spec_scanners(), ids=lambda p: p.name)
    def test_spec_scanner_is_scope_aware_or_allowlisted(self, script):
        if script.name in GLOBAL_SCAN_ALLOWLIST:
            assert GLOBAL_SCAN_ALLOWLIST[script.name].strip(), (
                f"{script.name}: allowlist entry must carry a reason"
            )
            return
        content = script.read_text(encoding="utf-8")
        assert _SCOPE_IMPORT_RE.search(content), (
            f"{script.name}: globs the spec tree but does not import scope.py "
            f"(W07). An /u-improve must never be gated or repaired against "
            f"domains it did not touch. Import scope.affected_domains or add "
            f"a justified GLOBAL_SCAN_ALLOWLIST entry."
        )
        assert _WORKFLOW_ID_RE.search(content), (
            f"{script.name}: imports scope.py but exposes no --workflow-id "
            f"CLI option — callers cannot pass the scope (W07)."
        )

    def test_allowlist_has_no_stale_entries(self):
        scanner_names = {p.name for p in _spec_scanners()}
        stale = [n for n in GLOBAL_SCAN_ALLOWLIST if n not in scanner_names]
        assert stale == [], (
            f"GLOBAL_SCAN_ALLOWLIST entries that no longer glob the spec "
            f"tree: {stale} — remove them."
        )
