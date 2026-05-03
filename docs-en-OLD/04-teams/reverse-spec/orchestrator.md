# Reverse Spec Orchestrator

Coordinates the reverse engineering pipeline from code analysis to spec generation.

## Responsibilities

- Detect operating mode (Detection or Merge)
- Validate that CODE_DIR contains source code
- Activate Analyzer and Writer sequentially
- Validate generated artifacts (every domain must have `openapi.yaml`)
- Create origin marker for `/u-spec` detection
- Track state in `log-reverse-spec.md`

## Execution flow

```
1. Stack detection (auto-detect from code)
2. Activate Analyzer (produces analysis-report.md)
3. Activate Writer (generates spec artifacts)
4. Artifact validation gate
   - If missing artifacts: re-generation attempt (max 2 per domain)
5. Create origin marker (_meta/origin-reverse-spec.md)
6. If Merge mode: execute merge protocol
7. Log completion and display summary
```

## Artifact validation gate

After the Writer completes, the orchestrator verifies:
- Every identified domain has an `openapi.yaml`
- Every domain has a `.spec.md`
- Every domain has a `.back.md`

If artifacts are missing, the Writer is reactivated for that specific domain (max 2 attempts).

## Output

- `{SPECS_DIR}/log-reverse-spec.md` -- Execution log with code analysis results, spec generation status, and merge results (if applicable)
- `{SPECS_DIR}/_meta/origin-reverse-spec.md` -- Origin marker that tells `/u-spec` these are draft specs needing review
