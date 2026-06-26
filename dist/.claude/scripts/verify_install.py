#!/usr/bin/env python3
"""verify_install.py — Verify a Siegard installation against siegard-manifest.json.

Runs inside a target project (from the project root). Compares every file
listed in .claude/siegard-manifest.json with the file on disk and reports
drift as a single JSON envelope on stdout.

Hashing: SHA-256 over CRLF-normalized content ("text-lf") — a file rewritten
with Windows line endings still verifies as intact.

Finding states:
    modified   managed file present but content differs from the manifest
    missing    managed file listed in the manifest but absent on disk
    unknown    file inside a Siegard-managed namespace that is not in the
               manifest (typically a leftover from an older version) —
               warning only, does not fail the check

Files outside the managed namespaces (the target's own .claude content)
are never reported.

Usage:
    python3 .claude/scripts/verify_install.py [--claude-dir PATH]

Exit codes:
    0  Installation intact (unknown-file warnings do not fail the check).
    1  Drift found: at least one managed file modified or missing.
    2  Cannot run: .claude directory or manifest missing/unreadable.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

MANIFEST_NAME = "siegard-manifest.json"
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc"}

# Namespaces owned by Siegard inside <target>/.claude/ — used only for
# "unknown" detection; integrity of listed files is checked regardless.
MANAGED_PREFIXES = (
    "agents/",
    "hooks/",
    "lib/",
    "scripts/",
    "commands/u-",
    "skills/u-",
    "skills/orch-",
    "skills/phase-",
)


def normalize_bytes(data: bytes) -> bytes:
    """CRLF -> LF, so hashes are stable across Windows/Unix checkouts."""
    return data.replace(b"\r\n", b"\n")


def hash_file(path: Path) -> str:
    return hashlib.sha256(normalize_bytes(path.read_bytes())).hexdigest()


def iter_managed_files(claude_dir: Path) -> list[str]:
    """All distributable files under claude_dir as sorted POSIX-relative paths.

    Excludes the manifest itself, __pycache__ directories, and *.pyc files.
    Shared by gen_manifest.py (generation) and this script (verification)
    so both sides walk the tree with identical rules.
    """
    results = []
    for entry in claude_dir.rglob("*"):
        if not entry.is_file():
            continue
        if EXCLUDED_DIRS.intersection(entry.parts):
            continue
        if entry.suffix in EXCLUDED_SUFFIXES:
            continue
        rel = entry.relative_to(claude_dir).as_posix()
        if rel == MANIFEST_NAME:
            continue
        results.append(rel)
    return sorted(results)


def _error_envelope(reason: str, detail: str) -> dict:
    return {
        "status": "error",
        "framework": "siegard-code",
        "version": None,
        "summary": {"total": 0, "ok": 0, "modified": 0, "missing": 0, "unknown": 0},
        "findings": [],
        "reason": reason,
        "detail": detail,
    }


def verify(claude_dir: Path) -> tuple[dict, int]:
    """Verify claude_dir against its manifest. Returns (envelope, exit_code)."""
    if not claude_dir.is_dir():
        return _error_envelope("claude_dir_not_found", str(claude_dir)), 2

    manifest_path = claude_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return _error_envelope("manifest_not_found", str(manifest_path)), 2

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {f["path"]: f["sha256"] for f in manifest["files"]}
        version = manifest["version"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return _error_envelope("manifest_unreadable", f"{type(exc).__name__}: {exc}"), 2

    findings = []
    counts = {"total": len(expected), "ok": 0, "modified": 0, "missing": 0, "unknown": 0}

    for rel_path, digest in expected.items():
        target = claude_dir / rel_path
        if not target.is_file():
            counts["missing"] += 1
            findings.append({"path": rel_path, "state": "missing"})
        elif hash_file(target) != digest:
            counts["modified"] += 1
            findings.append({"path": rel_path, "state": "modified"})
        else:
            counts["ok"] += 1

    for rel_path in iter_managed_files(claude_dir):
        if rel_path not in expected and rel_path.startswith(MANAGED_PREFIXES):
            counts["unknown"] += 1
            findings.append({"path": rel_path, "state": "unknown"})

    if counts["missing"]:
        status, exit_code = "incomplete", 1
    elif counts["modified"]:
        status, exit_code = "modified", 1
    else:
        status, exit_code = "ok", 0

    envelope = {
        "status": status,
        "framework": manifest.get("framework", "siegard-code"),
        "version": version,
        "summary": counts,
        "findings": findings,
    }
    return envelope, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--claude-dir",
        default=".claude",
        help="Path to the installed .claude directory (default: ./.claude)",
    )
    args = parser.parse_args(argv)

    envelope, exit_code = verify(Path(args.claude_dir))
    print(json.dumps(envelope, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
