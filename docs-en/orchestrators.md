# Orchestrators — Architecture and Hierarchy

> **Who is this document for?**
> Anyone who wants to understand how the orchestration system works — even without programming experience.
> Technical details are included but always explained in plain language first.

---

## What is an Orchestrator?

Imagine a **conductor of an orchestra**. The conductor doesn't play any instrument — they coordinate who plays when, at what speed, and what to do if someone makes a mistake. That's exactly what an orchestrator does in this system.

An orchestrator:
- Reads the current state of the work (from a log file)
- Decides what needs to be done next
- Assigns tasks to specialized agents (workers)
- Monitors whether tasks were completed correctly
- Handles failures, retries, and escalations to humans

> **Key rule:** orchestrators never do the actual work. They only coordinate who does it.

---

## The Two Independent Pipelines

The system has two separate pipelines that operate independently:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PIPELINE 1 — Main Workflow                                             │
│                                                                         │
│  User invokes the orchestrator → system executes the complete           │
│  workflow: specification → development → review → testing               │
│                                                                         │
│  Entry point: orchestrator (meta-orchestrator)                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  PIPELINE 2 — Reverse Engineering                                       │
│                                                                         │
│  User has existing code and wants to generate specs from it.            │
│  Analyzes the code and produces draft specifications.                   │
│                                                                         │
│  Entry point: u-reverse-spec-orchestrator                               │
│  Triggered by: /u-reverse-spec [CODE_DIR] command                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline 1 — Main Workflow

### The Meta-Orchestrator: the "air traffic controller"

The `orchestrator` is the **only entry point** for all workflows. Think of it as the air traffic controller at an airport: it doesn't fly the planes, but it decides which one takes off, which one lands, and what to do in an emergency.

```
User calls orchestrator
         │
         ▼
  ┌─────────────────┐
  │  "Where are     │   Reads the log (event history) to find out:
  │   we right now?"│   - Did work already start?
  │                 │   - Which phase are we in?
  │                 │   - Is there a pending problem?
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  Route to the   │   Looks at the phase table and calls the
  │  right phase    │   correct specialist orchestrator
  └─────────────────┘
```

**What the meta-orchestrator does, step by step:**

| Step | What it does | Analogy |
|------|-------------|---------|
| 1 — Infrastructure check | Verifies the system is healthy before starting | Pilot's pre-flight checklist |
| 2 — State derivation | Reads the log to understand where the workflow stands | Reading a work notebook |
| 3 — Terminal check | Is the work finished? Is there an unresolved problem? | "Are we done or is there a fire?" |
| 4 — First-run initialization | If nothing has started yet, creates the workflow ID and declares the phases | Opening a new job ticket |
| 5 — Phase entry | If no phase is active, starts the next one | "Let's start phase 1" |
| 6 — Spawn phase orchestrator | Calls the specialist for the current phase | Delegating to the right department |
| 7 — Evaluate return | The specialist finished — what now? | Checking if the department did its job |

**Safety limit:** the meta-orchestrator runs **exactly one phase orchestrator per invocation** (invariant I5). When a phase completes and the workflow is not yet finished, it outputs `phase_advanced` and stops — the caller (e.g. `/u-dev`) re-invokes it to start the next phase. This keeps the context bounded per invocation regardless of how long the workflow is. A cycle counter guards against logic bugs: reaching **2** means something is wrong and it stops.

---

### The Four Phases and Their Orchestrators

The main workflow has four phases in fixed order. Each has a dedicated orchestrator:

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   Phase 1          Phase 2          Phase 3          Phase 4        │
│                                                                      │
│  ┌────────┐       ┌────────┐       ┌────────┐       ┌────────┐     │
│  │  SDD   │──────▶│  DEV   │──────▶│ REVIEW │──────▶│  TEST  │     │
│  │        │       │        │       │        │       │        │     │
│  │ Write  │       │ Build  │       │  QA    │       │  Run   │     │
│  │ specs  │       │ the    │       │ review │       │ tests  │     │
│  │        │       │ code   │       │        │       │        │     │
│  └────────┘       └────────┘       └────────┘       └────────┘     │
│                                                                      │
│  orchestrator-sdd  orchestrator-dev  orchestrator-review  orch-test  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

