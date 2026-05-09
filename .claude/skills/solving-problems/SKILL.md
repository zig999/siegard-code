---
name: solving-problems
description: Use this skill whenever a request requires analysis, judgment, a recommendation, a diagnosis, a decision between alternatives, or any answer where being wrong has a real cost. Trigger on phrases like "should I", "what's the best", "help me decide", "why is X happening", "how do I solve", or any open-ended question with multiple plausible answers. Forces a structured path from request to best solution: triage complexity, frame the real problem, decompose, reason, generate competing hypotheses, stress-test, then verify before answering. Domain-agnostic.
---

# Solving Problems

Most weak answers do not come from missing knowledge. They come from skipped steps: treating symptoms as causes, locking onto the first plausible answer, ignoring alternatives, or asserting conclusions without checking them. This skill prevents those failures.

## Core rule

```
Do not deliver a recommendation until ALL three are true:
  1. The real problem is framed (not just the surface request).
  2. At least two competing solutions have been compared.
  3. The recommendation has been stress-tested and verified.
```

If any of the three is missing, the answer is a guess in formatting, not a solution.

## When to apply this skill

Apply when the request involves:
- A decision with trade-offs or multiple variables
- A diagnosis ("why is X happening?", "what's wrong with Y?")
- A recommendation between alternatives
- A strategy, plan, or risk assessment
- A dilemma, conflict, or judgment call
- Anything the user describes as "complex", "hard", or "stuck"

Apply **especially** when:
- The user phrases the request as a yes/no but the situation is multi-variable
- The user proposes their own solution embedded in the question (often hides the real problem)
- The user signals urgency (urgency is exactly when shortcut answers fail hardest)
- The first answer seems obvious

Do **not** apply when:
- The request is purely factual ("what is the capital of France")
- The task is mechanical execution ("translate this", "summarize this")
- The conversation is small talk

## The flow

```
[1] Triage  →  [2] Frame  →  [3] Decompose  →  [4] Reason  →
[5] Compete  →  [6] Attack  →  [7] Synthesize  →  [8] Verify  →  Deliver
```

Each step has an exit condition. Do not advance until it is met. Return to an earlier step if a later step exposes a flaw upstream.

---

## Step 1 — Triage

Classify the problem in one sentence before doing anything else. Depth scales to type.

| Type | Signals | Process depth |
|---|---|---|
| **Simple** | One variable, direct answer, low cost if wrong | Linear chain, one hypothesis, light verification |
| **Complicated** | Multi-variable but known method exists | Structured chain, two hypotheses, criterion check |
| **Complex** | Variables interact, no obvious method, high cost if wrong | Tree of options, three+ hypotheses, full stress-test |
| **Chaotic** | Facts shift mid-analysis, sources conflict | Stabilize first (which facts are reliable?), then re-triage |

**Decisive question:** "If this analysis is wrong, what's the cost?" Higher cost → higher depth.

**Exit:** Type named, depth chosen.

---

## Step 2 — Frame

Refine the question before answering it. The quality of the answer is bounded by the quality of the question.

**Do all of the following:**

1. **Restate the request in your own words.** Show the restatement to the user when the problem is Complicated or above. If they correct it, the original framing was wrong.

2. **Separate three layers explicitly:**
   - **Facts** — observed, stated, verified
   - **Inferences** — derived from facts (state the derivation chain)
   - **Assumptions** — taken for granted without verification

3. **Define success criteria.** How will we know the answer is good? Without this, any later answer can be retroactively justified.

4. **List hard constraints.** Time, resources, people, policies, values. These bound the solution space.

5. **State what is out of scope.** Explicitly exclude what will not be addressed here.

**Critical anti-pattern:** A request phrased as "how do I do X?" often hides the real problem. Ask "what would X solve?" before accepting X as the goal. If the answer reveals a different problem, frame *that* one.

**Exit:** Restatement, success criteria, constraints, scope all written. For Complex problems, get user confirmation before continuing.

---

## Step 3 — Decompose

Break the problem into parts that are **mutually exclusive and collectively exhaustive (MECE)**: no overlap, full coverage. Without this, analysis double-counts some dimensions and misses others entirely.

**Choose one decomposition axis:**

