---
name: u-drift-analysis
description: Deterministic spec<->code drift analysis engine for /u-drift. Provides the stdlib scripts that build a spec inventory (spec_inventory.py), constrain the LLM-produced code inventory (validate_inventory.py), match the two by exact keys (match_drift.py), and render the report (render_report.py). Defines the matching keys, path normalization, severity/action tables, and the structural-vs-semantic scope boundary. Consumed by the /u-drift command and the u-drift-analyzer worker. Not user-invocable — callers run the scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# u-drift-analysis

Engine skill for spec↔code drift analysis. All decision logic lives in stdlib
scripts (P7/P11 — critical guarantees in testable code, not in prompts). The
determinism boundary is explicit: everything here is byte-for-byte reproducible
except the code-inventory extraction, which is produced by an LLM and clamped by
`validate_inventory.py` (schema shape + physically-resolvable evidence).

## scripts

| Script | Producer/Consumer | Contract |
|--------|-------------------|----------|
| `spec_inventory.py` | reads `{SPECS_DIR}` → writes `spec-inventory.json` (+ draft-skipped sidecar) | schema `u-shared-templates/spec-inventory.schema.yaml` |
| `validate_inventory.py` | reads `code-inventory.json` + `code_dir` → pass/fail | fails closed unless shape-valid AND every `file:line` evidence resolves |
| `match_drift.py` | reads both inventories (+ skipped sidecar) → writes `drift-report.json` | schema `u-shared-templates/drift-report.schema.yaml` |
| `validate_findings.py` | reads `drift-verdicts.json` + `code_dir` → pass/fail | Release B — fails closed unless verdicts are shape-valid AND evidence resolves |
| `merge_semantic.py` | folds validated `drift-verdicts.json` into `drift-report.json` | Release B — deterministic; relocates verdicts, re-numbers, recounts |
| `render_report.py` | reads `drift-report.json` → writes `drift-report.md` | presentation only; no decisions |
| `drift_common.py` | shared helpers (normalization, ordering, counting) | not a CLI |

Exit codes are documented in each script's module docstring. `spec_inventory.py`
returns 3 when no approved backend specs exist (caller maps to
`E_no_approved_specs`); `validate_inventory.py` returns 1 on any violation.

## Determinism boundary (plan R3)

| Stage | Producer | Reproducible? |
|-------|----------|---------------|
| spec inventory | `spec_inventory.py` | Yes — sorted domains/arrays/keys |
| code inventory | `u-reverse-spec-analyzer` (LLM) | No — clamped by `validate_inventory.py`; invalid → 1 directed re-dispatch → still invalid = `blocked` |
| matching | `match_drift.py` | Yes — byte-identical report from identical inventories |
| rendering | `render_report.py` | Yes |
| semantic verdict | `u-drift-analyzer` (Release B) | Clamped by `validate_findings.py`; escape hatch `undecidable`, never a guess |

## Matching model

Every artifact class reduces to **presence/absence of a canonical key**. Within-item
attribute drift (endpoint status codes, error HTTP status, state set, BR behavior)
is NOT decided structurally — it is deferred to the semantic layer (Release B),
because the code side is LLM-extracted and an attribute mismatch is as likely to be
an extraction gap as real drift.

| Artifact | Key | Granularity |
|----------|-----|-------------|
| endpoint | `{method} {normalized_path}` | endpoint |
| error_code | code string | code |
| entity | entity name (lowercased) | entity; field-level diff when both sides present |
| state_machine | entity name (lowercased) | entity |
| event | event name | event |
| business_rule | none (no code-derivable key) | **semantic only — Release B** |

Verdicts:
- spec-only key → `missing_in_code` — spec is the truth (SDD); `create_implementation_cr`
- code-only key → `missing_in_spec` — document the code; `update_spec`
- both present → `aligned` (structural)

## Path normalization (plan R6)

`normalize_path` is single-side (no knowledge of the other inventory):
1. drop query/fragment
2. every path parameter segment → literal `{param}` (`:id`, `{id}`, `<id>` all collapse; names ignored so spec `{id}` matches code `:userId`)
3. trailing slash removed; empty → `/`

`base_path` (router prefix) is stripped by the analyzer before emitting the code
inventory. If a matched domain has spec endpoints AND code endpoints but zero keys
intersect, `match_drift.py` emits ONE `base_path_mismatch_suspected` finding
(`undecidable`, blocking, `needs_human`) instead of flooding the report — and never
pairs unrelated endpoints heuristically.

## Severity table

| Status | endpoint | entity (item) | entity.field | state_machine | event | error_code |
|--------|----------|---------------|--------------|---------------|-------|------------|
| missing_in_code | blocking | major | minor | major | major | minor |
| missing_in_spec | major | major | minor | minor | minor | minor |

## Action table (direction of truth, plan R5)

| Status | default_action | Handoff |
|--------|----------------|---------|
| missing_in_code | `create_implementation_cr` | `/u-dev` candidate |
| missing_in_spec (matched domain) | `update_spec` | `/u-improve` payload |
| undecidable / base_path | `needs_human` | human triage (fix_spec + fix_code) |

A code module with no matching spec domain and a spec domain with no matching code
module are surfaced as `skipped` entries (`no_spec_domain` / `no_code_module`) with a
suggested action — not per-artifact findings — to avoid flooding. `create_spec` and
`drifted` remain in the schema for the semantic layer (Release B).

## Scope

- **Backend only** (openapi.yaml + `*.back.md`). Frontend feature-spec drift is out of scope for this release.
- **Approved specs only.** `Status: draft`/`review` domains go to `skipped` with reason `draft_status`.
- **Release A** populates `missing_in_code` / `missing_in_spec` / `aligned` for the five keyable classes. **Release B** adds `business_rule` matching, refines a subset of aligned endpoints to `drifted`, and introduces confirmed `undecidable` verdicts via `u-drift-analyzer`.

## Dependencies

- `.claude/lib/minimal_yaml.py` — OpenAPI parsing (stdlib loader)
- `u-shared-templates` — the three schema/example pairs (`spec-inventory`, `code-inventory`, `drift-report`)
- `u-reverse-spec-analyzer` (code-inventory mode) — produces `code-inventory.json`
