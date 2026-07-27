#!/usr/bin/env python3
"""
verify_evidence.py — Cited evidence must be evidence that was produced.

The defect this closes, twice observed. A spec worker states something
*verifiable* about the source code and does not verify it:

  * BR-BE-24 declared three method signatures that do not exist
    (`getTechProfileBatch.execute(taskSeq)` vs the real
    `execute(userIds: string[])`, and two more). They were inferred from the
    accessor name. Five workers and ~44 min of execution passed over that table
    and none opened a service file. An implementation faithful to the spec would
    have produced interfaces the real services do not satisfy — the spec would
    have *caused* the compile break it exists to prevent.

  * BR-08 §4.3 went further and cited a command: "grep em plan.test.ts /
    collect.test.ts: derivesSubjects aparece só em fixtures de topologia". The
    grep was never run, and the real grep contradicts it — two golden vectors
    depend on exactly what the spec said nothing depended on.

The second is the worse one. An unsupported claim is weak and reads as weak; a
claim wearing false evidence reads as *checked*, and disarms the very scepticism
that would have caught it. Citing evidence costs nothing today, so it is worth
nothing. This script makes the citation cost one re-execution.

Both classes are verified here:

  `file_claim`  — {file, line, excerpt_sha256}: the excerpt at that location must
                  still hash to the recorded value.
  `command_claim` — {command, cwd, exit_code, output_sha256}: the command is
                  RE-RUN and must reproduce the recorded exit code and output.

Commands are re-run only from an allowlist of read-only tools. A spec may not
smuggle arbitrary execution into a validation gate.

Evidence block format (inside any spec file):

    <!-- evidence
    - kind: file_claim
      claim: "GetTechProfileBatchService.execute accepts userIds: string[]"
      file: backend/src/modules/fsm/service/get-tech-profile-batch.service.ts
      line: 42
      excerpt_sha256: 9f2b...
    - kind: command_claim
      claim: "derivesSubjects appears only in topology fixtures"
      command: "grep -c derivesSubjects backend/src/.../plan.test.ts"
      cwd: "."
      exit_code: 0
      output_sha256: 4ac1...
    -->

Usage:
    python3 verify_evidence.py --spec <file> [--spec <file> ...]
                              [--project-dir <dir>] [--allow-unverified]

Output (stdout, JSON):
    {"total": int, "verified": int, "failed": [{...}], "unverified": [{...}]}

Exit codes:
    0  every claim verified (or only `unverified: true` claims, with --allow-unverified)
    2  at least one claim FAILED verification — the spec asserts something false
    1  usage/internal error
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

_EVIDENCE_BLOCK_RE = re.compile(r"<!--\s*evidence\s*(.*?)-->", re.DOTALL)

# Read-only tools only. A validation gate must never become an execution vector:
# the spec is authored by an LLM, and re-running whatever it names would let a
# hallucinated command run with the validator's privileges.
_ALLOWED_COMMANDS = frozenset({
    "grep", "rg", "egrep", "fgrep", "wc", "find", "ls", "cat", "head", "tail",
    "sort", "uniq", "cut", "awk", "sed", "git", "python3", "test",
})
# `git` subcommands that only read.
_ALLOWED_GIT_SUBCOMMANDS = frozenset({
    "log", "show", "diff", "grep", "ls-files", "rev-parse", "status", "cat-file",
    "describe", "blame", "shortlog",
})


def sha256(text: str) -> str:
    """Hash normalized text: trailing whitespace per line and CRLF are noise."""
    normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n"))
    return hashlib.sha256(normalized.strip().encode("utf-8")).hexdigest()


def _unquote(value: str) -> str:
    """Strip ONE matching pair of surrounding quotes.

    Not `.strip('"').strip("'")`: that mangles any value whose content legitimately
    ends in a quote — `command: "find src -name '*.ts'"` lost its closing `'` and
    became unparseable, so a valid read-only command was rejected for the wrong
    reason. Inner quotes belong to the value.
    """
    for quote in ('"', "'"):
        if len(value) >= 2 and value[0] == quote and value[-1] == quote:
            return value[1:-1]
    return value


def _parse_claims(text: str) -> list[dict]:
    """Minimal list-of-mappings parser for the evidence block (stdlib only)."""
    claims: list[dict] = []
    for block in _EVIDENCE_BLOCK_RE.findall(text):
        current: dict | None = None
        for raw in block.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            stripped = line.strip()
            if stripped.startswith("- "):
                if current:
                    claims.append(current)
                current = {}
                stripped = stripped[2:].strip()
                if not stripped:
                    continue
            if current is None or ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            value = _unquote(value.strip())
            key = key.strip()
            if key in ("line", "exit_code"):
                try:
                    current[key] = int(value)
                except ValueError:
                    current[key] = value
            elif key == "unverified":
                current[key] = value.lower() == "true"
            else:
                current[key] = value
        if current:
            claims.append(current)
    return claims


def _command_is_allowed(command: str) -> tuple[bool, str]:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return False, f"unparseable command: {exc}"
    if not parts:
        return False, "empty command"
    # Shell metacharacters would bypass the allowlist entirely.
    for token in parts:
        if any(ch in token for ch in ";|&`$()<>"):
            return False, f"shell metacharacter in {token!r} — not allowed"
    exe = Path(parts[0]).name
    if exe not in _ALLOWED_COMMANDS:
        return False, f"{exe!r} is not in the read-only allowlist"
    if exe == "git":
        sub = next((p for p in parts[1:] if not p.startswith("-")), None)
        if sub not in _ALLOWED_GIT_SUBCOMMANDS:
            return False, f"git subcommand {sub!r} is not read-only"
    return True, ""


def _verify_file_claim(claim: dict, project_dir: Path) -> tuple[bool, str]:
    path = claim.get("file")
    if not path:
        return False, "file_claim without a 'file' field"
    target = project_dir / path
    if not target.is_file():
        return False, f"file does not exist: {path}"
    recorded = claim.get("excerpt_sha256")
    if not recorded:
        return False, "file_claim without 'excerpt_sha256' — nothing to verify against"
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return False, f"unreadable: {exc}"

    line_no = claim.get("line")
    if isinstance(line_no, int) and 1 <= line_no <= len(lines):
        excerpt = lines[line_no - 1]
    else:
        return False, f"line {line_no!r} is out of range (file has {len(lines)} lines)"

    actual = sha256(excerpt)
    if actual != recorded:
        return False, (
            f"{path}:{line_no} no longer matches the recorded excerpt "
            f"(recorded {recorded[:12]}…, actual {actual[:12]}…). The claim was "
            "true when written or was never checked; either way it is not true now"
        )
    return True, ""


def _verify_command_claim(claim: dict, project_dir: Path) -> tuple[bool, str]:
    command = claim.get("command")
    if not command:
        return False, "command_claim without a 'command' field"
    ok, why = _command_is_allowed(command)
    if not ok:
        return False, why
    recorded_hash = claim.get("output_sha256")
    if not recorded_hash:
        return False, "command_claim without 'output_sha256' — nothing to verify against"

    cwd = project_dir / (claim.get("cwd") or ".")
    if not cwd.is_dir():
        return False, f"cwd does not exist: {claim.get('cwd')}"
    try:
        proc = subprocess.run(
            shlex.split(command), cwd=str(cwd),
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"command could not be re-run: {exc}"

    recorded_exit = claim.get("exit_code")
    if isinstance(recorded_exit, int) and proc.returncode != recorded_exit:
        return False, (
            f"exit code changed: recorded {recorded_exit}, actual {proc.returncode}"
        )
    actual_hash = sha256(proc.stdout)
    if actual_hash != recorded_hash:
        return False, (
            "re-running the cited command produced different output "
            f"(recorded {recorded_hash[:12]}…, actual {actual_hash[:12]}…). If the "
            "command was never run, this is the BR-08 defect: a claim wearing "
            "evidence that was never produced"
        )
    return True, ""


_VERIFIERS = {
    "file_claim": _verify_file_claim,
    "command_claim": _verify_command_claim,
}


def verify(spec_paths: list[Path], project_dir: Path,
           allow_unverified: bool) -> dict:
    total = 0
    verified = 0
    failed: list[dict] = []
    unverified: list[dict] = []

    for spec in spec_paths:
        if not spec.is_file():
            failed.append({"spec": str(spec), "reason": "spec file not found"})
            continue
        text = spec.read_text(encoding="utf-8", errors="replace")
        for claim in _parse_claims(text):
            total += 1
            record = {
                "spec": str(spec),
                "claim": claim.get("claim", "<no claim text>"),
                "kind": claim.get("kind"),
            }
            # An explicit `unverified: true` is the honest escape hatch: the
            # worker could not check it and says so. Inventing a value is the
            # failure mode being prevented, not admitting ignorance.
            if claim.get("unverified"):
                unverified.append(record)
                continue
            verifier = _VERIFIERS.get(claim.get("kind"))
            if verifier is None:
                failed.append({**record, "reason":
                               f"unknown evidence kind {claim.get('kind')!r}"})
                continue
            ok, why = verifier(claim, project_dir)
            if ok:
                verified += 1
            else:
                failed.append({**record, "reason": why})

    return {
        "total": total,
        "verified": verified,
        "failed": failed,
        "unverified": unverified,
        "allow_unverified": allow_unverified,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", action="append", required=True,
                    help="spec file to scan for evidence blocks (repeatable)")
    ap.add_argument("--project-dir",
                    default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--allow-unverified", action="store_true",
                    help="do not fail on claims explicitly marked unverified")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    result = verify([Path(s) for s in args.spec], project_dir,
                    args.allow_unverified)
    print(json.dumps(result))

    if result["failed"]:
        sys.exit(2)
    if result["unverified"] and not args.allow_unverified:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