- **By dimension** — time, place, people, process, resource, money
- **By cause-effect** — what produces the outcome? each producer contributes how much?
- **By stakeholder** — who decides, who executes, who is affected, what each wants
- **By decision criterion** — which factors actually drive the choice

**MECE check:** If you summed the parts, would they reach 100% of the problem? Could anything important fall outside the decomposition? If yes to the second question, the decomposition is wrong — redo it.

For Complex problems, build a tree: each part may have sub-parts. Stop when leaf nodes are individually analyzable.

**Exit:** Parts cover the whole, do not overlap, and each part is more tractable than the whole.

---

## Step 4 — Reason: chain or tree

**Pick the reasoning mode based on path structure.**

### Chain (linear) — when the path is sequential

Use when each step logically depends on the previous one and there is no branching.

```
Premise → step 1 → step 2 → ... → conclusion
```

Write each step. Do not skip. If a step depends on something unverified, mark it `[ASSUMPTION]` inline.

### Tree (branching) — when there are real alternatives

Use when, at any point, multiple paths are plausible and it is not obvious which to take. For each branch:

1. **Generate alternatives.** Aim for three. Minimum two.
2. **Evaluate each branch** against explicit criteria (cost, feasibility, alignment with success criteria from Step 2).
3. **Prune or expand.** If a branch can be ruled out, record why. If not, expand it one level deeper.
4. **Backtrack is allowed.** If an expanded branch turns out worse than expected, abandon it and try another.

**Trigger for tree mode:** if you find yourself thinking "it depends on...", that is the branching point. Make the dependency explicit and explore both sides.

**Exit:** A traceable chain or a tree with branches evaluated, leading to one or more candidate solutions.

---

## Step 5 — Compete: generate rival hypotheses

**A hypothesis is not tested in isolation. It is tested against rivals.**

For the leading candidate solution, generate at least **two genuine alternative hypotheses** that could explain the same facts or solve the same problem differently.

For each hypothesis:

1. **State it specifically.** "Hypothesis N: [precise claim]"
2. **List supporting evidence.**
3. **List contradicting evidence.**
4. **State the falsifier.** "This hypothesis is wrong if we observe [specific evidence]."
5. **Rate confidence:** high / medium / low, with the reason.

**Self-trap question:** "What would have to be true for my preferred answer to be wrong?" If you cannot answer, it is not a hypothesis — it is a belief.

**Anti-pattern to refuse:** presenting a deliberately weak rival hypothesis to look balanced. If the alternative is obviously inferior, it is not a real alternative. Force a rival that an intelligent, well-informed person would actually defend.

**Exit:** Two or more hypotheses compared on equal footing. The differentiator (the evidence that picks one over the others) is identified.

---

## Step 6 — Attack: pre-mortem the candidate

Before declaring a solution, attack it.

1. **Apply the success criteria** (from Step 2) to the candidate. Does it meet all of them? Which only partially?

2. **Pre-mortem.** Imagine it is six months later and the recommendation failed badly. Write the failure story. The three most plausible causes of that imagined failure are the real risks.

3. **Asymmetric error costs.** If the recommendation is acted on and turns out wrong, what's the cost? If it is rejected and turns out right, what's lost? These are usually not symmetric, and the asymmetry should bend the recommendation toward the lower-cost error.

4. **Ignored stakeholders.** Who is affected by this solution and was not considered? Do they have practical vetoes that block execution?

5. **Reversibility.** If the solution does not work, can it be undone? At what cost? Irreversible solutions demand higher confidence.

**Exit:** The candidate survives the attack, OR the attack reveals adjustments that make it more robust. Apply those adjustments before continuing.

---

## Step 7 — Synthesize: write the answer

Use this exact structure unless the user requested a different format:

1. **Recommendation.** One or two sentences. Direct.
2. **Why.** Core reasoning. Do not reproduce the entire process — surface the load-bearing logic.
3. **Conditions.** Critical assumptions. State that the recommendation changes if these change.
4. **Alternatives considered.** Name them and state why each was not chosen.
5. **Residual risks.** What could still go wrong, with mitigation if available.
6. **What to monitor.** Observable signals that the solution is or is not working.

**Calibrated language is required.** Match expressed confidence to actual evidence:

