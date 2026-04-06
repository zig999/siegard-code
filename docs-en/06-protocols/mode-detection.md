# Mode Detection Protocol

Determines the operating mode for each orchestrator based on available artifacts.

## Dev orchestrator modes

| Mode | Detection criteria |
|------|-------------------|
| **Spec-first** | `{SPECS_DIR}` exists with `status: approved` in `.spec.md` headers |
| **Improve** | `improve##.md` files exist in `{SESSIONS_DIR}/{SESSION}/` |
| **Bug** | `bug##.md` files exist in `{SESSIONS_DIR}/{SESSION}/` |
| **Bug+Improve** | Both `improve##.md` and `bug##.md` exist (bugs processed first) |
| **Error** | None of the above -- halts with guidance |

Mode detection works identically for all domain values (`backend`, `frontend`, `fullstack`). In fullstack mode, the Meta-Orchestrator detects the mode once and passes it to both domain orchestrators -- they do not re-detect.

## Spec orchestrator modes

| Mode | Detection criteria |
|------|-------------------|
| **New domain** | No `{SPECS_DIR}` directory exists |
| **Reverse-eng review** | `_meta/origin-reverse-spec.md` exists |
| **Merge review** | `merge-pending-review.md` exists |
| **New with structure** | `{SPECS_DIR}` exists but new domain requested |
| **Resume** | `log-orchestrator-spec.md` exists with incomplete stages |

## Evaluation order

The orchestrator evaluates conditions in a specific order (first match wins):
1. Check for resume indicators (incomplete log files)
2. Check for reverse-spec markers
3. Check for merge markers
4. Check for existing artifacts (specs, improve, bug files)
5. Default to new/error mode
