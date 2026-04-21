# Protocol: Handoff Spec -> Dev

## Purpose
Define how the Spec group delivers approved artifacts to the Dev group, ensuring the transition is traceable, versioned, and without information loss.

## Preconditions for handoff

Before delivering, the Spec Orchestrator must verify:
- [ ] All domains in the requirement have `VALID` status from the Spec Validator
- [ ] All `error.code` are registered in the global catalog
- [ ] Changelog updated in all files
- [ ] Cross-domain dependencies verified (bidirectional, no drafts)
- [ ] If `{SPECS_DIR}/_validation/{domain}-validation-result.yaml` exists, status must be `VALID` or Triage `COMPLETED`
- [ ] **No open CRs blocking delivery:** for each `cr-NN.yaml` in `{SESSIONS_DIR}/{SESSION}/`, check `resolution.status`. If any CR has `resolution.status: open` and `impact.dev_blocked: true`, halt handoff and escalate to human. CRs with `resolution.status: accepted`, `rejected`, or `deferred` do not block delivery.
- [ ] **Version consistency:** for each domain, confirm that `validation-result.yaml` `validation.artifact_version` matches the domain version in the pending handoff manifest. If there is a mismatch, the validation result was generated from a different spec version — re-run the Validator before generating the manifest.

## Delivery package

### For the backend Dev Team

| File | Path | Consumed by |
|------|------|-------------|
| OpenAPI contract | `{SPECS_DIR}/domains/{domain}/openapi.yaml` | Developer (via context-mounting) |
| Business spec | `{SPECS_DIR}/domains/{domain}/{domain}.spec.md` | Planner (UCs -> Task Contracts) |
| Back-end spec | `{SPECS_DIR}/domains/{domain}/back/{domain}.back.md` | Developer (BRs, STs, EVs, model) |
| Error codes | `{SPECS_DIR}/_global/error-codes.md` | Developer (error handlers) |
| Glossary | `{SPECS_DIR}/_global/glossary.md` | Planner (terminology) |
| Validator report | (inline in log) | Reference |

### For the frontend Dev Team

| File | Path | Consumed by |
|------|------|-------------|
| OpenAPI contract | `{SPECS_DIR}/domains/{domain}/openapi.yaml` | Developer (consumed endpoints — one per domain) |
| Business spec | `{SPECS_DIR}/domains/{domain}/{domain}.spec.md` | Planner (UCs -> Task Contracts — one per domain) |
| Global frontend spec | `{SPECS_DIR}/front/front.md` | Developer (stack, state, routing, patterns) |
| Feature specs | `{SPECS_DIR}/front/features/{feature}.feature.spec.md` | UI Agent + Planner (mandatory base per feature/route — generates Task Contracts) |
| Component specs | `{SPECS_DIR}/front/components/{name}.component.spec.md` | Developer + UI Agent (Props Contract, States, BDD — conditional) |
| Flow specs | `{SPECS_DIR}/front/_flows/{flow}.flow.md` | UI Agent + Planner (navigation flows) |
| Decisions log | `{SPECS_DIR}/decisions.md` | Orchestrator + Planner (active decisions override SKILL defaults) |
| Error codes | `{SPECS_DIR}/_global/error-codes.md` | Developer + UI Agent |
| Glossary | `{SPECS_DIR}/_global/glossary.md` | Planner (terminology) |

> **Note:** a feature may consume endpoints from multiple domains. The Dev Team must load the `openapi.yaml` from ALL domains referenced in §1 of each feature spec.

### For the fullstack Dev Team (`domain: fullstack`)

When the project uses `domain: fullstack`, the Fullstack Meta-Orchestrator receives **both** delivery packages above. The meta-orchestrator:

1. Passes backend artifacts to the BE orchestrator during Phase 1
2. Passes frontend artifacts to the FE orchestrator during Phase 2
3. The FE phase additionally receives the `handoff-be-to-fe.md` generated after Phase 1 completes (see `u-fullstack-coordination.md`)

The artifact list is the same — the difference is in sequencing and the inter-phase handoff.

## Handoff manifest (machine-readable)

Immediately after verifying all preconditions and assembling the delivery packages, the Spec Orchestrator MUST generate:

- Path: `{SPECS_DIR}/handoff-manifest.yaml`
- Template: `.claude/skills/u-shared-templates/handoff-manifest.yaml`
- Overwrite on every handoff — always reflects the most recent delivery
- For fast-track/evolution handoffs, populate `change_summary` with type, CR, changed files, and `dev_impact`
- Compute sha256 for every entry in `backend_package[]` and `frontend_package[]` at generation time. The hash covers the raw file contents at `{SPECS_DIR}/{path}` — Dev orchestrators verify the hash before consuming the artifact (rules HDF-020 / HDF-021 in `u-handoff-validator`).
- Before writing the file, invoke `u-handoff-validator` with `caller=u-spec-orchestrator` against the in-memory manifest. If the envelope returns `status: invalid`, halt and fix — do not persist an invalid manifest.

The Dev Orchestrator reads this manifest at session start, invokes `u-handoff-validator` to validate it, and consumes the returned envelope (it does NOT parse narrative text). The orchestrator then emits a `handoff-receipt.yaml` acknowledging consumption (see "Handoff receipt" below).

## Handoff receipt (bidirectional acknowledgment)