- High evidence → "X is the case", "evidence shows", "this will"
- Moderate evidence → "X is likely because Y", "evidence indicates", "this should"
- Weak or contested evidence → "X is plausible but depends on Y", "this might if"
- Genuinely unknown → say "I don't know" and state what would resolve it

Confident wording over weak evidence is the worst output: it misleads without warning.

---

## Step 8 — Verify before delivery

Run this gate immediately before sending the answer. Do not skip.

```
1. ANSWER: Does the response address the framed problem from Step 2?
2. CRITERIA: Is each success criterion explicitly addressed?
3. CONSISTENCY: Does any part of the synthesis contradict another?
4. ASSUMPTIONS: Are critical assumptions stated where the user can see them?
5. CALIBRATION: Does expressed confidence match actual evidence?
```

If any check fails, do not deliver. Return to the relevant step.

**Stop signals — if any of these is true, do not deliver yet:**

- Hedge words ("should", "probably", "seems") appear without a stated reason
- Steps 5 and 6 were not actually run
- The thought "good enough" appeared on a problem triaged as Complex
- You cannot articulate what evidence would change the conclusion

---

## Common rationalizations and the truth

| Rationalization | Truth |
|---|---|
| "This problem is simple, skip steps." | Step 1 already accounts for that. If simple, the flow is fast — but Step 1 is not skipped. |
| "I already know the answer, just formalize it." | Knowing the answer before analysis is *exactly* when rival hypotheses are needed. |
| "The user is in a hurry." | A fast wrong answer costs more total time than a slightly slower right one. |
| "The rival hypothesis is weak — skip it." | If it is weak, find a stronger one. No real rival means no real comparison. |
| "Pre-mortem is overkill." | It takes thirty seconds. The cost of skipping it equals every preventable failure. |
| "Verification is redundant." | Verification is the only step that separates "my answer" from "the right answer." |
| "Calibrated language sounds uncertain." | False confidence misleads. Calibrated language is honest, and users prefer it once they notice the difference. |

---

## Signals that a step was skipped

When the user says any of these, a specific step was skipped. Do not defend the prior answer — reopen the named step.

| User signal | Step to revisit |
|---|---|
| "That's not what I asked" | Step 2 (framing) |
| "What about [factor I didn't consider]?" | Step 3 (decomposition was not MECE) |
| "Why didn't you consider X?" | Step 5 (rival hypotheses insufficient) |
| "How do you know it will work?" | Step 8 (verification absent) |
| "But what if [scenario]?" | Step 6 (pre-mortem incomplete) |
| "You contradicted yourself" | Step 8 check 3 (consistency) failed |

---

## Worked example

**Request:** "Should I take the offer from Company Y?"

**Step 1 — Triage:** Complex. Multi-variable, high cost if wrong. → Tree mode, three hypotheses, full stress-test.

**Step 2 — Frame:** Restated as "Which career move in the next six months best serves the user's long-term goals?" The original phrasing embedded a binary (accept/reject) that hides the real decision. Success criteria to confirm with user: growth, compensation, alignment with goals, life quality. Constraints: timeline of the offer, current obligations.

**Step 3 — Decompose (MECE):** Financial, professional development, lifestyle, risk, external option (do nothing / look further).

**Step 4 — Reason (Tree):** Branching at "professional development" — grow internally vs. grow externally.

**Step 5 — Compete:**
- H1: Accept the offer (evidence: higher pay, new challenge)
- H2: Stay and renegotiate internally (evidence: established network, low transition cost)
- H3: Decline both, search wider (evidence: neither option meets all stated criteria)

**Step 6 — Attack:** Pre-mortem of accepting: most plausible failure is cultural mismatch — uninvestigated. Mitigation: speak to two former employees before deciding. This adjustment is added before delivery.

**Step 7 — Synthesize:** Calibrated recommendation with assumptions and monitoring signals.

**Step 8 — Verify:** Each success criterion addressed? Assumptions visible? Confidence calibrated? Yes → deliver.

---

## Bottom line

Frame the question. Decompose it. Generate rival hypotheses. Attack the candidate. Verify. **Then deliver.**

This is the difference between analysis and a guess in nice formatting.