# Handoff Protocol

Formal artifact transfer from the Spec team to the Dev team.

## When triggered

- Spec Validator produces a VALID final report
- Auto-detected when `{SPECS_DIR}` with approved status is present in the directory

## What is packaged

The handoff bundles all artifacts the Dev team needs:

- `_global/conventions.md`
- `_global/error-codes.md`
- `openapi.yaml` per domain
- `{domain}.spec.md` per domain
- `{domain}.back.md` per domain (backend)
- `front.md` + screens + flows (frontend)
- Validator's compliance report
- Pinned spec version

## Spec version pinning

The handoff includes the exact spec version used. If specs change after the handoff (e.g., during development), the system generates a `spec-changelog-notify.md` to inform the Dev team of changes.

## Post-handoff spec changes

If specs are modified after delivery to the Dev team:
1. System detects the change
2. Generates `spec-changelog-notify.md` with the delta
3. Dev orchestrator presents the change notification
4. Human decides whether to continue, adjust, or restart affected Stories