After consuming a valid manifest, the Dev Orchestrator MUST emit a machine-readable receipt:

- Path: `{SPECS_DIR}/handoff-receipts/{manifest_id}-{orchestrator}.yaml`
  - `{manifest_id}` matches `handoff.id` from the consumed manifest
  - `{orchestrator}` is `be` or `fe`
- Template: `.claude/skills/u-shared-templates/handoff-receipt.yaml`
- Schema: `.claude/skills/u-shared-templates/handoff-receipt.schema.yaml`
- One receipt per `(manifest_id, orchestrator)` pair — idempotent: re-reading the same manifest does NOT emit a new receipt

The receipt records: consumer identity, consumption timestamp, validated manifest sha256, and the decisions the orchestrator took (`domains_halted`, `task_contracts_reevaluated`, `task_contracts_proceeded`).

**Spec side:** before issuing a new handoff of type `fast_track` or `major_evolution` that targets a domain already delivered, the Spec Orchestrator SHOULD read the latest receipts for the previous manifest. If no receipt exists for the BE orchestrator (or FE, for frontend-bearing handoffs), log a warning — the previous handoff may not have been consumed.

---

## Detection by the Dev Orchestrator

The Dev Orchestrator detects specs automatically:

```
Check existence of {SPECS_DIR}/
  |
  +--> Exists with at least 1 domain whose .spec.md has status "approved"
  |      --> Activate "Spec-first" mode
  |
  +--> Does not exist or all in "draft"
         --> Feature/Improve/Error modes (current flow)
```

## Versioning at handoff

Each artifact consumed by Dev must be pinned to a version:

```markdown
## Consumed spec
| File | Version | Date |
|------|---------|------|
| auth.spec.md | 1.2.0 | 2026-03-21 |
| domains/auth/openapi.yaml | 1.2.0 | 2026-03-21 |
| domains/auth/back/auth.back.md | 1.0.0 | 2026-03-21 |
```

The Orchestrator-Dev records consumed versions in `log-orchestrator-dev.md`.

## Post-handoff change notification

### Spec side: register notification when updating a delivered spec

When the Spec Orchestrator updates a spec that has already been delivered to Dev (via CR, feedback, or fast-track):

1. **Append to the notification file:** create or append `{SPECS_DIR}/spec-changelog-notify.yaml` using the canonical template at `.claude/skills/u-shared-templates/spec-changelog-notify.yaml`:

   ```yaml
   layer: semi-permanent

   notifications:
     - id: NOTIFY-<YYYYMMDD-HHMMSS>
       notified_at: <ISO-8601>
       domain: <domain-name>
       version_from: <semver>
       version_to: <semver>
       change_type: patch | minor | major
       origin: cr | fast_track | triage
       cr: CR-NN | null
       changed_files: [<path>]
       summary: <one structured sentence>
       dev_impact: no_action | reevaluate_task_contracts | stop_domain_task_contracts
       processed_by: []
   ```

2. **Rules:**
   - Append-only: never remove or reorder existing entries — the file is history
   - Schema: `.claude/skills/u-shared-templates/spec-changelog-notify.schema.yaml`
   - This file is the **only** post-handoff Spec → Dev communication channel when no new `handoff-manifest.yaml` covers the same change
   - The `handoff-manifest.yaml` takes precedence when present — this file is the fallback for changes that do not warrant a full re-handoff

### Dev side: detect unprocessed notifications at session start

The Dev Orchestrator (BE or FE) reads `{SPECS_DIR}/spec-changelog-notify.yaml` at session start and filters for entries where `processed_by` has no element with `orchestrator=<self>`.

Decision table driven by `dev_impact`:

| `dev_impact` | Action |
|---|---|
| `no_action` | Log and continue |
| `reevaluate_task_contracts` | Reevaluate affected Task Contracts for the domain |
| `stop_domain_task_contracts` | Halt Task Contracts for the domain until reevaluated |

After acting on a notification, the Dev Orchestrator MUST append an entry to that notification's `processed_by[]`:

```yaml
processed_by:
  - orchestrator: u-be-orchestrator-core | u-fe-orchestrator-core
    processed_at: <ISO-8601>
    action_taken: no_action | reevaluated | halted
```

This is the source of truth for "has this Dev team seen this change?" — no log parsing, no free-form interpretation.

## Artifact mapping Spec -> Dev

| Spec Artifact | Identifiers | Consumed by Dev as |
|---------------|-------------|---------------------|
| UC-NN (.spec.md) | UC-01, UC-02... | Reference in Task Contracts ("Technical notes: UC-01") |
| BR-NN (.back.md) | BR-01, BR-02... | Reference in tests ("describe BR-01") |
| UI-NN (.feature.spec.md §2) | UI-01, UI-02... | Reference in feature tests and QA checklist |
| BDD-NN (.feature.spec.md §9) | scenarios | Feature invariants — QA primary verification criterion |
| FL-NN (.flow.md) | FL-01, FL-02... | Reference in navigation tests |
| DEC-NN (decisions.md) | DEC-01, DEC-02... | Orchestrator reads at session start; active decisions override SKILL defaults |
| error.code (error-codes.md) | BUSINESS_*, etc. | Direct use in code (error handlers) |
| Glossary (glossary.md) | terms | Use in Task Contract names, variables, messages |
