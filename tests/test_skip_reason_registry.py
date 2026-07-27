"""R03 — `task_skipped` audit-trail integrity.

Two defects of the same kind, both in the one place the architecture declares
unbreakable (P1: the log is the truth; P3: corrections happen via new events).

1. `ui_task_false_back_only` was emitted by orchestrator-sdd and absent from
   `_VALID_SKIP_REASONS`, so `append_event` raised and the front-leg skip on a
   back-only workflow went unrecorded. A skip that cannot be written is a hole
   in the audit trail, not a no-op.

2. The targeted-mode event declared `skipped_steps: [... "spec-back" ...]` while
   the same phase dispatched three `spec-back` tasks. The event misdescribed what
   the log itself recorded two events later.

Both were literals that nothing cross-checked. This module is the cross-check.
"""
import re
import sys

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
sys.path.insert(0, str(dist / "lib"))

import orch_core  # noqa: E402

ORCHESTRATORS = sorted((dist / "agents").glob("orchestrator*.md"))

# `--event-type task_skipped` ... `--data '{...}'`, tolerating the intervening
# --task-id line. Non-greedy so consecutive appends do not merge.
_SKIP_APPEND_RE = re.compile(
    r"--event-type\s+task_skipped\b(?P<body>.*?)--data\s+'(?P<data>\{.*?\})'",
    re.DOTALL,
)
_REASON_RE = re.compile(r'"reason"\s*:\s*"([a-z_]+)"')


def _skip_appends(text: str):
    for m in _SKIP_APPEND_RE.finditer(text):
        payload = m.group("data")
        reason = _REASON_RE.search(payload)
        yield (reason.group(1) if reason else None), payload


def _all_appends():
    for path in ORCHESTRATORS:
        for reason, payload in _skip_appends(path.read_text(encoding="utf-8")):
            yield path.name, reason, payload


class TestReasonRegistry:
    def test_appends_are_discovered(self):
        found = list(_all_appends())
        assert found, "no task_skipped append blocks found — the regex has rotted"

    def test_every_emitted_reason_is_valid(self):
        """The bug: a reason in the prose that the validator rejects at runtime."""
        offenders = [
            (f, r) for f, r, _ in _all_appends()
            if r is not None and r not in orch_core._VALID_SKIP_REASONS
        ]
        assert not offenders, (
            "task_skipped reasons emitted by orchestrators but rejected by "
            f"_VALID_SKIP_REASONS (append_event would raise): {offenders}"
        )

    def test_every_append_carries_a_reason(self):
        missing = [f for f, r, _ in _all_appends() if r is None]
        assert not missing, f"task_skipped append with no reason field in: {missing}"

    def test_the_two_regression_reasons_are_registered(self):
        for reason in ("ui_task_false_back_only",
                       "unaffected_domain_out_of_change_scope"):
            assert reason in orch_core._VALID_SKIP_REASONS

    def test_registry_has_no_unreachable_entries(self):
        """A reason no orchestrator emits is either dead or an undocumented path.

        `phase_short_circuit` is emitted programmatically rather than from
        orchestrator prose, so it is the one allowed exception.
        """
        emitted = {r for _, r, _ in _all_appends() if r}
        unreachable = orch_core._VALID_SKIP_REASONS - emitted - {"phase_short_circuit"}
        assert not unreachable, (
            f"reasons in the registry that no orchestrator emits: {sorted(unreachable)}"
        )

    def test_reasons_validate_through_the_real_validator(self):
        """Assert against the code path that actually runs, not against the set."""
        for fname, reason, _ in _all_appends():
            orch_core._validate_event_data(
                "task_skipped", {"phase": "sdd", "reason": reason}
            )  # must not raise


class TestTargetedSkipPayloadIsHonest:
    """The targeted event must not claim to skip a step it dispatches."""

    @property
    def _sdd(self):
        return (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")

    def test_literal_skipped_steps_field_is_gone(self):
        assert "skipped_steps" not in self._sdd, (
            "the field was renamed to superseded_standard_steps — a literal list "
            "of 'skipped' steps is what produced the false audit entry"
        )

    def test_targeted_payload_declares_what_ran_instead(self):
        text = self._sdd
        idx = text.index("targeted_mode_step_not_in_scope")
        window = text[idx - 1800:idx + 1200]
        assert "steps_dispatched_instead" in window
        assert "superseded_standard_steps" in window

    def test_targeted_payload_is_derived_not_copied(self):
        text = self._sdd
        idx = text.index("targeted_mode_step_not_in_scope")
        window = text[max(0, idx - 1800):idx + 400]
        assert "derived" in window.lower(), (
            "the instruction must tell the orchestrator to derive the list from the "
            "tasks it created; a hardcoded list is the defect"
        )

    def test_no_orchestrator_hardcodes_spec_back_as_skipped(self):
        """The exact false claim: spec-back listed as skipped in targeted mode."""
        for path in ORCHESTRATORS:
            for reason, payload in _skip_appends(path.read_text(encoding="utf-8")):
                if reason != "targeted_mode_step_not_in_scope":
                    continue
                assert '"spec-back"' not in payload, (
                    f"{path.name}: targeted mode dispatches spec-back — it cannot "
                    "be listed as superseded in a literal"
                )