Phases are not always sequential — review can return tasks to dev,
and test can return tasks to dev if failures are found.
```

> **Important:** any phase can send tasks **back to a previous phase**. This is not a failure — it's the system correcting itself before moving forward.

---

### Phase 1 — SDD (orchestrator-sdd)

**What SDD means:** Specification-Driven Development — writing detailed specifications before writing code.

**Analogy:** before building a house, you draw the blueprints. SDD is the blueprints.

**Model used:** `claude-sonnet-4-6` (the orchestrator only coordinates — the deep reasoning happens inside the spec workers).

```
                    orchestrator-sdd
                          │
                          ▼
    Step 0.5 — TRIAGE (always first, synchronous)
    ┌─────────────────────────────────────────────────────┐
    │  u-spec-triage writes triage.json:                  │
    │   - trigger (/u-spec vs /u-improve)                 │
    │   - affected specs / domains                        │
    │   - mode_hint + execution policy                    │
    └────────────────────────┬────────────────────────────┘
                             │  derives effective_mode + bypass_e99
                             ▼
          ┌──────────────────────────────────┐
          │  Human gate (E99)                │
          │  required, UNLESS bypass_e99=true │ ← /u-improve already confirmed
          └──────────────────┬───────────────┘
                             │
            ┌────────────────┴─────────────────┐
            │                                  │
       STANDARD mode                      TARGETED mode
       (new spec / broad change)          (localized improve)
            │                                  │
            ▼                                  ▼
   For each domain — strict pipeline:   Only the affected specs:
   spec-writer → spec-reviewer →        domain worker + spec-reviewer
   spec-back → spec-validator →         (writer/validators/compliance
   spec-front → spec-validator           skipped, logged as task_skipped)
            │                                  │
            ▼                                  │
   After all domains:                          │
   spec-compliance (cross-domain)              │
            └────────────────┬─────────────────┘
                             ▼
    Exit criteria (all must be true):
      ✓ handoff-manifest approved
      ✓ all domains validated         (standard)
        OR all improve reviewers done  (targeted)
      ✓ error codes synchronized
                             │
                             ▼
                      → transitions to DEV
