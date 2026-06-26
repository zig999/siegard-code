"""Layer Hard Manifest Fail-Closed — parse_manifest_fields no longer defaults stack (task 05).

A3-F7: parse_manifest_fields silently coerced an unknown/absent stack to "be",
so an FE-only or unparseable manifest mis-routed QA/impl tasks to BE workers.
Now: explicit stack is honored; otherwise stack is inferred from package presence;
if nothing resolves, stack is None and the caller must fail-closed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dist" / ".claude" / "lib"))


class TestParseManifestFailClosed:
    def test_no_stack_no_packages_returns_none(self):
        from orch_core import parse_manifest_fields
        assert parse_manifest_fields("handoff:\n  type: new_domain\n")["stack"] is None

    def test_explicit_stack_preserved(self):
        from orch_core import parse_manifest_fields
        assert parse_manifest_fields("stack: be\n")["stack"] == "be"
        assert parse_manifest_fields("stack: fe\n")["stack"] == "fe"
        assert parse_manifest_fields("stack: fullstack\n")["stack"] == "fullstack"

    def test_frontend_package_infers_fe(self):
        from orch_core import parse_manifest_fields
        r = parse_manifest_fields("frontend_package:\n  - artifact: front-spec\n    path: x\n")
        assert r["stack"] == "fe"

    def test_backend_package_infers_be(self):
        from orch_core import parse_manifest_fields
        r = parse_manifest_fields("backend_package:\n  - artifact: openapi\n    path: x\n")
        assert r["stack"] == "be"

    def test_both_packages_infers_fullstack(self):
        from orch_core import parse_manifest_fields
        r = parse_manifest_fields("backend_package:\n  - path: a\nfrontend_package:\n  - path: b\n")
        assert r["stack"] == "fullstack"

    def test_unknown_stack_value_not_coerced_to_be(self):
        from orch_core import parse_manifest_fields
        # garbage stack with no package signal -> None, NOT silently "be" (the A3-F7 bug)
        assert parse_manifest_fields("stack: mobile\n")["stack"] is None

    def test_type_still_defaults_new_domain(self):
        from orch_core import parse_manifest_fields
        # type default is the SAFEST branch (no D6 vacuous-exit / HDF-030 halt) — kept.
        assert parse_manifest_fields("stack: be\n")["type"] == "new_domain"
