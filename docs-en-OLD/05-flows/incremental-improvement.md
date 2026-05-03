# Incremental Improvement Flow

Small improvements to existing functionality without requiring a complete specification redesign.

## When to use

- Minor enhancements to existing features
- UI adjustments
- Performance improvements
- Small additions that don't change the API contract

## Command sequence

### Implementation-only improvement
```
/u-improve {SPECS_DIR} {SESSION} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
```

### Improvement that affects the API
```
/u-improve {SPECS_DIR} {SESSION} -> /u-spec {SPECS_DIR} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
```

## Step-by-step

1. Run `/u-improve` -- Answer the 3-question questionnaire
2. The command generates `improve##.md` and suggests next steps
3. If the improvement affects the API contract:
   - Run `/u-spec` to update specifications first
4. Run `/u-dev` -- The orchestrator detects Improve mode
5. Planner generates Task Contracts from `improve##.md`
6. Developer implements with simplified pipeline
7. QA validates
8. After QA approval, orchestrator evaluates if specs need updating (post-Task Contract spec evaluation)
