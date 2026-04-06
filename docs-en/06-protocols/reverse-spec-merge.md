# Reverse Spec Merge Protocol

Merge strategy when reverse-engineering specs for a project that already has existing specifications.

## Core principles

- **Never remove existing content** -- Only add or flag divergences
- **Divergences are signaled, not overwritten** -- Human decides resolution
- **Creates review artifact** -- `merge-pending-review.md` for human review

## How it works

1. Reverse Spec Writer generates new specs from code analysis
2. System compares generated specs with existing specs
3. Additions are merged automatically
4. Divergences are flagged in `merge-pending-review.md`
5. Human reviews divergences and decides resolution

## merge-pending-review.md

Contains:
- List of divergences between generated and existing specs
- For each: what the code says vs what the spec says
- Suggested resolution
- Human decision field

## Mode trigger

When `/u-spec` detects `merge-pending-review.md`, it enters **Merge review** mode for human-guided resolution.

## Recovery

If a merge produces incorrect results:
- Run `/u-spec` in Merge review mode to fix specific issues
- Or use `git checkout -- {SPECS_DIR}` to restore the previous state
