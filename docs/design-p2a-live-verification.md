# Design — P2-a: Live-Application Verification Gate (R1)

> Status: **DESIGN / proposal** (not implemented). Scope approved for design only.
> Origin: SIEGARD Field Evaluation Report, Recommendation 1. Addresses defect class
> D1/D2/D3/D7 and absorbs Recommendation 3 (real-DB QA).

---

## 1. Problem

Every existing gate validates artifacts against **specifications and mocks** — never
against the **running application + a real database**. Consequence observed on the
`curadoria-ui` run: the framework declared the feature dev-complete and 5/7 QA-approved
while `/curation` rendered only placeholders, and shipped two runtime endpoint bugs
(HTTP 503 on a `UNION uuid/text`; envelope/shape mismatch) that were green across
1164+1006 mocked tests. No phase ever booted the BFF+SPA and observed behavior.

The framework's definition of "verified" is *"declared exit-criteria pass + spec
conformance + unit/component suites pass."* There is no notion of *"the running product
does the thing."* This is architectural, not a single bug.

## 2. Goal / Non-goals

**Goal.** Add a capability that boots (or attaches to) the assembled application, drives
the changed surface, and asserts **observable behavior + zero console/network errors**
against an **ephemeral DB seeded with representative rows** — gated **before** the E99
human-approval escalation, so the human approves a *verified* deliverable.

**In scope (defect classes this reliably catches):**
- D1 — entry surface renders placeholders / never wired (smoke asserts a real control is present + no placeholder text).
- D2 — SQL type/serialization errors (the query runs against real Postgres).
- D3 — response envelope/shape mismatch (real HTTP client reads the real body).
- D7 — layout/runtime errors surfaced as console/network errors.

**Explicitly NOT in scope (do not oversell):**
- Semantic/business-correctness defects (D8 grouping, D10 date off-by-one, D11 missing
  subject label). A generic smoke does not assert domain semantics unless the smoke spec
  encodes them. These remain the responsibility of spec acceptance criteria + human review.
- Providing the project's runtime (DB engine, dev-server command, Playwright install).
  The framework ships the **gate and the contract**, never project infra (CLAUDE.md:
  "Do not implement business logic from downstream projects"; zero external deps).

## 3. Why a capability + contract, not a baked-in implementation

The framework is installed by manual copy into heterogeneous projects (Node/Fastify,
React, Postgres here; anything elsewhere). A hardcoded "boot Postgres + Playwright"
implementation would (a) embed downstream-specific infra, (b) require external deps,
(c) break portability. Therefore the live-verification worker is **driven entirely by a
project-supplied config contract**. With no contract present, the gate is **inert and
non-blocking** (additive — never breaks an existing pipeline that has not opted in).

## 4. Architecture

Two viable placements; **recommendation: a new optional `e2e` phase** ordered after
`review`, gated before review's E99 only if the project opts in via the simpler
"review-entry smoke" variant. Decision matrix:

| Option | Placement | Pros | Cons |
|---|---|---|---|
| **A — review exit criterion** | `check_live_smoke_passed.py` in `phase-review-rules`, run at Step 6 before `phase_exit_approved` | Catches before E99; no new phase; smallest surface | Couples review (artifact QA) with runtime execution; review workers are read-only |
| **B — new `e2e` phase** (recommended) | `phase-e2e-rules/` + `agents/orchestrator-e2e.md` + `agents/dev/u-e2e-runner.md`, ordered `…→review→e2e→test` | Clean separation; reuses phase machinery (entry guard, exit criteria, DLQ); runtime worker isolated | New phase; must run before the *final* human gate, so E99 placement is revisited |

Option B is preferred because the live run needs **Bash + a foreground orchestrator**
(boot/seed/drive are stateful shell operations) — the same constraint the meta-orchestrator
already enforces (`E_NO_BASH`). A dedicated phase keeps that requirement explicit and the
read-only review workers unchanged (P6 — least privilege).

```
sdd → dev → review → e2e → test
                       │
                       └─ orchestrator-e2e
                            ├─ entry guard: live-verify config present & app bootable
                            ├─ dispatch u-e2e-runner (FOREGROUND — needs Bash)
                            │     boot → seed → drive changed surface → collect result
                            └─ exit criteria:
                                  check_live_smoke_passed   (every smoke path passed)
                                  check_no_console_errors   (zero console/network errors)
```

### 4.1 The project-provided config contract

A new project file, read by `u-e2e-runner` (path via `ORCH_E2E_CONFIG`, default
`.orch/e2e-config.json`). Absent file ⇒ phase is a no-op, `met: true`, evidence
`{"skipped": "no_e2e_config"}`.

```jsonc
{
  "boot": {
    "command": "npm run dev:test",        // start assembled stack (or "attach" to running)
    "ready_check": "http://localhost:3000/health",  // poll until 2xx, then proceed
    "ready_timeout_s": 60,
    "teardown": "npm run dev:test:down"    // always run, even on failure
  },
  "database": {
    "mode": "ephemeral",                   // ephemeral | branch | attach
    "migrate": "npm run db:migrate:test",
    "seed": "npm run db:seed:test"         // representative rows the smoke needs
  },
  "smoke": [
    {
      "id": "curation-page-functional",
      "kind": "browser",                   // browser (Playwright) | http
      "spec": "e2e/curation.smoke.ts",     // project owns the driver script
      "asserts": ["no_placeholder_text", "decision_control_interactive", "no_console_errors"]
    },
    {
      "id": "metrics-endpoint",
      "kind": "http",
      "request": { "method": "GET", "path": "/api/v1/curation/metrics" },
      "expect": { "status": 200, "body_shape": "bare" }   // catches D2 (503) + D3 (envelope)
    }
  ]
}
```

