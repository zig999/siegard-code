---
name: u-spec-back-writing
description: Checklist and quality rules for backend specification writing. Used by the Back Spec Agent to ensure completeness and correctness of .back.md artifacts.
user-invocable: false
---

# Skill: Backend Spec Writing

## Data Modeling Checklist

- [ ] All entities have explicit primary key strategy (uuid, auto-increment, composite)
- [ ] All FKs have explicit `on-delete` rule (CASCADE, SET NULL, RESTRICT)
- [ ] Index justification documented for all non-PK fields used in WHERE clauses
- [ ] Enum values listed explicitly — no open-ended "etc."
- [ ] Nullable vs. required fields declared for every column
- [ ] Soft-delete strategy declared if entities can be deactivated
- [ ] If soft-delete: corresponding endpoint uses PATCH or POST (never DELETE)
- [ ] If hard-delete: DELETE endpoint is justified in a BR (irreversible by design)

## Business Rules Checklist

- [ ] Each BR cites its `Source rule` (`{domain}.spec.md BR-NN`) — the `.spec.md` is the single normative source; the back BR never restates WHAT the rule is
- [ ] `Description` declares only HOW the rule is enforced: guards, edge cases, extension strategy, implementation artifacts
- [ ] `Where to validate` holds pointers (layer · file · symbol · test name) — never test plans or fixture code (test requirements live in u-be-standards)
- [ ] `Error returned` points to the `.spec.md` §6 Error Behaviors row — never redeclares the error table
- [ ] Each BR references the UC that originates it (`UC-NN`)
- [ ] Validation layer specified for each BR (API gateway | service | repository)
- [ ] Error code registered in global catalog for each BR violation
- [ ] Edge cases documented for each BR (what happens at boundary values)
- [ ] Conflict resolution documented when two BRs can contradict each other
- [ ] BR titles and bodies describe the current state only — no version markers (`(v1.2.0: ...)`) or migration narratives; history belongs to the Changelog, git, and `decisions.md`
- [ ] If a domain concept supports multiple implementations that may grow (e.g., payment method, notification channel, export format), extension strategy declared: `polymorphism` | `strategy pattern` | `closed enum + factory`. If closed (variants will not grow), say so explicitly. Never left implicit.

## State Machine Checklist

- [ ] All states enumerated (no implicit "other" state)
- [ ] All valid transitions mapped (From → Trigger → To)
- [ ] Guard conditions explicit for each transition
- [ ] Terminal states identified
- [ ] Invalid transition behavior documented (reject silently or throw error)

## Event Payload Checklist

- [ ] Producer domain identified
- [ ] Consumer domains listed
- [ ] Payload schema fields typed with JSON schema or TypeScript equivalent
- [ ] At-least-once or exactly-once delivery semantics declared
- [ ] Event versioning strategy declared (if events are persisted or shared cross-service)

## Changelog Checklist

- [ ] Each entry `Description` is a single sentence, max 200 characters (what changed + which sections touched)
- [ ] No incident narratives, before/after comparisons, or rationale in entries — that detail lives in git history and the orchestration log
- [ ] Max 10 rows — oldest rows collapsed into a single `rollup` row when exceeded

## Quality Gate

The Back Spec Agent must not mark a `.back.md` as ready for the Validator unless all checked items in each applicable section above are filled. Sections not applicable to the domain (e.g., no events) may be omitted with a note: `N/A — no domain events`.
