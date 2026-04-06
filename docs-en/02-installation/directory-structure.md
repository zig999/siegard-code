# Directory Structure

Complete directory tree after installation, for both the source repository and the target project.

## Source repository (siegard-code/)

```
siegard-code/
  dist/
    agents/
      dev/                      # Dev team agents (FE + BE)
        protocols/              # On-demand protocols
      spec/                     # Spec team agents
        protocols/              # On-demand protocols
      reverse-spec/             # Reverse Spec team agents
        protocols/              # On-demand protocols
    commands/                   # Slash commands (/u-spec, /u-dev, etc.)
    skills/                     # Reusable skill catalog
  docs-en/                      # English documentation
```

## Target project (after installation)

```
project/
  .claude/
    agents/                     # Installed agents (always overwritten)
      dev/
        protocols/
      spec/
        protocols/
      reverse-spec/
        protocols/
    commands/                   # Installed commands (always overwritten)
    skills/                     # Installed skills (always overwritten)
  CLAUDE.md                     # Project configuration (created manually)
  {SPECS_DIR}/                  # Specification directory
    _global/                    # Shared resources
      conventions.md            # Project conventions
      error-codes.md            # Error code catalog
      glossary.md               # Domain glossary
    _templates/                 # Spec templates
    _meta/                      # Metadata (origin markers, changelog)
    _validation/                # Persisted validation reports
    domains/                    # Backend specs organized by domain
      {domain}/
        openapi.yaml            # API contract
        {domain}.spec.md        # Use cases and business rules
        back/
          {domain}.back.md      # Backend technical spec
    front/                      # Frontend specs
      front.md                  # Global frontend spec
      design-system/            # Design system reference
      screens/                  # Screen specifications
        {screen}.screen.md
      _flows/                   # Navigation flows
        {flow}.flow.md
    openapi.root.yaml           # Root OpenAPI aggregator
    log-orchestrator-spec.md    # Spec orchestrator log
  {SESSIONS_DIR}/               # Session directory
    {SESSION}/                  # Current session working directory
      backlog.md                # Story backlog (permanent)
      us-XX-delivery.md         # Story delivery file (-> _temp/)
      us-XX-qa.md               # QA report (-> _temp/)
      us-XX-pending-items.md    # Blockers/dependencies (permanent)
      ui-epic-XX.md             # UI specifications (-> _temp/)
      tech-debt.md              # Technical debt registry (permanent)
      log-orchestrator-dev.md   # Dev orchestrator log (permanent)
      _temp/                    # Archived artifacts
```

## Organization principles

- **Backend**: Specs organized by **domain** (`domains/{domain}/`)
- **Frontend**: Specs organized by **screen/flow** (`front/screens/`, `front/_flows/`), not by domain -- because screens often compose multiple domains
- **Temporary artifacts**: Moved to `_temp/` after consumption, never deleted
- **Permanent artifacts**: `backlog.md`, `tech-debt.md`, `pending-items.md`, and orchestrator logs remain in place
