# Template: tc-XX-delivery.md (Backend)

Save to `$SESSION_DIR/delivery/$ORCH_TASK_ID-delivery.md`.

Two YAML blocks, sequential. QA reads gate first — if `qa_ready: false`, stops immediately. Then reads body for implementation details and inference audit.

````markdown
```yaml
# delivery-gate
task_id: TC-XX
layer: semi-permanent
delivered_by: u-be-developer
timestamp: <YYYY-MM-DDTHH:MM:SSZ>

status: implemented | implemented_with_caveats

spec_consumed:
  domain_spec: "<domain>.spec.md@<version>"
  back_spec: "<domain>.back.md@<version>"
  openapi: "<domain>/openapi.yaml@<version>"

tests:
  command: <exact test command from CLAUDE.md>
  last_local_run: passed | failed
  total: <int>
  passed: <int>
  failed: <int>

acceptance_criteria:
  total: <int>
  covered: <int>
  uncovered: []

spec_divergences:
  count: <int>
  items: []

tech_debt:
  count: <int>

prohibition_violations: []
# Mandatory list (empty = clean). Each entry must declare a violation of the rules in
# u-be-development.md "Explicit prohibitions" (e.g., temporary console.log, hardcoded
# value awaiting token, suppressed test). Format per item:
#   - rule: "<rule name>"
#     location: "<path/file:line>"
#     reason: "<why it could not be removed in this TC>"
#     remediation: "<follow-up TC id or next step>"

qa_ready: true | false
qa_notes: ""
```

```yaml
# delivery-body
files_created:
  - path: ""
    responsibility: ""

files_modified:
  - path: ""
    change: ""

migrations_created:
  - path: ""
    description: ""

acceptance_criteria_coverage:
  - criterion: "Given X, When Y, Then Z"
    status: covered | not_covered
    location: "path/file.ts:functionName()"
    not_covered_reason: ""

edge_cases:
  - case: ""
    handling: ""

infra_dependencies:
  report: "tc-XX-infra-pending-items.md" | none
  mocks_created: []

tech_debt:
  - item: ""
    issue_ref: ""

tests:
  - file: ""
    covers: []

inference_log:
  - decision: ""
    rationale: ""
    evidence: []
    impact: ""
```
````
