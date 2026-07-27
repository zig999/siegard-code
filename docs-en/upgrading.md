# Upgrading Siegard in a target project

Installation is a manual copy of `dist/.claude/` into `<target>/.claude/`. There is no installer,
which means there is **no merge step** — a copy overwrites. That is fine for a first install and
dangerous for an upgrade, because by then the target may hold local changes.

This document is the procedure that makes an upgrade non-destructive. It exists because the failure
it prevents already happened.

---

## What went wrong once

A target project running v2.26.0 reported `verify_install.py` → `{"status": "modified", "modified": 2}`.
The two files told different stories:

| File | What had happened |
|---|---|
| `skills/phase-review-rules/scripts/check_documentation_verified.py` | The target held a **newer** version than the framework: it had hand-ported fix F7 (revision supersession), which had been applied to a sibling gate in v2.6.0 and never propagated here. A plain copy would have silently reverted a real fix and reinstated a spurious-`E08` bug. |
| `skills/u-spec-globals/error-codes.md` | The target had added its own error codes — reasonably, since every spec agent was told this file was "the global error catalog". But it is a framework file under manifest integrity, so it can never verify clean and an upgrade destroys the additions. |

Both are now addressed upstream (the F7 helpers are shared, and the base catalog carries a header
saying where project codes belong), but the class of problem is permanent: any target can diverge,
and only the target knows why.

---

## The procedure

### 1. Before copying anything — check what diverged

Run this **in the target project**, against the version currently installed:

```bash
python3 .claude/scripts/verify_install.py
```

| Result | Meaning |
|---|---|
| `{"status": "ok"}` | Nothing diverged. Copy freely; go to step 3. |
| `{"status": "modified", ...}` | One or more files differ from the manifest. **Do not copy yet** — go to step 2. |
| `{"status": "missing", ...}` | Files the manifest expects are absent. Usually a partial copy; the upgrade will fix it, but note which. |

### 2. Resolve every `modified` file explicitly

For each path in `findings`, decide which of these it is — and record the decision somewhere durable
(a commit message is ideal, since the copy itself leaves no trace):

```bash
diff <path-to-new-dist>/.claude/<path> .claude/<path>
```

| Case | What to do |
|---|---|
| **The target is ahead** — a local fix the framework lacks | Do **not** discard it. Port the fix upstream first (open an issue / PR against the framework), then upgrade. If you must upgrade now, save the file and re-apply after copying, and keep a note of it — an unrecorded local fix is lost at the next upgrade too. |
| **The framework is ahead** — the local edit is stale or superseded | Let the copy overwrite. Verify the behaviour you cared about is still present. |
| **A project extension** — codes, config, project-specific content added to a framework file | Move the content to the project-owned file for that concern (for error codes: `{SPECS_DIR}/_global/error-codes.md`) **before** upgrading. Framework files carry a header naming their project-owned counterpart. |
| **Unexplained** | Stop and investigate. An unexplained divergence in an engine file is the one case where copying is genuinely unsafe. |

### 3. Copy

```bash
cp -r <path-to-new-dist>/.claude/. <target>/.claude/
```

### 4. Verify the result

```bash
python3 .claude/scripts/verify_install.py
```

Expect `{"status": "ok"}` with the new `version`. Anything else means step 2 was incomplete.

### 5. Re-apply anything you deliberately kept

If step 2 identified a local fix you had to preserve, re-apply it now and re-run the verification.
Its file will report as `modified` again — that is correct and expected, and it is why the decision
belongs in a commit message.

---

## Framework files vs project files

The rule that prevents most of this: **never add project content to a file under
`siegard-manifest.json`.** Each such file names its project-owned counterpart in its own header.

| Concern | Framework file (overwritten on upgrade) | Project file (never touched) |
|---|---|---|
| Error codes | `.claude/skills/u-spec-globals/error-codes.md` | `{SPECS_DIR}/_global/error-codes.md` |
| Conventions | `.claude/skills/u-spec-globals/conventions.md` | your `CLAUDE.md` |
| Engine config | — | `.orch/config.json` |
| Project instructions | `.claude/claude-md-target-template.md` (a template) | your `CLAUDE.md` |

A `modified` report on one of these is not a false positive to learn to ignore — it means content
that will be destroyed is sitting in the wrong file. Ignoring it is how the mechanism stops working:
a verification that is always dirty teaches the operator that dirty is normal.

---

## Why not an installer

Adding one is a real option, and it would remove this document. The reason it does not exist yet is
the self-containment invariant: everything a target needs must live inside the copied
`dist/.claude/` tree, because nothing runs at install time. An installer is the natural next step if
upgrades become frequent enough that the manual procedure is the bottleneck rather than the
divergence itself.