```

**What each worker does in the SDD pipeline:**

| Worker | Responsibility |
|--------|---------------|
| `u-spec-triage` | Runs first (synchronous). Classifies the request and writes `triage.json` — the orchestrator reads it to pick the mode |
| `spec-writer` | Writes the initial specification from scratch |
| `spec-reviewer` | Reviews and approves (or rejects) the spec |
| `spec-back` | Adds backend-specific details (APIs, database) |
| `spec-validator` | Validates technical correctness |
| `spec-front` | Adds frontend-specific details (screens, flows) |
| `spec-validator` (2nd pass) | Re-validates after frontend additions |
| `spec-compliance` | Cross-domain consistency check |

**Operating modes (derived from `triage.json`):**
- **standard** — new spec or broad change; runs the full pipeline for each domain.
- **targeted** — localized `/u-improve` change; only the affected specs go through `domain worker + spec-reviewer`; writer/validators/compliance are skipped. Exit uses `all_improve_reviewers_completed` instead of `all_domains_validated`.
- **implementation_only** — `/u-improve` with no spec impact; SDD exits immediately and the workflow goes straight to DEV.

**Human gates in SDD:**
- Before the first dispatch, the human must confirm the pipeline state (E99 gate).
- When the trigger is `/u-improve`, `bypass_e99` is set and this confirmation is skipped (it was already given earlier).

**Escalation codes:**
| Code | When | What it means |
|------|------|--------------|
| E99 | Before first dispatch | "Please confirm you want to proceed" |
| E05 | Too many rejections | spec-writer ≥3 attempts or spec-validator ≥2 — needs human attention |
| E06 | Dispatch loop limit | Loop reached 30 iterations without converging — tasks stuck |
| E11 | Missing input files | spec-reviewer found files that should exist but don't |
| E12 | State reduction failed | `reduce.py` errored — log may be corrupt |
| E08 | All done but criteria not met | Something is wrong with the output — needs investigation |

---

### Phase 2 — DEV (orchestrator-dev)

**What DEV means:** implementation — building the code based on the approved specs.

**Analogy:** the builders who follow the blueprints.

**Model used:** `claude-sonnet-4-6` (balanced model — implementation is guided by specs).

**Key feature:** this phase is **fully autonomous** — no human confirmation is needed during execution.

```
                    orchestrator-dev
                          │
                          ▼
              Validates handoff-manifest
              (the approved "briefing" from SDD)
                          │
              dev_impact == "no_action"? ──▶ skip to review
                          │
                          ▼
                  ┌───────────────┐
                  │   PLANNING    │
                  │               │
                  │  Planner reads │
                  │  handoff and  │
                  │  generates:   │
                  │  backlog.json │
                  │  tc-NNN.md    │
                  │  (task cards) │
                  └───────┬───────┘
                          │
                          ▼
              Creates one task per task contract:
              dev_tc_001, dev_tc_002, dev_tc_003...
                          │
                          ▼
              ┌─────────────────────────────┐
              │      DISPATCH LOOP          │
              │                             │
              │  Picks up to 2 ready tasks  │
              │  Spawns workers in parallel │
              │  Each worker:               │
              │   - reads task spec (tc-NNN)│
              │   - writes delivery.md      │
              │   - emits task_completed    │
              │                             │
              │  Failures → retry           │
              │  Max retries → DLQ+escalate │
              └──────────────┬──────────────┘
                             │
                             ▼
              Exit criteria:
                ✓ all impl tasks terminal
                ✓ all deliveries qa_ready
                ✓ no open prohibitions
                             │
                             ▼
                    → transitions to REVIEW
```

**Retry logic:** if a worker fails, the orchestrator decides based on policy:
- Retryable failure → schedules retry with backoff (waiting period between attempts)
- Non-retryable failure → sends to DLQ (Dead Letter Queue) and escalates

**DLQ (Dead Letter Queue):** a "quarantine" for tasks that failed too many times. The orchestrator escalates to the human so they can investigate what went wrong.

**Escalation codes:**
| Code | When | What it means |
|------|------|--------------|
| E07 | Planning failed | Could not generate the backlog — check the handoff-manifest |
| E04 | Task in DLQ | Implementation task failed non-retryably |
| E08 | Exit criteria not met | All tasks finished but something is still wrong |

---

### Phase 3 — REVIEW (orchestrator-review)

**What REVIEW means:** quality assurance — QA agents review the deliveries from DEV.

**Analogy:** building inspectors who check the construction against the blueprints.

**Model used:** `claude-sonnet-4-6`

**Key feature:** QA dispatch is autonomous, but **final approval always requires a human**.

```
                    orchestrator-review
                          │
                          ▼
            Reads dev_completed_tasks with artifacts
                          │
                          ▼
            Creates one review task per dev task:
            review_dev_tc_001, review_dev_tc_002...
                          │
                          ▼
              ┌─────────────────────────────┐
              │      DISPATCH LOOP          │
              │                             │
              │  Each task is classified by │
              │  qa_mode (micro/standard/   │
              │  full) → drives concurrency │
              │                             │
              │  QA workers review each     │
              │  delivery artifact and      │
              │  produce a qa.md verdict    │
              │                             │
              │  Verdict is binary:         │
              │   approved                  │
              │   rejected                  │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │    HUMAN APPROVAL GATE      │  ← mandatory*
              │                             │
              │  Shows verdict summary      │
              │  Flags SPEC-DIVERGENCE      │
              │  (cases where implementation│
              │   had to deviate from spec) │
              │                             │
              │  Human chooses:             │
              │  ├─ approve → continue      │
              │  ├─ return_to_dev → all     │
              │  │  failed tasks go back    │
              │  └─ return_partial → only   │
              │     selected tasks go back  │
              └──────────────┬──────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
         APPROVED                     RETURNED TO DEV
              │                             │
              ▼                             ▼
         Exit criteria:           Creates revision tasks:
           ✓ all verdicts approved  dev_tc_001_r1,
           ✓ no critical findings   dev_tc_002_r1...
           ✓ documentation verified
              │
              ▼
     → transitions to TEST
