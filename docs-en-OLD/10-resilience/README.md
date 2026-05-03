# Resilience

Failure scenarios, recovery strategies, and system limits.

## Failure scenarios

### 1. Spec Reviewer rejects repeatedly

**What happens:**
- Rounds 1-2: Writer auto-corrects based on rejection feedback
- Round 3: Escalation to human with all 3 rejection reports

**Recovery:**
- Read the rejection reports to understand recurring issues
- Correct the spec manually or provide more detailed requirements
- Run `/u-spec` to resume

**Prevention:** Provide detailed, unambiguous requirements upfront.

---

### 2. QA rejects Task Contract repeatedly

**What happens:**
- Rounds 1-2: Developer auto-corrects in short mode
- Round 3: Task Contract blocked, escalated to human

**Recovery:**
- Review QA diagnostics and Developer's attempts
- Reformulate `validation.criteria` or reduce Task Contract scope
- Resume with `/u-dev`

**Prevention:** Write clear, objective `validation.criteria` in the `execution_contract`.

---

### 3. Spec Validator returns 20+ errors

**Do NOT** correct all at once (token overflow risk).

**Do:** Use `/u-spec-triage` to fix 5-10 errors per session. Repeat until resolved.

---

### 4. Token overflow

**Symptoms:** Incomplete output, ignored instructions, truncated responses.

**Common causes:**
- 10+ domains in one spec session
- Huge analysis report from reverse spec
- 20+ Task Contracts in one dev session

**Recovery:** Divide into smaller sessions (1 domain or 1 Epic at a time).

**Prevention:** Use `/u-spec-triage` for incremental processing. Use short mode for reactivations.

---

### 5. Session interrupted

**Preserved:** Files on disk, orchestrator logs, backlog status.

**Lost:** In-memory context, conversational state.

**Recovery:** Run the same command again -- the orchestrator detects the incomplete log and resumes from the last completed step.

**Limitation:** Verify that no file was left in a partial (half-written) state before resuming.

---

### 6. Spec-code divergence (reverse feedback)

**When:** Developer finds the spec is wrong or infeasible during implementation.

**Recovery:**
- Developer generates `feedback-NN.md`
- Run `/u-spec` for Writer to classify and correct

**Alternative:** Register as accepted divergence in `spec-divergences.md`.

---

### 7. Reverse spec merge corrupts specs

**Protections:** Merge never removes existing content; divergences are only flagged.

**Recovery:**
- Run `/u-spec` in Merge review mode to fix specific issues
- Or restore with `git checkout -- {SPECS_DIR}`

---

## System limits

| Limit | Value | Consequence |
|-------|-------|-------------|
| Reviewer rejection cycles | Max 3 | Escalation to human |
| QA rework rounds | Max 3 | Task Contract blocked |
| Parallel Task Contracts | Max 3 | Queue for remaining |
| Spec domains WIP | Max 3 | Queue for remaining |
| Triage validation cycles | Max 2 per agent | Escalation to human |
| Analysis report size | ~300 lines | Use Executive Summary for larger |
