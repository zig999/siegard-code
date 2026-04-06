---
name: u-improve
description: Interactive skill that collects small improvement requests through a quick 3-question flow and generates improve##.md files in `{SESSIONS_DIR}/{SESSION}/`. Invoked via the /u-improve command.
user-invocable: true
---

# SKILL: Improve

## Purpose
Capture small improvements quickly and objectively. Supports multiple improvements per session. Each improvement is saved as an individual `improve##.md` file in `{SESSIONS_DIR}/{SESSION}`, ready for the dev team to implement via `/u-dev`.

---

## Behavior rules

- **Always ask the human for the desired `{SESSIONS_DIR}/{SESSION}` before any other action** — never assume, infer, or choose a directory on your own. This must be the **first question** in the flow.
- Ask **one question at a time** — never group questions
- Before starting, check if `improve*.md` files already exist in `{SESSIONS_DIR}/{SESSION}`:
  - If they exist: identify the highest existing number (e.g., `improve03.md` -> next will be `improve04.md`) and ask whether to **add new improvements** starting from the next number or **recreate from scratch** (deleting existing ones with confirmation)
  - If they don’t exist: start the flow normally from `improve01.md`
- At the end of each improvement, display the **summary** and ask if it is correct before proceeding
- If the human answers "I don’t know", record it as `Warning - To confirm:` — do not block the flow
- After each confirmed improvement, ask if there are more improvements to register

---

## Question flow — per improvement

**Q1 — What to improve?**
```
Describe the improvement in a short sentence.
(E.g., "Add tooltip to the export button")

[open-ended]
```

**Q2 — Where?**
```
On which screen, component, or area of the system?

[open-ended]
```

**Q3 — How should it work?**
```
Describe the desired behavior after the improvement.
(E.g., "On mouse hover over the button, display 'Export report as PDF'")

[open-ended]
```

### Confirmation

At the end of each improvement, display the summary before recording:

```
## Improve #N — Summary

**What:** [description]
**Where:** [screen/component]
**How it should work:** [desired behavior]

Is this improvement correct?

1. Yes — record and continue
2. I want to correct something — [indicate what]
```

---

### More improvements?

After confirming each improvement:

```
Are there more improvements to register?

1. Yes — next improvement
2. No — save the files now
```

---

## Generated improve##.md template

Each improvement is saved as an individual file in `{SESSIONS_DIR}/{SESSION}` named `improve##.md` (e.g., `improve01.md`, `improve02.md`, etc.).

```markdown
# Improve #NN — [Short description]

_Generated on: YYYY-MM-DD_
_Via: skill-improve (guided questionnaire)_

---

**Where:** [screen or component]

## Desired behavior
[description of how it should work after the improvement]

## Open questions
[List of Warning - To confirm: unanswered items, or "None"]
```

---

## File generation rules

- Save each improvement in `{SESSIONS_DIR}/{SESSION}/improve##.md` (two-digit numbering: `improve01.md`, `improve02.md`, etc.)
- Numbering is sequential and continuous — if `improve01.md` and `improve02.md` already exist, the next will be `improve03.md`
- Never overwrite existing files without confirming with the human
- After saving all improvements, display a consolidated summary:
  - Total improvements recorded in the session
  - List of created files
- After the summary, execute the **next step flow** described below

---

## Next step flow

After all improvements are confirmed and saved, ask:

```
Do any of these improvements involve:

1. Significant visual changes (layout, screen flow, new interaction)
   -> Go through the UX Team before development
2. Changes to API contracts, endpoints, or business rules
   -> Go through the Spec Team before development
3. Internal adjustments only (no visual or API impact)
   -> Go straight to development
4. I don't know — decide later
```

### If **1 (Visual changes)** or **2 (API/contract changes)**:
```
Next steps:
1. /u-spec [SPECS_DIR] [SESSION] — update the technical specifications (fast-track for minor changes)
2. /u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION] — run development with updated specs

Run: /u-spec [SPECS_DIR] [SESSION]
```

### If **3 (Internal adjustments)** or **4 (I don’t know)**:
```
Next step:
/u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION] — the Planner will generate the backlog directly from the improvements

Run: /u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION]
```

> **Note:** `/u-dev` automatically detects the presence of `improve##.md` and operates in **improve mode**.

> **Important:** `/u-dev` requires the field `domain: frontend`, `domain: backend`, or `domain: fullstack` in `CLAUDE.md`. Verify that the field exists before guiding the next step. If it does not exist, alert the human: "The `CLAUDE.md` file must contain the field `domain: frontend`, `domain: backend`, or `domain: fullstack` before running `/u-dev`."