```

*\*Auto-approval:* the orchestrator may skip the human gate **only** when the strict Step 5.0 gate qualifies — every completed review task is `qa_mode == micro`, all verdicts are `approved`, and there are no severe findings. In that case it emits `E18_auto_approval_granted` and synthesizes the approval itself. The decision is bound to a Python script exit code, not the prompt (invariant I8). An operator can still override by appending a `return_to_dev` response.

**Special workers (not part of automatic QA dispatch):**
- `u-architecture-reviewer` — reviews architectural decisions
- `u-security-reviewer` — security vulnerability review

The automatic dispatch creates one `qa` task per completed dev task. These two reviewers are injected by an operator when desired; they write to `<session_dir>/reviews/`.

**Escalation codes:**
| Code | When | What it means |
|------|------|--------------|
| E99 | After QA completes | "QA finished — please approve or return to dev" |
| E18 | Auto-approval gate met | Orchestrator synthesized the approval (micro, unanimous, clean) |
| E09 | SPEC-DIVERGENCE found | Implementation deviated from spec — a Change Request may be needed |
| E16 | Shared build failed | The shared build/test suite failed — QA cannot be dispatched |
| E17 | Suite parser degraded | Could not parse test failures — falls back to per-task gate |
| E19 | qa_mode classifier failed | Classifier errored — task created as `standard` (warning only) |
| E08 | Criteria not met / DLQ | Human approved but checks still fail, or review tasks remain in DLQ |

---

### Phase 4 — TEST (orchestrator-test)

**What TEST means:** automated test execution — running the test suites described in deliveries.

**Analogy:** final quality inspection — everything under real conditions.

**Model used:** `claude-sonnet-4-6`

**Key feature:** if all tests pass, the workflow completes **with no human intervention**. Only failures require a human decision.

```
                    orchestrator-test
                          │
                          ▼
            Reads dev_completed_tasks with artifacts
                          │
                          ▼
            Creates one test task per dev task:
            test_dev_tc_001, test_dev_tc_002...
                          │
                          ▼
              ┌─────────────────────────────┐
              │      DISPATCH LOOP          │
              │                             │
              │  Test workers execute the   │
              │  test suites and produce:   │
              │  test-reports/<id>-report.md│
              │                             │
              │  Stale thresholds:          │
              │   critical tasks → 600s     │
              │   standard tasks → 300s     │
              │   bulk tasks → 120s         │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────────────┐
              │           EXIT CRITERIA              │
              │                                     │
              │  ✓ all test tasks terminal           │
              │  ✓ all tests passed                  │
              │  ✓ no critical failures              │
              │                                     │
              │  ALL MET → workflow complete! ──────▶│
              │                                     │
              │  FAILURES EXIST:                    │
              │  Human decides:                     │
              │  ├─ return_to_dev → revision tasks  │
              │  └─ accept_with_failures → done      │
              │     (known/acceptable failures)      │
              └─────────────────────────────────────┘
