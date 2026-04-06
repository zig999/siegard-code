# /u-reverse-spec -- Reverse Specification Command

Reverse-engineers technical specifications from existing source code.

## Usage

```
/u-reverse-spec [CODE_DIR]
```

## Pipeline

```
Orchestrator -> Analyzer -> Writer
```

- **Analyzer** scans source code and produces `_temp/analysis-report.md`
- **Writer** generates spec artifacts from the analysis report using standard templates
- All artifacts are marked with `draft` status

## Mode detection

| Mode | Trigger | Behavior |
|------|---------|----------|
| **New** | No `{SPECS_DIR}` directory exists | Generate specs from scratch |
| **Merge** | `{SPECS_DIR}` already exists | Compare generated specs with existing, produce merge report |
| **Resume** | `log-reverse-spec.md` exists with incomplete stages | Resume from last stage |

## Initial validation

The orchestrator confirms that `CODE_DIR` contains source code by checking for common project indicators (e.g., dependency manifests, source directories, configuration files).

## Stack auto-detection

The Analyzer automatically identifies:
- Programming language and framework
- Database and ORM
- State management and data fetching patterns (frontend)
- Authentication and authorization patterns
- Project structure and architecture patterns

Detection is based on dependency manifests, file patterns, and import analysis. Results are recorded in the analysis report.

## Generated artifacts

All artifacts use the same templates as the Spec Writer but receive `draft` status:
- `domains/{domain}/openapi.yaml`
- `{domain}.spec.md`, `{domain}.back.md`
- `front/screens/{screen}.screen.md`
- `front/_flows/{flow}.flow.md`
- `_meta/origin-reverse-spec.md` -- Origin marker for `/u-spec` detection

## What happens next

After `/u-reverse-spec` completes:
1. Run `/u-spec` to formally review and approve the draft specs
2. Optionally run `/u-spec-triage` if validation returns many errors
3. Then run `/u-dev` to start implementation
