# Task: Audit and prune `tests/` to eliminate cosmetic tests

## Goal

Perform a systematic audit of all 1249 tests across `tests/` (root level and `tests/orch/`). Classify each test file as **critical**, **contract**, **integration**, or **cosmetic**. Remove cosmetic tests and resolve duplication between the root-level orch unit tests (`tests/test_*.py`) and their expanded counterparts in `tests/orch/`. The result must be a leaner test suite where every test either (a) enforces an architecture invariant, (b) validates a schema contract, or (c) exercises a behavior observable from outside the module.

Execute iteratively via `/loop`, processing one file group per iteration until all groups are evaluated and the suite stabilized.

## Type
`test`

## Project Context

- **Stack**: Python 3.12, pytest 9.0.3, stdlib only — no external deps
- **Conventions**: `tests/pytest.ini` at rootdir; test discovery via `tests/conftest.py` and `tests/orch/conftest.py`
- **Architecture invariants**: P1–P12 in `extras/architecture.md` — every retained test must trace to at least one invariant or a published schema/fixture
- **Relevant existing code**:
  - `dist/.claude/lib/orch_core.py` — core library under test
  - `dist/.claude/hooks/` — hook scripts tested by `test_hooks.py`, `test_on_stop.py`, `test_on_subagent_stop.py`
  - `dist/.claude/scripts/` — scripts tested by `test_preflight.py`, `test_scripts.py`, `test_circuit_breaker.py`, `test_dlq_triage.py`
  - `tests/fixtures/` — YAML valid/invalid fixtures for schema conformance tests

## Scope

### In scope
- All `tests/*.py` files (root level)
- All `tests/orch/**/*.py` files
- Fixtures in `tests/fixtures/` referenced only by cosmetic tests (delete orphaned fixtures)
- `conftest.py` helpers that only cosmetic tests rely on

### Out of scope
- `dist/` artifacts — do not modify production code to satisfy tests
- Adding new tests — this task is pruning only
- `CLAUDE.md`, `extras/`, `docs/` — read-only context

---

## Classification Criteria

Apply this rubric to every test function:

| Category | Rule | Action |
|---|---|---|
| **Critical** | Enforces an architecture invariant (P1–P12) or guards a behavioral contract that, if broken, silently corrupts state | Keep unconditionally |
| **Contract** | Validates a schema with a fixture pair (valid/invalid) or checks a CLI exit code | Keep if the schema/CLI is still published in `dist/` |
| **Integration** | Exercises multiple components together and would catch a real regression not caught by unit tests | Keep if it provides non-redundant coverage |
| **Cosmetic** | Existence checks (`assert len(...) > 0`), trivial string assertions, parametrized tests that repeat a passing scenario with no variation in boundary conditions, tests duplicated verbatim between root and `tests/orch/` | Delete |

---

## /loop Execution Plan

Each loop iteration processes exactly one **file group** (see list below), then exits. The next iteration continues from the next group. The loop terminates when `AUDIT_STATUS.md` lists all groups as `done` and `pytest` exits 0.

### File Groups (iterate in this order)

```
Group A  — tests/test_orch_core_helpers.py
Group B  — tests/test_log_integrity.py + tests/orch/test_verify.py + tests/orch/test_verify_and_recover.py + tests/test_verify_chain.py
Group C  — tests/test_reducer.py vs tests/orch/test_reducer.py (duplication audit)
Group D  — tests/test_retry.py vs tests/orch/test_retry.py + tests/orch/test_retry_reducer.py
Group E  — tests/test_state_machine.py + tests/orch/test_append.py + tests/orch/test_event.py
Group F  — tests/test_hooks.py + tests/orch/test_on_stop.py + tests/orch/test_on_subagent_stop.py
Group G  — tests/test_blob.py vs tests/orch/test_blobs.py (duplication audit)
Group H  — tests/test_escalation.py vs tests/orch/orchestrator_scenarios/test_escalation_flows.py
Group I  — tests/test_worker_registry.py vs tests/orch/test_worker_registry_and_config.py
Group J  — tests/test_integration.py vs tests/orch/test_integration.py + tests/orch/test_e2e_phase_lifecycle.py + tests/orch/test_recovery_e2e.py
Group K  — tests/orch/test_circuit_breaker.py + tests/orch/test_dlq_cascade.py + tests/orch/test_dlq_triage.py
Group L  — tests/orch/test_locking.py + tests/orch/test_stale.py + tests/orch/test_perf.py
Group M  — tests/orch/test_preflight.py + tests/orch/test_append_cli.py + tests/orch/test_emit_cli.py + tests/orch/test_read.py + tests/orch/test_read_verify_cli.py + tests/orch/test_orch_state_cli.py
Group N  — tests/orch/orchestrator_scenarios/test_dev_failures.py + test_phase_handoffs.py
Group O  — tests/orch/phase_scripts/ (all 5 files)
Group P  — tests/test_layer1_frontmatter.py + tests/test_layer3_cross_references.py
Group Q  — tests/test_layer2_schema_conformance.py + tests/test_layer5_flows.py + tests/test_layer5_design_system_config.py
Group R  — tests/test_layer6_spec_templates.py + tests/test_layer7_content_integrity.py + tests/test_layer8_improve_triage_flows.py + tests/test_layer9_handoff_envelope_flow.py
Group S  — tests/test_layer10_shared_suite_run.py + tests/test_layer11_qa_mode_classifier.py
Group T  — tests/test_scripts.py (scripts integration)
```

