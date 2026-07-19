# `/u-drift` — Spec ↔ Code Drift Analysis

Audit the divergence between your **approved specifications** and your **implemented
code**. `/u-drift` builds a deterministic, evidence-backed report of what the spec
declares but the code does not implement, what the code exposes but the spec does not
document, and where the two have drifted apart — and maps every finding to a concrete
follow-up action.

It exists to catch the drift that the normal pipeline cannot: changes made outside
`/u-spec` → `/u-dev` (a manual hotfix, a direct spec edit, a legacy base that evolved).

---

## What you run vs. what runs for you

Only **one** artifact is user-facing. The rest is machinery the command orchestrates —
all of it is `user-invocable: false` and must not be invoked directly.

| Artifact | Kind | You use it? |
|---|---|---|
| `/u-drift [CODE_DIR]` | command | **Yes — the only entry point** |
| `u-drift-analyzer` | agent | No — invoked by `/u-drift` for the semantic pass |
| `u-reverse-spec-analyzer` (code-inventory mode) | agent | No — invoked by `/u-drift` to extract the code inventory |
| `u-drift-analysis` | skill (scripts) | No — the command/agents run its scripts |
| `spec-inventory` / `code-inventory` / `drift-report` / `drift-verdicts` | schemas | Reference contracts — validated, not executed |

---

## Prerequisites

1. **Approved backend specs.** Only domains with `Status: approved` are audited. Drafts
   are reported as skipped, never as drift.
2. **The source code** for those domains.
3. `SPECS_DIR` is resolved from the `specs_dir:` field in the target project's
   `CLAUDE.md`, or defaults to `{CODE_DIR}/specs`.

---

## Running it

```
/u-drift ./src
/u-drift /path/to/project
```

`/u-drift` is **read-only**: it never modifies specs or source code. Its only writes are
under `{SPECS_DIR}/_validation/`:

| File | Purpose |
|---|---|
| `drift-report.md` | Human-readable report |
| `drift-report.json` | Machine-consumable source of truth (act on this) |
| `spec-inventory.json`, `code-inventory.json`, `drift-verdicts.json` | Intermediate artifacts |

It runs in the foreground (outside the orchestration engine, like `/u-reverse-spec`).
A single run is a single shot — there is no retry or supervisor; re-run it if interrupted.

---

## Reading the report

Every finding carries **status → severity → evidence → a mechanical action**. The action
is the contract — you execute it manually. No free-form recommendations are produced.

| Status | Meaning | Follow-up action |
|---|---|---|
| `missing_in_code` | Spec declares it; no implementation exists | `/u-dev` — implement it (the spec is the source of truth) |
| `missing_in_spec` | Code exposes it; no spec documents it | `/u-improve` — document it in the spec |
| `drifted` | Both exist but behavior diverges | Human triage — the finding carries both `fix_spec` and `fix_code` |
| `undecidable` | Not decidable deterministically (e.g. a `base_path` mismatch) | Human triage |

Skipped domains are surfaced separately with a reason:

| Skip reason | Meaning | Action |
|---|---|---|
| `draft_status` | Spec not approved (or spec/back status inconsistent) | Approve via `/u-spec`, then re-run |
| `parse_failed` | `openapi.yaml` could not be parsed | Fix the spec (or report a parser gap) and re-run |
| `no_spec_domain` | A code module has no matching spec | `/u-reverse-spec {CODE_DIR}` scoped to that module |
| `no_code_module` | A spec domain has no matching code | Verify module naming, or implement the domain |

Severity (`blocking` / `major` / `minor`) prioritizes triage within each status.

**Staleness guard:** the report pins `spec_content_hash` and `code_commit_sha`. Before
acting on an older report, confirm those still match the current specs and commit.

---

## Acting on the findings

`/u-drift` reports; it does **not** act. Work the handoffs in priority order:

1. `blocking` `missing_in_code` (unimplemented contract) → `/u-dev`
2. `drifted` / `undecidable` → human triage, then `/u-improve` or `/u-dev`
3. `missing_in_spec` (undocumented code) → `/u-improve`
4. `no_spec_domain` modules → scoped `/u-reverse-spec`

---

## When to use it

- After changes made **outside** the `/u-spec` → `/u-dev` pipeline.
- On a **legacy** codebase that outgrew its specs.
- As a **periodic** spec↔code audit.
- As the **compare-without-overwrite** path for existing specs (the suspended
  `/u-reverse-spec` merge mode now routes here).

---

## Scope and limits

- **Backend only** (`openapi.yaml` + `*.back.md`). Frontend feature-spec drift is out of
  scope in this release.
- **Approved specs only.** Drafts are skipped, not drifted.
- **Structural matching** (deterministic) covers endpoints, error codes, entity fields,
  state machines, and events by exact key. **Business rules and behavioral endpoint
  drift** are decided by the semantic layer, which is honest about uncertainty: an
  undecidable case returns `undecidable`, never a guess.
- **One code-derivable key per class.** Path parameters are normalized to `{param}`, so
  two sibling routes that differ only by parameter name share a key.

---

## For agent developers (advanced)

The engine lives in stdlib scripts (zero external dependencies) and each stage is
testable in isolation:

```bash
python3 .claude/skills/u-drift-analysis/scripts/spec_inventory.py --specs-dir <specs>
python3 .claude/skills/u-drift-analysis/scripts/match_drift.py \
  --spec-inventory si.json --code-inventory ci.json --out drift-report.json
python3 .claude/skills/u-drift-analysis/scripts/render_report.py --report drift-report.json
```

The full contract — matching keys, path normalization, severity/action tables, and the
structural-vs-semantic boundary — is documented in
`.claude/skills/u-drift-analysis/SKILL.md`.
