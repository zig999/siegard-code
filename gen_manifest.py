#!/usr/bin/env python3
"""gen_manifest.py — Generate dist/.claude/siegard-manifest.json (release tool).

Authoring-time tool for the siegard-code repository — NOT part of the
distribution. Walks dist/.claude/, hashes every distributable file
(SHA-256 over CRLF-normalized content), and writes the manifest that
travels with the manual copy into target projects.

Hash/walk rules are imported from dist/.claude/scripts/verify_install.py
so generation and verification are the same code path by construction.

Usage:
    python3 gen_manifest.py [--version X.Y.Z] [--repository URL]

    --version     Required on first generation; afterwards reuses the
                  current manifest version when omitted.
    --repository  Defaults to the existing manifest value, else to
                  `git remote get-url origin`.

Exit codes:
    0  Manifest written.
    1  Error (missing/invalid version, no repository resolvable, IO failure).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_DIST_CLAUDE = _REPO_ROOT / "dist" / ".claude"

sys.path.insert(0, str(_DIST_CLAUDE / "scripts"))

from verify_install import MANIFEST_NAME, hash_file, iter_managed_files

_SEMVER = re.compile(r"\d+\.\d+\.\d+")


def _load_existing() -> dict:
    manifest_path = _DIST_CLAUDE / MANIFEST_NAME
    if not manifest_path.is_file():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _resolve_repository(arg_value: str | None, existing: dict) -> str | None:
    if arg_value:
        return arg_value
    if existing.get("source", {}).get("repository"):
        return existing["source"]["repository"]
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, cwd=_REPO_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Release version (X.Y.Z)")
    parser.add_argument("--repository", help="Source repository URL")
    args = parser.parse_args(argv)

    if not _DIST_CLAUDE.is_dir():
        print(json.dumps({"status": "error", "reason": "dist_not_found",
                          "detail": str(_DIST_CLAUDE)}))
        return 1

    existing = _load_existing()

    version = args.version or existing.get("version")
    if not version:
        print(json.dumps({"status": "error", "reason": "version_required",
                          "detail": "no existing manifest — pass --version X.Y.Z"}))
        return 1
    if not _SEMVER.fullmatch(version):
        print(json.dumps({"status": "error", "reason": "version_invalid",
                          "detail": f"'{version}' is not X.Y.Z"}))
        return 1

    repository = _resolve_repository(args.repository, existing)
    if not repository:
        print(json.dumps({"status": "error", "reason": "repository_unresolvable",
                          "detail": "pass --repository URL"}))
        return 1

    files = [
        {"path": rel_path, "sha256": hash_file(_DIST_CLAUDE / rel_path)}
        for rel_path in iter_managed_files(_DIST_CLAUDE)
    ]

    manifest = {
        "framework": "siegard-code",
        "version": version,
        "source": {"repository": repository},
        "generated_at": datetime.now(timezone.utc)
                                .isoformat(timespec="seconds")
                                .replace("+00:00", "Z"),
        "hash_normalization": "text-lf",
        "files": files,
    }

    manifest_path = _DIST_CLAUDE / MANIFEST_NAME
    try:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
    except OSError as exc:
        print(json.dumps({"status": "error", "reason": "write_failed",
                          "detail": f"{type(exc).__name__}: {exc}"}))
        return 1

    print(json.dumps({"status": "ok", "version": version,
                      "files": len(files), "path": str(manifest_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