### Per-iteration procedure

```
1. Read the current group's test files in full.
2. Classify each test function using the rubric above.
3. For Groups C, D, G, H, I, J (duplication audits):
   a. Diff semantics between root-level and tests/orch/ versions.
   b. If tests/orch/ version covers a strict superset, delete the root-level file entirely.
   c. If root-level contains tests not in tests/orch/, migrate those tests to the orch version before deleting.
4. Delete cosmetic tests in-place (edit the file; do not leave empty test classes).
5. If a file becomes empty after pruning, delete the file.
6. Run: python3 -m pytest tests/ -x -q 2>&1 | tail -5
7. Assert exit code 0 and record the new test count.
8. Append one line to AUDIT_STATUS.md: "<Group X> done — <before> → <after> tests (<N> removed>"
9. Stop. (Next loop iteration picks up the next group.)
```

---

## Files to Touch

| Path | Action | Purpose |
|------|--------|---------|
| `tests/test_orch_core_helpers.py` | modify/delete | Remove trivial canonical-JSON unit tests that duplicate Python's own dict sorting guarantees |
| `tests/test_reducer.py` | delete after migration | Superseded by `tests/orch/test_reducer.py` (774 vs 530 lines) |
| `tests/test_retry.py` | delete after migration | Superseded by `tests/orch/test_retry.py` + `test_retry_reducer.py` |
| `tests/test_blob.py` | delete after migration | Superseded by `tests/orch/test_blobs.py` |
| `tests/test_verify_chain.py` | delete after migration | Superseded by `tests/orch/test_verify.py` + `test_verify_and_recover.py` |
| `tests/test_worker_registry.py` | delete after migration | Superseded by `tests/orch/test_worker_registry_and_config.py` |
| `tests/test_layer3_cross_references.py` | modify | Remove `test_finds_schema_files` / `test_finds_skill_directories` (existence-only) |
| `tests/test_layer1_frontmatter.py` | modify | Remove `test_discovery_sanity` (trivial) |
| `tests/orch/test_perf.py` | delete | Performance benchmarks are not functional correctness gates; remove from CI suite |
| `AUDIT_STATUS.md` | create | Per-iteration progress ledger |

---

## Acceptance Criteria

- [ ] Every retained test maps to at least one of: architecture invariant P1–P12, a schema/fixture pair in `tests/fixtures/`, or a documented CLI contract
  - **Verify:** manual review of `AUDIT_STATUS.md` classification log
- [ ] No duplicate test function (same behavior, different file) in the final suite
  - **Verify:** `grep -rh "def test_" tests/ | sort | uniq -d` returns empty
- [ ] Final test count <= 900 (target: >=25% reduction from 1249, zero behavioral regressions)
  - **Verify:** `python3 -m pytest tests/ --collect-only -q 2>&1 | tail -1`
- [ ] All retained tests pass
  - **Verify:** `python3 -m pytest tests/ -x -q`
- [ ] No orphaned fixture files (fixtures only referenced by deleted tests are removed)
  - **Verify:** `python3 -m pytest tests/ --collect-only -q 2>&1 | grep "ERROR\|warning"` returns empty
- [ ] Root-level `tests/*.py` contains only tests with no equivalent in `tests/orch/`
  - **Verify:** compare module names between root and `tests/orch/` — no semantic overlap

## Verification

```bash
python3 -m pytest tests/ -x -q
python3 -m pytest tests/ --collect-only -q 2>&1 | tail -1
grep -rh "def test_" tests/ | sort | uniq -d
```

## Edge Cases & Risks

- **Migration before deletion**: for Groups C/D/G/H/I/J, always confirm that unique tests in the root-level file are migrated to the `orch/` counterpart before the root file is deleted; running pytest after each migration verifies nothing was lost
- **Parametrized expansion**: some tests generate many IDs from `dist/` file lists (e.g., test_layer2_schema_conformance parametrizes per fixture file); count reduction from schema tests reflects fixture count, not cosmetic test removal — do not delete these based on count alone
- **Conftest coupling**: `tests/conftest.py` helper functions used only by deleted test files must be removed from conftest to prevent dead code; but do not remove helpers used by any retained test