```

**Escalation codes:**
| Code | When | What it means |
|------|------|--------------|
| E04 | Non-retryable test failure | Test failed definitively — needs investigation |
| E99 | Test failures found | "Tests failed — return to dev or accept?" |
| E08 | Tasks done but criteria fail | Internal inconsistency |

---

## Pipeline 2 — Reverse Engineering (u-reverse-spec-orchestrator)

**What it does:** given an existing codebase, automatically generates draft specifications.

**When to use:** when you have a project that was built without formal specs and you want to bring it into the main pipeline (`/u-spec`, `/u-dev`).

**Analogy:** a historian who reads an ancient building and produces a technical blueprint from what was built.

**Key feature:** strongly interactive — asks for human confirmation at every significant step.

```
  User: /u-reverse-spec ./my-project
           │
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  u-reverse-spec-orchestrator                                │
  │                                                             │
  │  NEVER analyzes code directly                               │
  │  NEVER writes specs directly                                │
  │  Always delegates to specialized agents                     │
  └─────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 0             │  Has a previous session log?
  │  Resume Check       │  If yes → continue from where it stopped
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐  ┌─────────────────────────────────────┐
  │  Step 1             │  │  Detects:                           │
  │  Stack Detection    │  │  - Language (Python, JS, Java...)   │
  │             [HUMAN] │  │  - Framework (Django, React...)     │
  │  Confirmation gate  │  │  - Database (Postgres, MongoDB...)  │
  └────────┬────────────┘  │  - Context (backend/frontend/both) │
           │               └─────────────────────────────────────┘
           │  Human confirms or corrects the detection
           ▼
  ┌─────────────────────┐  ┌─────────────────────────────────────┐
  │  Step 2             │  │  Modes:                             │
  │  Mode Detection     │  │  New    — specs/ doesn't exist      │
  │                     │  │  Resume — analysis already done     │
  └────────┬────────────┘  │  Merge  — specs exist, will compare│
           │               └─────────────────────────────────────┘
           ▼
  ┌─────────────────────┐
  │  Step 3             │  Invokes u-reverse-spec-analyzer
  │  Analysis           │  → reads source code
  │  (delegates)        │  → produces analysis-report.md
  │                     │    (entities, endpoints, rules, screens)
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 4             │  Shows summary table:
  │  Summary            │  domains | entities | endpoints | gaps
  │             [HUMAN] │
  │  Confirmation gate  │  Human: Y / N / Adjust
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 5             │  Invokes u-reverse-spec-writer
  │  Generation         │  Per domain, generates (in order):
  │  (delegates)        │  1. openapi.yaml  ← MANDATORY
  │                     │  2. {domain}.spec.md
  │                     │     3. {domain}.back.md (if backend)
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 6             │  Verifies all artifacts exist
  │  Validation Gate    │  Missing → re-invokes writer (max 2x)
  │  MANDATORY          │  Still missing → escalates to human
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 7             │  (if specs already existed)
  │  Merge              │  Shows diff, applies only confirmed changes
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 8             │  Creates _meta/origin-reverse-spec.md
  │  Origin Marker      │  → tells /u-spec and /u-dev that
  │                     │    specs came from reverse engineering
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │  Step 9             │  Shows artifact summary
  │  Completion         │  Suggests next step: /u-spec [SPECS_DIR]
  └─────────────────────┘

