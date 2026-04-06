# Reverse Spec + Triage Flow

Document an existing project and incrementally evolve its specifications.

## When to use

- Existing project without formal specifications
- Legacy codebase needing documentation before refactoring
- Onboarding scenario where specs need to be created from code

## Command sequence

```
/u-reverse-spec -> /u-spec -> /u-spec-triage (repeat) -> /u-dev
```

## Step-by-step

### Phase 1: Reverse engineering (`/u-reverse-spec`)
1. Point to the source code directory
2. Analyzer scans code and produces analysis report
3. Writer generates draft specifications
4. All artifacts marked as `draft`

### Phase 2: Formal review (`/u-spec`)
1. Orchestrator detects reverse-eng review mode (via `origin-reverse-spec.md`)
2. Writer reviews and polishes draft specs
3. Reviewer approves or requests changes
4. Validator checks cross-reference consistency

### Phase 3: Incremental triage (`/u-spec-triage`)
If the Validator returns many errors (20+):
1. Run `/u-spec-triage` to select 5-10 errors per session
2. Agents fix the selected errors
3. Validator re-checks
4. Repeat until all errors resolved

### Phase 4: Development (`/u-dev`)
Once specs are fully approved, proceed with normal development flow.
