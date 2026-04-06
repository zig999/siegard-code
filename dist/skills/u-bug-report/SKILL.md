---
name: u-bug-report
description: Interactive skill that collects one or more bug reports through a guided questionnaire with multiple-choice options and generates bug##.md files in `{SESSIONS_DIR}/{SESSION}/`. Invoked via the /u-bug-report command.
user-invocable: true
---

# SKILL: Bug Report

## Purpose
Guide the human through a structured questionnaire to capture bugs in a complete and standardized way. Supports multiple bugs per session. Each bug is saved as an individual `bug##.md` file in `{SESSIONS_DIR}/{SESSION}`, ready for the dev team to fix via `/u-dev`.

---

## Behavior rules

- **Always ask the human for the desired `{SESSIONS_DIR}/{SESSION}` before any other action** — never assume, infer, or choose a directory on your own. This must be the **first question** in the flow.
- Ask **one question at a time** — never group questions
- Prefer **single-choice numbered questions** — the human responds with the number
- Use open-ended questions only when predefined options cannot cover the answer space
- Before starting, check if `bug*.md` files already exist in `{SESSIONS_DIR}/{SESSION}`:
  - If they exist: identify the highest existing number (e.g., `bug03.md` -> next will be `bug04.md`) and ask whether to **add new bugs** starting from the next number or **recreate from scratch** (deleting existing ones with confirmation)
  - If they don't exist: start the flow normally from `bug01.md`
- At the end of each bug, display the **collected bug summary** and ask if it is correct before proceeding
- If the human answers "I don't know" or "I don't remember", record it as `Warning - To confirm:` — do not block the flow
- After each confirmed bug, ask if there are more bugs to report before generating the file

---

## Question flow — per bug

### BLOCK 1 — Identification

**Q1.1 — Bug title**
```
Describe the bug in a short sentence.
(E.g., "Save button does not respond on the address form")

[open-ended]
```

**Q1.2 — Where does it occur?**
```
In which area of the system does the bug appear?

[open-ended — identify the screen, component, or specific flow]
```

**Q1.3 — Bug type**
```
How would you classify this bug?

1. Visual/UI fix — layout, color, spacing, wrong text
2. Incorrect behavior — logic, flow, validation
3. Integration error — API, contract, inconsistent data
4. I don't know
```

---

### BLOCK 2 — Reproduction

**Q2.1 — How to reproduce?**
```
Describe the steps to reproduce the bug.
(E.g., "1. Go to /checkout  2. Fill in address  3. Click Save")

[open-ended — list the steps numbered]
```

### BLOCK 3 — Behavior

**Q3.1 — What was expected?**
```
Describe the correct expected behavior.
(E.g., "The form should save and redirect to the confirmation screen")

[open-ended]
```

**Q3.2 — What actually happens?**
```
Describe the current incorrect behavior.
(E.g., "Nothing happens when clicking — no feedback, no redirect")

[open-ended]
```

**Q3.3 — Error message**
```
Did any error message appear? If yes, paste it here (screen or console).
If not, say "no".

[open-ended]
```

### BLOCK 5 — Bug confirmation

At the end of each bug, display the summary before recording:

```
## Bug #N — Summary

**Title:** [title]
**Where:** [screen/component]
**Type:** [visual/UI fix | incorrect behavior | integration error | I don't know]
**Steps:** [numbered list]
**Expected:** [correct behavior]
**Actual:** [incorrect behavior]
**Error:** [message or "none"]

Is this bug correct?

1. Yes — record and continue
2. I want to correct something — [indicate what]
```

---

### BLOCK 6 — More bugs?

After confirming each bug:

```
Are there more bugs to report?

1. Yes — next bug
2. No — save the files now
```

---

## Generated bug##.md template

Each bug is saved as an individual file in `{SESSIONS_DIR}/{SESSION}` named `bug##.md` (e.g., `bug01.md`, `bug02.md`, etc.).

```markdown
# Bug #NN — [Title]

_Generated on: YYYY-MM-DD_
_Via: skill-bug-report (guided questionnaire)_

---

**Where:** [screen or component]
**Type:** [visual/UI fix | incorrect behavior | integration error | I don't know]

## How to reproduce
1. [step 1]
2. [step 2]
3. [step 3]

## Expected behavior
[description]

## Actual behavior
[description]

## Error message
[message text, log excerpt, or "None"]

## Open questions
[List of Warning - To confirm: unanswered items, or "None"]
```

> The file `.claude/skills/u-bug-report/bug.template.md` is the human reference for this template — it does not need to be read at runtime.

---

## File generation rules

- Save each bug in `{SESSIONS_DIR}/{SESSION}/bug##.md` (two-digit numbering: `bug01.md`, `bug02.md`, etc.)
- Numbering is sequential and continuous — if `bug01.md` and `bug02.md` already exist, the next will be `bug03.md`
- Never overwrite existing files without confirming with the human
- After saving all bugs, display a consolidated summary:
  - Total bugs recorded in the session
  - List of created files
- After the summary, display the next step flow:

**If all bugs are of type "visual/UI fix":**
```
Run: /u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION]
```
> The Dev Orchestrator will detect `type: visual/UI fix` and use the **lean pipeline** — no Planner, no TDD, direct fix.

**If there are bugs of type "incorrect behavior" or "integration error":**
```
Do any of these bugs reveal behavior not covered in API contracts
or existing specifications?

1. Yes — update specs before fixing
2. No — fix directly in code
3. I don't know — the Dev Orchestrator will evaluate
```

If **1**: `Run: /u-spec [SPECS_DIR] [SESSION]` (describe the bug as reverse feedback)
If **2** or **3**: `Run: /u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION]`

> **Note:** `/u-dev` automatically detects `bug##.md` and operates in **bug mode**. The bug's `type:` determines whether it uses the lean pipeline (visual/UI) or the full pipeline (logic/contract).

> **Important:** `/u-dev` requires the field `domain: frontend` or `domain: backend` in `CLAUDE.md`. Verify that the field exists before guiding the next step. If it does not exist, alert the human: "The `CLAUDE.md` file must contain the field `domain: frontend` or `domain: backend` before running `/u-dev`."