All artifacts are created with status "draft" — they still need
to be reviewed and approved via /u-spec before dev can start.
```

---

## Complete Hierarchy Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                      USER / OPERATOR                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
              ┌─────────────┴──────────────┐
              │                            │
              ▼                            ▼
  ┌───────────────────────┐    ┌──────────────────────────┐
  │     orchestrator      │    │  u-reverse-spec-orch      │
  │   (meta-orchestrator) │    │  /u-reverse-spec command  │
  │                       │    │                          │
  │  • Routes phases      │    │  • Analyzes existing code│
  │  • Zero domain logic  │    │  • Produces draft specs  │
  │  • 1 phase/invocation │    │  • Interactive (gates)   │
  │  • Log is the truth   │    │  • Output: draft specs   │
  └────────────┬──────────┘    └────────────┬─────────────┘
               │                            │
      Phase routing                    Delegates to
               │                            │
   ┌───────────┴──────────┐         ┌───────┴───────┐
   │                      │         │               │
   ▼                      │    u-reverse-spec-   u-reverse-spec-
┌──────────────┐          │    analyzer           writer
│orchestrator  │          │    (reads code)       (writes specs)
│    -sdd      │          │
│              │          │
│ • sonnet-4-6 │          │
│ • Semi-auto  │          │
│ • E99 gate   │          │
│ • triage +   │          │
│   pipeline   │          │
│   per domain │          │
└──────┬───────┘          │
       │                  │
  Spawns workers:         │
  u-spec-triage (first)   │
  spec-writer             │
  spec-reviewer           │
  spec-back               │
  spec-validator          │
  spec-front              │
  spec-compliance         │
       │                  │
       ▼                  │
┌──────────────┐          │
│orchestrator  │          │
│    -dev      │          │
│              │          │
│ • sonnet-4-6 │          │
│ • Full auto  │          │
│ • No gates   │          │
│ • Planning   │          │
│   + dispatch │          │
└──────┬───────┘          │
       │                  │
  Spawns workers:         │
  u-be-planner            │
  u-fe-planner            │
  u-be-developer          │
  u-fe-developer          │
  u-fe-spec-writer        │
       │                  │
       ▼                  │
┌──────────────┐          │
│orchestrator  │          │
│   -review    │          │
│              │          │
│ • sonnet-4-6 │          │
│ • Semi-auto  │          │
│ • E99 gate   │          │
│   (human     │          │
│   approval)  │          │
│ • Can return │          │
│   to dev     │          │
└──────┬───────┘          │
       │                  │
  Spawns workers:         │
  u-be-qa-docs            │
  u-fe-qa-docs            │
  u-architecture-reviewer │
  u-security-reviewer     │
       │                  │
       ▼                  │
┌──────────────┐          │
│orchestrator  │          │
│    -test     │          │
│              │          │
│ • sonnet-4-6 │          │
│ • Full auto  │          │
│   if passes  │          │
│ • Gate only  │          │
│   on failure │          │
│ • Can return │          │
│   to dev     │          │
└──────────────┘          │
                          │
  Spawns workers:         │
  (test-run workers)      │
                          │
  ──────────────────      │
  Output: phase_complete  ◄┘
  Workflow done!
```

---

## The Log: the "Single Source of Truth"

One of the most important concepts in this system is that **the log is the only truth**.

```
  ┌──────────────────────────────────────────────────────────────┐
  │  .orch/log.jsonl  (append-only file)                        │
  │                                                              │
  │  {"seq":1, "event":"phase_declared",   "agent":"orch"   ...}│
  │  {"seq":2, "event":"phase_entered",    "agent":"orch"   ...}│
  │  {"seq":3, "event":"task_created",     "agent":"orch-sdd"...}│
  │  {"seq":4, "event":"task_claimed",     "agent":"orch-sdd"...}│
  │  {"seq":5, "event":"task_completed",   "agent":"worker" ...}│
  │  {"seq":6, "event":"phase_transitioned","agent":"orch-sdd"...}│
  │  ...                                                         │
  └──────────────────────────────────────────────────────────────┘
```

**Why this matters:**
- Every orchestrator reads the log at the start of each step — never trusts its own memory
- If the system crashes in the middle, the next invocation reads the log and resumes exactly where it left off
- Nothing is ever deleted from the log — corrections are made by adding new events
- Every decision cites the log sequence numbers that justify it (evidence_seq)

---

## Human Gates: when the system asks for a decision

The system is designed to be autonomous, but certain decisions require a human. These moments are called **escalation gates**.

