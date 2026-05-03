# /u-spec-triage -- Specification Triage Command

Incrementally selects and fixes spec validation errors to avoid token overflow.

## Usage

```
/u-spec-triage [SPECS_DIR] [SESSION]
```

## Why triage?

When the Spec Validator returns 20+ errors, correcting them all at once risks token overflow and degraded output quality. Triage selects a manageable batch per session.

## How it works

1. **Load reports** -- Reads persisted validation reports from `{SPECS_DIR}/_validation/`
2. **Staleness check** -- Warns if specs were modified after the validation report was generated
3. **Present errors** -- Displays all errors grouped by domain and severity
4. **Human selects** -- User chooses which errors to fix (recommended: 5-10 per session)
5. **Agents correct** -- Appropriate spec agents are activated to fix selected errors
6. **Revalidate** -- Validator runs again on corrected artifacts

## Recommended batch size

- **5-10 errors per session** -- Balances thoroughness with token efficiency
- Repeat triage sessions until all errors are resolved
- Max 2 invalidation cycles per agent before escalation to human

## Flow

```
/u-spec-triage -> select errors -> agents fix -> revalidate -> repeat if needed
```
