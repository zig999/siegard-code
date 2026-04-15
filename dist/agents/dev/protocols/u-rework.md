## Rework Protocol (feedback loop)

When QA rejects:

1. Separate bugs by severity:
   - **Critical / High** -> blocking; immediate correction cycle
   - **Medium** -> caveats; remain pending for a separate improvement Task Contract
   - **Low** -> recorded; no action

2. For Critical/High, classify:
   - **Technical bug** -> Developer with correction prompt (see below)
   - **UX issue** -> escalate to the human
   - **Spec divergence** (QA reported `SPEC-DIVERGENCE`) -> evaluate:
     - Necessary divergence (incomplete spec): open a CR using `.claude/skills/u-shared-templates/cr-template.yaml` → save as `{SESSIONS_DIR}/{SESSION}/cr-{id}.yaml` → notify human to decide whether to update spec via `/u-spec` before continuing
     - Accidental divergence (Developer error): Developer corrects to conform with spec

3. **Mount correction context for the Developer:**
   ```
   ## Mode: correction
   ## Target Task Contract: TC-XX — [Title]

   ## Bugs to fix (extracted from tc-XX-qa.md)
   [copy only the BUG-XX blocks with Critical/High severity]

   ## Original delivery
   [include complete tc-XX-delivery.md for reference]

   Fix only the listed bugs. Do not change approved behaviors.
   ```
   Skills: **always use short mode** — the agent has already processed this Task Contract in the original activation. Consult `.claude/agents/dev/protocols/u-context-mounting-short-mode.md`.

4. After correction -> reactivate QA with history:
   ```
   ## Mode: full
   ## Round: N (retest)
   ## Previous QA report (tc-XX-qa.md from round N-1)
   [include complete report so QA can verify if bugs were resolved]
   ## New delivery (updated tc-XX-delivery.md)
   ```

5. Record round: `In testing (round N)` in the log
6. On the 3rd round -> Task Contract changes to `Blocked — Escalation` (see orchestrator-core.md)
7. While waiting -> continue with other independent Task Contracts; record the block in the log

### Post-correction spec verification (Spec-first mode)

After Developer corrects and QA approves in a retest round:
- Check if the correction introduced an unregistered spec divergence
- If `tc-XX-delivery.md` `delivery-body.spec_divergences` has items: open a CR using `.claude/skills/u-shared-templates/cr-template.yaml` → save as `{SESSIONS_DIR}/{SESSION}/cr-{id}.yaml` → record in `spec-divergences.md` → notify human
- If no divergences: proceed normally
