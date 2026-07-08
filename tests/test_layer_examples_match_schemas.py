"""Layer — Shipped templates structurally match their schemas.

The canonical template/example files in u-shared-templates are what workers
copy when emitting envelopes. Before this gate nothing validated them — a
template could silently drift from its schema (renamed field, missing
required key, stale extra key) and teach every worker the wrong contract.

The templates carry PLACEHOLDERS by design (`TC-XX`, `<YYYY-MM-DDTHH:MM:SSZ>`,
`valid | invalid`), so value-level constraints (pattern/enum/format/type of
primitives) cannot apply to them — those are enforced on real instances at
runtime (u-handoff-validator) and on concrete fixtures (layer 2). This gate
validates STRUCTURE: required properties present, no unknown properties
where additionalProperties is false, object/array shape correct — the exact
drift class a copy-pasting worker propagates.
"""
import pytest
from conftest import get_all_schema_files, get_dist_dir, load_yaml

import jsonschema

TEMPLATES_DIR = get_dist_dir() / "skills" / "u-shared-templates"

# Schemas whose template file does not follow the `<stem>.yaml` convention.
TEMPLATE_NAME_OVERRIDES = {
    "cr.schema.yaml": "cr-template.yaml",
}

# Schemas that deliberately ship without a YAML template. Adding a schema
# here is a conscious decision — the inventory test fails on any NEW
# template-less schema, forcing either a template or a justified entry.
NO_TEMPLATE_ALLOWED = {
    "backlog.schema.yaml": "backlog is produced per-project by planners; canonical shape lives in u-planning templates",
    "delivery.schema.yaml": "delivery is a markdown artifact (delivery-gate.md); schema validates its YAML gate block",
    "qa-verdict.schema.yaml": "verdict blocks are embedded in qa-report.md; parser contract tested in test_verdict_parser.py",
}

# Value-level keywords stripped for structural validation (placeholders are
# strings and would fail them by design).
_VALUE_KEYWORDS = frozenset({
    "pattern", "enum", "format", "const", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
    "multipleOf", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties",
})
_PRIMITIVE_TYPES = frozenset({"string", "number", "integer", "boolean", "null"})


def _structural(node, is_schema=True):
    """Recursively strip value-level constraints; keep structural ones.

    Primitive `type` is dropped (a `<int>` placeholder is a string); object
    and array types are kept so shape drift still fails. `is_schema=False`
    marks a properties-map level, where keys are PROPERTY NAMES (a field
    legitimately named `type` or `pattern`) and must not be treated as
    JSON-Schema keywords.
    """
    if isinstance(node, list):
        return [_structural(v, is_schema) for v in node]
    if not isinstance(node, dict):
        return node
    if not is_schema:
        # properties map: each value is a schema, each key is a field name.
        return {k: _structural(v, True) for k, v in node.items()}
    out = {}
    for key, value in node.items():
        if key in _VALUE_KEYWORDS:
            continue
        if key == "type" and isinstance(value, (str, list)):
            types = value if isinstance(value, list) else [value]
            if all(isinstance(t, str) for t in types) \
                    and all(t in _PRIMITIVE_TYPES for t in types):
                continue  # placeholder-tolerant: any primitive accepted
        if key in ("properties", "patternProperties"):
            out[key] = _structural(value, is_schema=False)
        elif key == "oneOf":
            # Relaxed branches lose their distinguishing value constraints and
            # may all match a placeholder — exclusivity is value-level, so
            # structural validation demands only "matches at least one".
            out["anyOf"] = _structural(value, is_schema=True)
        else:
            out[key] = _structural(value, is_schema=True)
    return out


def _template_for(schema_file):
    name = TEMPLATE_NAME_OVERRIDES.get(
        schema_file.name, schema_file.name.replace(".schema.yaml", ".yaml")
    )
    path = TEMPLATES_DIR / name
    return path if path.exists() else None


_PAIRS = [(f, _template_for(f)) for f in get_all_schema_files()]


class TestTemplateInventory:
    def test_every_schema_has_template_or_registered_exemption(self):
        missing = [
            f.name for f, tpl in _PAIRS
            if tpl is None and f.name not in NO_TEMPLATE_ALLOWED
        ]
        assert missing == [], (
            f"Schemas without a shipped template and without a registered "
            f"exemption: {missing}. Ship a template or add a justified entry "
            f"to NO_TEMPLATE_ALLOWED."
        )

    def test_exemption_list_has_no_stale_entries(self):
        stale = [
            name for name in NO_TEMPLATE_ALLOWED
            if _template_for(TEMPLATES_DIR / name) is not None
        ]
        assert stale == [], (
            f"NO_TEMPLATE_ALLOWED entries whose template now exists: {stale} "
            f"— remove the exemption so the template is validated."
        )


class TestStructuralTransformStillBites:
    """The relaxed validator must still catch the drift class it exists for."""

    _SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "meta"],
        "properties": {
            "id": {"type": "string", "pattern": "^TC-[0-9]+$"},
            "meta": {
                "type": "object",
                "required": ["kind"],
                "properties": {"kind": {"enum": ["a", "b"]}},
            },
        },
    }

    def _errors(self, data):
        import jsonschema as js
        return list(js.Draft7Validator(_structural(self._SCHEMA)).iter_errors(data))

    def test_placeholder_values_pass(self):
        assert self._errors({"id": "TC-XX", "meta": {"kind": "a | b"}}) == []

    def test_missing_required_key_fails(self):
        assert self._errors({"id": "TC-XX"}) != []

    def test_unknown_key_fails(self):
        assert self._errors(
            {"id": "TC-XX", "meta": {"kind": "a"}, "renamed_field": 1}
        ) != []

    def test_wrong_shape_fails(self):
        # object required, placeholder string given → structural, must fail
        assert self._errors({"id": "TC-XX", "meta": "<object>"}) != []


class TestTemplatesStructurallyValidate:
    @pytest.mark.parametrize(
        "schema_file,template_file",
        [(f, tpl) for f, tpl in _PAIRS if tpl is not None],
        ids=lambda p: p.name,
    )
    def test_template_matches_schema_structure(self, schema_file, template_file):
        schema = _structural(load_yaml(schema_file))
        data = load_yaml(template_file)
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))
        assert errors == [], (
            f"{template_file.name} structurally drifted from "
            f"{schema_file.name}: "
            + "; ".join(e.message[:120] for e in errors[:5])
        )
