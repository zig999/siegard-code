# Installation

This chapter describes how to install the Dev Team Agents into a target project.

## Prerequisites

- **Claude Code** installed and functional on the machine
- Access to the `siegard-code/` repository (source repo)
- Target project already created with a basic folder structure

## Installation

Copy the contents of `dist/` into the target project's `.claude/` directory:

```bash
cp -r siegard-code/dist/agents/ /path/to/your-project/.claude/agents/
cp -r siegard-code/dist/commands/ /path/to/your-project/.claude/commands/
cp -r siegard-code/dist/skills/ /path/to/your-project/.claude/skills/
```

On Windows (PowerShell):

```powershell
Copy-Item -Recurse -Force siegard-code\dist\agents your-project\.claude\
Copy-Item -Recurse -Force siegard-code\dist\commands your-project\.claude\
Copy-Item -Recurse -Force siegard-code\dist\skills your-project\.claude\
```

This copies all agents, skills, and commands into the target project.

## What is copied

| Source (siegard-code/dist/) | Destination (project/.claude/) | Description |
|-----------------------------|--------------------------------|-------------|
| `commands/` | `commands/` | The 6 slash commands available |
| `agents/` | `agents/` | All agents from the 3 teams |
| `skills/` | `skills/` | Complete skill catalog |

### Overwrite behavior

- Agents, skills, and commands are **always overwritten** on re-copy (full update)
- The target project's `CLAUDE.md` must be created and configured manually -- it is never generated or overwritten

## After installation

1. Configure the target project's `CLAUDE.md` -- see [Project Configuration](project-configuration.md)
2. Verify the directory structure -- see [Directory Structure](directory-structure.md)
3. Run a test command to validate the installation -- see [Commands](../03-commands/README.md)

## Next steps

- [Project Configuration](project-configuration.md) -- How to fill in CLAUDE.md
- [Directory Structure](directory-structure.md) -- Full tree of source repo and target project
- [Back to Index](../README.md)