```
Types of escalation:

  E99 — "I need your approval to proceed"
  ├─ SDD: confirms the spec pipeline before starting
  ├─ Review: approves QA verdicts before moving to test
  └─ Test: decides what to do about test failures

  E04 — "A task failed and cannot be retried"
  └─ Needs investigation: what went wrong?

  E05 — "A spec was rejected too many times"
  └─ The spec may have a structural problem

  E06 — "Dispatch loop did not converge"
  └─ Reached 30 iterations — tasks stuck in retry

  E07 — "Planning failed"
  └─ The handoff-manifest may have issues

  E08 — "All tasks are done but criteria are not met"
  └─ Something is inconsistent — needs review

  E09 — "The implementation deviated from the spec"
  └─ A Change Request (CR) may be needed

  E10 — "Phase orchestrator error + circuit breaker tripped"
  └─ Multiple failures detected — needs urgent attention

  E11 — "Required spec files are missing"
  └─ Create the files and re-invoke

  E12 — "State could not be derived from the log"
  └─ reduce.py errored — log may be corrupt

  E13 — "Phase orchestrator returned no valid output"
  └─ Possible context overflow or startup failure (auto-retries first)

  E14 — "Confirm the improvement before proceeding"
  └─ /u-improve gate before the SDD phase

  E16 — "Shared build/test suite failed" (review)
  └─ QA cannot start until the build is fixed

  E17 — "Test output parser degraded" (review, warning)
  └─ Falls back to per-task test gate

  E18 — "Auto-approval granted" (review, info)
  └─ Micro + unanimous + clean: orchestrator approved automatically

  E19 — "qa_mode classifier failed" (review, warning)
  └─ Task defaulted to standard mode
```

> Codes **E16–E19** are review-phase only. The full, authoritative reference is `dist/.claude/ESCALATION_CODES.md`.

**To resume after an escalation:**
The human emits a `human_response` event with an `action` field. The available actions depend on the escalation code. Then they invoke the orchestrator again — it reads the response from the log and continues.

---

## Autonomy Levels by Phase

```
Phase       │ Dispatch  │ Completion │ Failures   │ Human Gate
────────────┼───────────┼────────────┼────────────┼───────────
SDD         │ Semi-auto │ Auto       │ Escalates  │ Before 1st
            │ (E99 gate │            │            │ dispatch
            │ before    │            │            │
            │ 1st disp) │            │            │
────────────┼───────────┼────────────┼────────────┼───────────
DEV         │ Full auto │ Auto       │ Retry →    │ None
            │           │            │ DLQ →      │
            │           │            │ Escalate   │
────────────┼───────────┼────────────┼────────────┼───────────
REVIEW      │ Full auto │ Needs      │ Retry      │ Final
            │           │ approval   │            │ approval
────────────┼───────────┼────────────┼────────────┼───────────
TEST        │ Full auto │ Auto if    │ Retry →    │ Only on
            │           │ all pass   │ Human if   │ failure
            │           │            │ non-retry  │
```

---

## Shared Infrastructure

All orchestrators use the same set of shared skills (libraries):

| Skill | What it does |
|-------|-------------|
| `orch-log` | Read/write/verify the event log |
| `orch-state` | Derive current state from the log (reduce.py, current_phase.py) |
| `orch-infra` | Infrastructure checks (preflight, integrity, circuit breaker) |
| `orch-report` | Safe interface for workers to emit events (blocks unauthorized event types) |

**Circuit breaker:** if too many failures occur in a short time, the circuit breaker "trips" and prevents new tasks from being dispatched. This avoids cascade failures. An operator must reset it after resolving the underlying issue.

---

## Summary Table

| Orchestrator | Phase | Model | Autonomy | Human gates | Next phase |
|-------------|-------|-------|----------|-------------|------------|
| `orchestrator` | — (routes) | sonnet-4-6 | Routing only | Escalations | Any phase |
| `orchestrator-sdd` | SDD | sonnet-4-6 | Semi | E99 before dispatch (bypassed for `/u-improve`) | dev |
| `orchestrator-dev` | DEV | sonnet-4-6 | Full | None | review |
| `orchestrator-review` | REVIEW | sonnet-4-6 | Semi | E99 for approval | test or dev |
| `orchestrator-test` | TEST | sonnet-4-6 | Full* | E99 only on failure | done or dev |
| `u-reverse-spec-orchestrator` | Reverse Eng | sonnet-4-6 | Interactive | Every phase | /u-spec |

*Full autonomy only when all tests pass.
