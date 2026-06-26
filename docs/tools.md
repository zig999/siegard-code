# Project Tools

Authoring-time tools of the siegard-code repository. None of these are part of the distribution (`dist/.claude/`).

## gen_manifest.py

Generates `dist/.claude/siegard-manifest.json` — the versioned inventory (SHA-256 per file) that travels with the manual copy into target projects and is consumed by `dist/.claude/scripts/verify_install.py`.

| Aspect | Value |
|---|---|
| Location | repo root |
| Usage | `python3 gen_manifest.py [--version X.Y.Z] [--repository URL]` |
| `--version` | Required on first generation; afterwards reuses the current manifest version when omitted |
| `--repository` | Defaults to existing manifest value, else `git remote get-url origin` |
| Hash rules | Imported from `verify_install.py` (`iter_managed_files`, `hash_file`) — generation and verification share one code path |
| Normalization | SHA-256 over CRLF→LF normalized content (`text-lf`) — hashes stable across Windows/Unix checkouts |
| Exclusions | `__pycache__/`, `*.pyc`, the manifest itself |
| Output | One JSON envelope on stdout; exit 0 written / 1 error |
| Guarded by | `tests/test_manifest_integrity.py` — a stale manifest (any dist file added/removed/edited after generation) fails the suite |

Run it after ANY change to `dist/` content, before committing.
