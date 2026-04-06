# Action Guide

"I want to do X" -> Here's the command sequence.

## Features

| I want to... | Commands |
|--------------|----------|
| Build a complete feature (FE or BE) | `/u-spec` -> `/u-dev` |
| Implement from existing specs | `/u-dev` |
| Add a new domain | `/u-spec` |
| Make a breaking change | `/u-spec` (describe the change) |
| Make a minor adjustment | `/u-spec` (fast-track auto-detected) |
| Document existing code as specs | `/u-reverse-spec` |
| Review generated specs | `/u-spec` (enters review mode) |
| Fix all validation errors | `/u-spec` |
| Fix errors incrementally | `/u-spec-triage` -> repeat |

## Bugs

| I want to... | Commands |
|--------------|----------|
| Document a bug | `/u-bug-report` |
| Fix a code-only bug | `/u-bug-report` -> `/u-dev` |
| Fix a bug with spec gap | `/u-bug-report` -> `/u-spec` -> `/u-dev` |

## Improvements

| I want to... | Commands |
|--------------|----------|
| Document an improvement | `/u-improve` |
| Simple improvement | `/u-improve` -> `/u-dev` |
| Improvement affecting API | `/u-improve` -> `/u-spec` -> `/u-dev` |
| Visual improvement (FE) | `/u-improve` -> `/u-spec` -> `/u-dev` |

## Feedback

| I want to... | Commands |
|--------------|----------|
| Report a spec problem found during dev | `/u-spec` (describe as reverse feedback) |

## Combined

| I want to... | Commands |
|--------------|----------|
| Fix bugs AND add improvements | `/u-bug-report` + `/u-improve` -> `/u-dev` (bugs first) |
