"""F-04 — readable workflow_id resolution.

The engine used to mint an opaque uuid4 unconditionally, discarding the readable
id passed to /u-spec; sessions keyed by UUID could not be located or resumed by
name. resolve_workflow_id honors a usable requested id and otherwise falls back
to a readable slug — never a UUID.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dist" / ".claude" / "lib"))

import orch_core  # noqa: E402


class TestSlugify:
    def test_plain_name_is_kept(self):
        assert orch_core.slugify_workflow_id("chat-ui") == "chat-ui"

    def test_dotted_ok_underscore_mapped_to_hyphen(self):
        # 5-a: '_' is the namespace delimiter inside task IDs (dev_{wf}_tc_{n});
        # a workflow id containing '_' would make the namespace non-injective
        # ('pay_v2'+'auth' vs 'pay'+'v2_auth'), so slugify maps '_' -> '-'.
        assert orch_core.slugify_workflow_id("spec_2026.06") == "spec-2026.06"
        assert orch_core.slugify_workflow_id("pay_v2") == "pay-v2"

    def test_path_separator_rejected(self):
        assert orch_core.slugify_workflow_id("a/b") is None
        assert orch_core.slugify_workflow_id("a\\b") is None

    def test_empty_and_none_rejected(self):
        assert orch_core.slugify_workflow_id("") is None
        assert orch_core.slugify_workflow_id("   ") is None
        assert orch_core.slugify_workflow_id(None) is None

    def test_dot_segments_rejected(self):
        assert orch_core.slugify_workflow_id(".") is None
        assert orch_core.slugify_workflow_id("..") is None

    def test_whitespace_is_stripped(self):
        assert orch_core.slugify_workflow_id("  chat-ui  ") == "chat-ui"

    def test_lowercased_for_windows_case_insensitive_fs(self):
        # Targets run on a case-insensitive FS; 'Chat-UI' and 'chat-ui' must not
        # become two log ids resolving to the same session dir (P1 violation).
        assert orch_core.slugify_workflow_id("Chat-UI") == "chat-ui"
        assert orch_core.slugify_workflow_id("CHAT_UI") == "chat-ui"  # '_' -> '-' (5-a)


class TestResolveWorkflowId:
    def test_readable_request_is_honored(self):
        wf, diverged = orch_core.resolve_workflow_id("chat-ui", "20260620")
        assert wf == "chat-ui"
        assert diverged is False

    def test_absent_request_falls_back_to_readable_slug(self):
        wf, diverged = orch_core.resolve_workflow_id("", "20260620")
        assert wf == "spec-20260620"
        # nothing was requested → not a divergence
        assert diverged is False

    def test_fallback_is_never_a_uuid(self):
        wf, _ = orch_core.resolve_workflow_id(None, "20260620")
        assert wf.startswith("spec-")
        assert "-" in wf and len(wf) < 40  # readable, not a 36-char uuid4

    def test_collision_disambiguated(self):
        wf, _ = orch_core.resolve_workflow_id(
            None, "20260620", existing=["spec-20260620"])
        assert wf == "spec-20260620-2"
        wf2, _ = orch_core.resolve_workflow_id(
            None, "20260620", existing=["spec-20260620", "spec-20260620-2"])
        assert wf2 == "spec-20260620-3"

    def test_invalid_request_diverges_and_is_logged(self):
        # A requested id with a path separator cannot be used → divergence flagged
        wf, diverged = orch_core.resolve_workflow_id("bad/name", "20260620")
        assert wf == "spec-20260620"
        assert diverged is True
