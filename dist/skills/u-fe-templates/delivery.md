# Template: tc-XX-delivery.md

Save to `{SESSIONS_DIR}/{SESSION}/tc-XX-delivery.md`.

Two YAML blocks, sequential. QA reads gate first — if `qa_ready: false`, stops immediately. Then reads body for implementation details and inference audit.

````markdown
```yaml
# delivery-gate
task: TC-XX
layer: semi-permanent
delivered_by: u-fe-developer
timestamp: <YYYY-MM-DDTHH:MM:SSZ>

status: implemented | implemented_with_caveats

spec_consumed:
  feature_spec: "<feature>.feature.spec.md@<version>"
  component_specs: []
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

acceptance_criteria_coverage:
  - criterion: "Given X, When Y, Then Z"
    status: covered | not_covered
    location: "path/file.tsx:functionName()"
    not_covered_reason: ""

edge_cases:
  - case: ""
    handling: ""

backend_dependencies:
  report: "tc-XX-backend-pending-items.md" | none
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