The framework defines the **schema and the contract semantics**; the project supplies the
commands and driver scripts. The runner executes them via Bash and reduces results to a
structured artifact — it does not contain Playwright or a DB client itself.

### 4.2 Worker output artifact (deterministic, AI-FIRST)

`u-e2e-runner` emits `e2e/<workflow_id>-smoke.json` and a `task_completed` event:

```jsonc
{
  "workflow_id": "curadoria-ui",
  "booted": true,
  "db_mode": "ephemeral",
  "results": [
    { "id": "curation-page-functional", "passed": false,
      "failures": ["placeholder_text_found: 'Painel de decisão em construção'"],
      "console_errors": 0 },
    { "id": "metrics-endpoint", "passed": false,
      "failures": ["status 503 expected 200", "body_shape enveloped expected bare"] }
  ],
  "all_passed": false
}
```

`check_live_smoke_passed.py` and `check_no_console_errors.py` read this artifact and emit
the uniform gate schema `{status, check, criterion, met, timestamp, evidence}`.

## 5. How this absorbs R3 (real-DB QA)

R3 as a *static* review gate is weak: detecting "mock-only test" by parsing project source
is fragile and language-specific. The robust form of R3 is **execution against a real
schema** — which is exactly what §4.1 `database.mode: ephemeral|branch` provides. D2 (the
`UNION uuid/text` 503) surfaces because the smoke's HTTP call hits a route backed by real
Postgres; no separate "is this test real-DB?" heuristic is needed. R3 therefore folds into
this design rather than shipping as an independent fragile checker.

## 6. Invariant alignment

- **P6 (least privilege):** `u-e2e-runner` is the only worker granted Bash + network; review
  workers stay read-only. Declared in frontmatter `allowed-tools`.
- **P7 (robustness via hooks):** boot/teardown idempotent; teardown always runs.
- **P8 (evidence mandatory):** the gate cites the smoke artifact's failing entries.
- **P9/P10 (one phase per task / auditable transition):** `e2e` is a first-class phase with
  `phase_entered`/`phase_exit_approved`/`phase_transitioned` events.
- **P11 (exit criteria in code):** pass/fail is computed by `check_*.py`, not prose.
- **Foreground rule:** orchestrator-e2e requires Bash; fails fast with `E_NO_BASH` like the meta-orchestrator.

## 7. Failure modes & fail-closed policy

| Condition | Behavior |
|---|---|
| No `e2e-config.json` | No-op, `met: true`, evidence `skipped` (opt-in gate) |
| Config present but boot fails / ready_check times out | **Fail closed** — `met: false`, E08-style block; do not pass an unbootable app |
| Smoke driver script missing | Fail closed (config references a deliverable that must exist) |
| Any smoke path failed or console_errors > 0 | Fail closed |
| Teardown fails | Log warning; does not change verdict (artifact already collected) |

Fail-open is allowed **only** for the "no contract" case — once a project opts in, an
unbootable or failing app blocks. This is the inverse of the static gates (which fail-open
on empty scope) because here "could not verify" must not read as "verified".

## 8. Effort & phasing

| Step | Deliverable | Effort |
|---|---|---|
| 1 | `e2e-config.json` schema in `u-shared-templates` + validation | Low |
| 2 | `agents/dev/u-e2e-runner.md` (boot→seed→drive→reduce; foreground; Bash) | Medium |
| 3 | `phase-e2e-rules/` (exit-criteria.json, `check_live_smoke_passed.py`, `check_no_console_errors.py`, `select_worker.py`) | Medium |
| 4 | `agents/orchestrator-e2e.md` (entry guard, dispatch, exit eval) + phase-order wiring | Medium-High |
| 5 | Tests (`tests/orch/phase_scripts/test_check_e2e_exit_criteria.py`, lifecycle) + docs + manifest | Medium |

Total: **High.** This is the only structural fix for the report's thesis; it is a strategic
item, not a quick win. P0-a/P0-b (shipped) already deterministically catch the headline D1
and the D5 misdiagnosis at far lower cost.

## 9. Open questions (resolve before implementing)

1. **Phase vs review-entry.** Option B (new phase) is cleaner but moves the final human gate.
   Does E99 stay in `review`, or move to `e2e`? (Proposal: keep E99 in review for code
   quality; add an info-level `e2e` summary the human sees, with `e2e` exit blocking
   `test`.)
2. **Attach vs boot.** Should the runner ever boot, or only attach to a stack the operator
   started? Booting in CI is heavy; attaching needs the operator to pre-run. (Proposal:
   support both via `boot.command: "attach"`.)
3. **Per-feature smoke selection.** How does the runner know which smoke paths map to *this*
   workflow's changed surface? (Proposal: smoke entries tagged; runner runs all by default,
   or the subset named in `ORCH_E2E_SMOKE_IDS`.)
4. **Cost.** A live run adds minutes + a DB. Acceptable given it gates the human approval?
