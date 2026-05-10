# Audit Status

| Group | Files | Status | Before | After | Removed |
|-------|-------|--------|--------|-------|---------|
| A | tests/test_orch_core_helpers.py | done | 1249 | 1241 | 8 |
| B | tests/test_log_integrity.py + tests/orch/test_verify.py + tests/orch/test_verify_and_recover.py + tests/test_verify_chain.py | done | 1241 | 1215 | 26 |
| C | tests/test_reducer.py vs tests/orch/test_reducer.py | done | 1215 | 1179 | 36 |
| D | tests/test_retry.py vs tests/orch/test_retry.py + tests/orch/test_retry_reducer.py | done | 1179 | 1179 | 0 (root file already absent) |
| E | tests/test_state_machine.py + tests/orch/test_append.py + tests/orch/test_event.py | done | 1179 | 1158 | 21 |
| F | tests/test_hooks.py + tests/orch/test_on_stop.py + tests/orch/test_on_subagent_stop.py | done | 1158 | 1149 | 9 |
| G | tests/test_blob.py vs tests/orch/test_blobs.py | done | 1149 | 1139 | 10 |
| H | tests/test_escalation.py vs tests/orch/orchestrator_scenarios/test_escalation_flows.py | done | 1139 | 1125 | 14 |
| I | tests/test_worker_registry.py vs tests/orch/test_worker_registry_and_config.py | done | 1125 | 1122 | 3 (9 removed, 6 migrated) |
| J | tests/test_integration.py vs orch integration tests | done | 1122 | 1116 | 6 |
| K | tests/orch/test_circuit_breaker.py + tests/orch/test_dlq_cascade.py + tests/orch/test_dlq_triage.py | done | 1116 | 1116 | 0 (all contract/integration) |
| L | tests/orch/test_locking.py + tests/orch/test_stale.py + tests/orch/test_perf.py | done | 1116 | 1108 | 8 (4 from test_perf.py deleted, 4 cosmetic from test_locking.py) |
| M | tests/orch/test_preflight.py + test_append_cli.py + test_emit_cli.py + test_read.py + test_read_verify_cli.py + test_orch_state_cli.py | done | 1108 | 1101 | 7 |
| N | tests/orch/orchestrator_scenarios/test_dev_failures.py + test_phase_handoffs.py | done | 1101 | 1101 | 0 (all integration scenarios) |
| O | tests/orch/phase_scripts/ (5 files) | done | 1101 | 1101 | 0 (all contract) |
| P | tests/test_layer1_frontmatter.py + tests/test_layer3_cross_references.py | done | 1101 | 1098 | 3 |
| Q | tests/test_layer2_schema_conformance.py + tests/test_layer5_flows.py + tests/test_layer5_design_system_config.py | done | 1098 | 1093 | 5 |
| R | tests/test_layer6_spec_templates.py + tests/test_layer7_content_integrity.py + tests/test_layer8_improve_triage_flows.py + tests/test_layer9_handoff_envelope_flow.py | done | 1093 | 1089 | 4 |
| S | tests/test_layer10_shared_suite_run.py + tests/test_layer11_qa_mode_classifier.py | done | 1089 | 1089 | 0 (all integration) |
| T | tests/test_scripts.py | done | 1089 | 1087 | 2 |
| FINAL | Cross-file deduplication: test_orch_core_helpers.py (validate_orchestrator_report), test_e2e_phase_lifecycle.py, test_blobs.py | done | 1087 | 1073 | 14 |

## Summary

- **Start**: 1249 tests
- **End**: 1073 tests  
- **Removed**: 176 tests (14.1% reduction)
- **All 1073 tests pass**: ✅
- **Target ≤900**: ❌ Not reached — remaining tests are all contract/integration/critical
- **No behavioral regressions**: ✅

## Acceptance Criteria

- [x] All retained tests pass (`python3 -m pytest tests/ -x -q`)
- [x] No duplicate test behavior (verified per file group)
- [ ] Final count ≤900 — reached 1073 (target was too aggressive; remaining tests are substantive)
- [x] No orphaned fixture files
