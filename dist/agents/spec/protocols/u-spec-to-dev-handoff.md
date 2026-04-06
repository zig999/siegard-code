# Protocol: Handoff Spec -> Dev

## Purpose
Define how the Spec group delivers approved artifacts to the Dev group, ensuring the transition is traceable, versioned, and without information loss.

## Preconditions for handoff

Before delivering, the Spec Orchestrator must verify:
- [ ] All domains in the requirement have `VALID` status from the Spec Validator
- [ ] All `error.code` are registered in the global catalog
- [ ] Changelog updated in all files
- [ ] Cross-domain dependencies verified (bidirectional, no drafts)
- [ ] If `{SPECS_DIR}/_validation/{domain}-validation.md` exists, status must be `VALID` or Triage `COMPLETED`

## Delivery package

### For the backend Dev Team

| File | Path | Consumed by |
|------|------|-------------|
| OpenAPI contract | `{SPECS_DIR}/domains/{domain}/openapi.yaml` | Developer (via context-mounting) |
| Business spec | `{SPECS_DIR}/domains/{domain}/{domain}.spec.md` | Planner (UCs -> Stories) |
| Back-end spec | `{SPECS_DIR}/domains/{domain}/back/{domain}.back.md` | Developer (BRs, STs, EVs, model) |
| Error codes | `{SPECS_DIR}/_global/error-codes.md` | Developer (error handlers) |
| Glossary | `{SPECS_DIR}/_global/glossary.md` | Planner (terminology) |
| Validator report | (inline in log) | Reference |

### For the frontend Dev Team

| File | Path | Consumed by |
|------|------|-------------|
| OpenAPI contract | `{SPECS_DIR}/domains/{domain}/openapi.yaml` | Developer (consumed endpoints — one per domain) |
| Business spec | `{SPECS_DIR}/domains/{domain}/{domain}.spec.md` | Planner (UCs -> Stories — one per domain) |
| Global frontend spec | `{SPECS_DIR}/front/front.md` | Developer (stack, state, routing, patterns) |
| Screen specs | `{SPECS_DIR}/front/screens/{screen}.screen.md` | UI Agent (mandatory base per screen) |
| Flow specs | `{SPECS_DIR}/front/_flows/{flow}.flow.md` | UI Agent + Planner (navigation flows) |
| Error codes | `{SPECS_DIR}/_global/error-codes.md` | Developer + UI Agent |
| Glossary | `{SPECS_DIR}/_global/glossary.md` | Planner (terminology) |

> **Note:** a screen may consume endpoints from multiple domains. The Dev Team must load the `openapi.yaml` from ALL domains referenced in the "Consumed Domains" section of each screen.

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

1. **Register in the notification file:** create or update `{SPECS_DIR}/spec-changelog-notify.md`:
   ```markdown
   # Spec Change Notifications

   ## [{date}] — {domain} v{previous-version} -> v{new-version}
   **Type:** patch | minor | major
   **CR:** CR-NN (or "fast-track" or "triage")
   **Origin:** CR-NN | fast-track | triage (items #{list})
   **Changed files:** {list}
   **Summary:** {1 sentence}
   **Impact on Dev:**
   - patch: no action needed
   - minor: reevaluate Stories for the domain
   - major: STOP Stories for the domain until reevaluation
   ```

2. **Rule:** this file is the only form of Spec -> Dev post-handoff communication. The Spec Orchestrator MUST update it whenever a delivered spec changes.

### Dev side: detect changes when starting a session

When the Spec Team updates a spec that has already been delivered:

1. **Patch:** Dev can ignore (does not affect implementation)
2. **Minor:** Dev must reevaluate affected Stories — new endpoint or UC may generate an additional Story
3. **Major:** Dev must STOP Stories for the affected domain until reevaluating impact

### How Dev detects changes

When starting a `/u-dev` session, the Orchestrator-Dev must:

1. Check if `{SPECS_DIR}/spec-changelog-notify.md` exists
2. If it exists, check for unprocessed notifications (compare with log)
3. Additionally, compare versions in the log vs current versions of files in `specs/`
4. If there is a difference by any mechanism:
   ```
   Spec update detected:
   | File | Version in log | Current version | Type | Impact |
   |------|---------------|----------------|------|--------|
   | auth.spec.md | 1.0.0 | 1.1.0 | minor | Reevaluate Stories |

   Recommended action: reevaluate Stories for the auth domain.
   Confirm? [Y / N]
   ```
5. Record in log: "Spec change detected: {domain} v{old} -> v{new} — {action taken}"

## Artifact mapping Spec -> Dev

| Spec Artifact | Identifiers | Consumed by Dev as |
|---------------|-------------|---------------------|
| UC-NN (.spec.md) | UC-01, UC-02... | Reference in Stories ("Technical notes: UC-01") |
| BR-NN (.back.md) | BR-01, BR-02... | Reference in tests ("describe BR-01") |
| UI-NN (.screen.md) | UI-01, UI-02... | Reference in screen tests and QA checklist |
| FL-NN (.flow.md) | FL-01, FL-02... | Reference in navigation tests |
| error.code (error-codes.md) | BUSINESS_*, etc. | Direct use in code (error handlers) |
| Glossary (glossary.md) | terms | Use in Story names, variables, messages |
