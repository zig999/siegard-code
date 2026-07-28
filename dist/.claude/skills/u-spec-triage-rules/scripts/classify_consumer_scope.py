#!/usr/bin/env python3
"""
classify_consumer_scope.py — Does this change reach a consumer outside itself?

`mode_hint` had one axis: **compatibility**. Anything that modifies an existing
contract is `full`, whatever it touches. So a rename of two keys in an injection
map private to one module — every call site in the same repo, all updated in the
same commit — paid the same toll as breaking a published DTO.

Measured: that change ran the full pipeline at 10 workers / 336k tokens / 56 min.
With the blast radius accounted for it is 5 workers. Meanwhile the *larger* change
in the same series (the engine's plan/collect core) ran fast-track. The axis was
inverted in practice.

Root cause, narrower than "the axis is missing". The label vocabulary had no term
for a code-level interface, so `api_contracts` was assigned to changes that touch
no API at all:

    domains/mwo-catalog/back/mwo-catalog.back.md  ["schemas", "api_contracts"]
    domains/fsm/back/fsm.back.md                  ["api_contracts"]

for (1) named TS interfaces on DI surfaces, (2) a rename of private injection map
keys, (3) three barrel exports. `internal_interfaces` and `module_exports` now
exist precisely so that reach is recorded rather than inflated, and this script
derives the scope from those labels deterministically.

**Conservative by construction.** `internal` requires that EVERY changed section
across EVERY affected spec is internal-only AND no published contract file is
touched. Anything unrecognised, anything ambiguous, an empty section list, an
`openapi.yaml` in scope — all resolve to `public`. A wrong `public` costs
pipeline time; a wrong `internal` skips the cross-domain validator on a published
contract. The two errors are not symmetric, so the default is not symmetric.

Usage:
    # Production path — triage passes the array it holds in memory (Step 2.5b).
    python3 classify_consumer_scope.py --affected-specs '<json array>'

    # Inspection path — for a triage.json that ALREADY exists. Do not use this
    # from the triage skill itself: triage.json is written in Step 3, after this
    # classification runs, so on a new workflow the file is absent (exit 1) and on
    # a resumed workflow it still holds the previous run's affected_specs.
    python3 classify_consumer_scope.py --triage <path/to/triage.json>

Output (stdout, JSON, exit 0):
    {
      "consumer_scope": "public" | "internal",
      "rationale": "<why>",
      "public_signals": ["<spec>: <section>", ...],
      "internal_signals": ["<spec>: <section>", ...],
      "unrecognized_sections": ["<section>", ...]
    }

Exit codes:
    0  classified
    1  usage/IO error
"""
import argparse
import json
import sys
from pathlib import Path

# Sections whose change is visible to a consumer this change does not update:
# an HTTP client, another service, a stored payload, a downstream package.
PUBLIC_SECTIONS: frozenset[str] = frozenset({
    "endpoints",         # HTTP routes / RPC methods
    "api_contracts",     # published API compatibility
    "error_codes",       # clients branch on these
    "event_types",       # other services consume these
    "auth_rules",        # security surface
    "schemas",           # published data schemas (openapi components)
    "data_models",       # persisted entities — stored data outlives the change
    "state_contracts",   # state machines other components depend on
    "component_props",   # a component's contract with its callers
})

# Sections whose change is confined to this repository and updated with it.
INTERNAL_SECTIONS: frozenset[str] = frozenset({
    "internal_interfaces",  # code-level interfaces, DI surfaces, private types
    "module_exports",       # barrel/module export lists
    # Text-only labels carry no reach by definition.
    "descriptions", "labels", "examples", "notes", "changelog", "formatting",
})

# Files that ARE the published contract — their presence forces `public`
# regardless of how the sections were labelled.
_PUBLISHED_CONTRACT_FILES = ("openapi.yaml", "openapi.yml", "asyncapi.yaml")


def _affected_from_triage(triage: dict) -> list[dict]:
    return triage.get("affected_specs") or []


def classify(affected_specs: list[dict]) -> dict:
    # No affected specs is not evidence of a small blast radius — it is absence
    # of evidence. Stay public.
    if not affected_specs:
        return {
            "consumer_scope": "public",
            "rationale": "no affected_specs to inspect — reach is undetermined, "
                         "so the conservative scope applies",
            "public_signals": [],
            "internal_signals": [],
            "unrecognized_sections": [],
        }

    public_signals: list[str] = []
    internal_signals: list[str] = []
    unrecognized: list[str] = []

    for entry in affected_specs:
        path = str(entry.get("path", "<unknown>"))
        sections = entry.get("changed_sections") or []

        if any(path.endswith(f) or f"/{f}" in path for f in _PUBLISHED_CONTRACT_FILES):
            public_signals.append(f"{path}: published contract file")

        if not sections:
            # A spec in scope with no labelled sections tells us nothing about
            # reach; treat it as public rather than assuming it is small.
            public_signals.append(f"{path}: no changed_sections declared")
            continue

        for section in sections:
            label = str(section)
            if label in PUBLIC_SECTIONS:
                public_signals.append(f"{path}: {label}")
            elif label in INTERNAL_SECTIONS:
                internal_signals.append(f"{path}: {label}")
            else:
                unrecognized.append(label)
                public_signals.append(f"{path}: {label} (unrecognized)")

    if public_signals:
        scope = "public"
        rationale = (
            f"{len(public_signals)} section(s) reach a consumer this change does "
            "not update — the full pipeline applies"
        )
    else:
        scope = "internal"
        rationale = (
            "every changed section is code-internal and updated within this "
            "change; no published contract file is in scope"
        )

    return {
        "consumer_scope": scope,
        "rationale": rationale,
        "public_signals": public_signals,
        "internal_signals": internal_signals,
        "unrecognized_sections": sorted(set(unrecognized)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--affected-specs",
                       help="affected_specs as a JSON array — the production path; "
                            "pass the array the caller holds in memory")
    group.add_argument("--triage",
                       help="path to an EXISTING triage.json (inspection only — see "
                            "the module docstring for why triage must not use this)")
    args = ap.parse_args()

    if args.triage:
        path = Path(args.triage)
        if not path.is_file():
            print(json.dumps({
                "status": "error", "reason": "triage_not_found", "detail": str(path),
            }), file=sys.stderr)
            sys.exit(1)
        try:
            affected = _affected_from_triage(
                json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({
                "status": "error", "reason": "triage_unreadable", "detail": str(exc),
            }), file=sys.stderr)
            sys.exit(1)
    else:
        try:
            affected = json.loads(args.affected_specs)
        except json.JSONDecodeError as exc:
            print(json.dumps({
                "status": "error", "reason": "invalid_json", "detail": str(exc),
            }), file=sys.stderr)
            sys.exit(1)
        if not isinstance(affected, list):
            print(json.dumps({
                "status": "error", "reason": "invalid_json",
                "detail": "--affected-specs must be a JSON array",
            }), file=sys.stderr)
            sys.exit(1)

    print(json.dumps(classify(affected)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
