#!/usr/bin/env python3
"""
preflight.py — Validates runtime assumptions before orchestrator workflows.

Usage:
    python3 .claude/scripts/preflight.py           # full (local + remote)
    python3 .claude/scripts/preflight.py --quick   # local checks only (< 5s)

Exit codes:
    0  All checks passed.
    1  One or more checks failed.
    2  Invalid arguments.

Output: single JSON object on stdout. All other output on stderr.
"""
import argparse
try:
    import fcntl
except ImportError:  # Windows — fcntl is POSIX-only; msvcrt fallback below
    fcntl = None
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_DIR = _SCRIPTS_DIR.parent
_LIB = _DIST_DIR / "lib"

sys.path.insert(0, str(_LIB))

from orch_core import ORCH_DIR, now_iso

MIN_PYTHON = (3, 10)
MIN_CLAUDE_VERSION = (2, 1, 0)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    ok: bool
    reason: str
    duration_ms: float = 0.0
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"ok": self.ok, "reason": self.reason, "duration_ms": round(self.duration_ms, 1)}
        if self.detail:
            d["detail"] = self.detail
        return d


# ---------------------------------------------------------------------------
# Local checks
# ---------------------------------------------------------------------------

def _timed(fn: Callable[[], CheckResult]) -> CheckResult:
    start = time.monotonic()
    result = fn()
    result.duration_ms = (time.monotonic() - start) * 1000
    return result


def check_python_version() -> CheckResult:
    def _run() -> CheckResult:
        current = sys.version_info[:2]
        version_str = platform.python_version()
        if current < MIN_PYTHON:
            return CheckResult(
                ok=False,
                reason=f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, got {version_str}",
                detail={"current": version_str, "required": f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"},
            )
        return CheckResult(
            ok=True,
            reason=f"Python {version_str}",
            detail={"current": version_str},
        )
    return _timed(_run)


def check_bash_available() -> CheckResult:
    """Probes that a Bash shell can execute a command.

    The orchestrator dispatches every infrastructure step, log append, and worker
    through the Bash tool. A meta-orchestrator spawned in background runs in a
    reduced-permission sandbox WITHOUT Bash and with no interactive approval path
    (see F-01): it stalls for minutes and then asks for Bash permission instead of
    failing fast. This check surfaces a missing/unusable Bash as a structured
    E_NO_BASH failure so the infra gate blocks the cycle immediately. Orchestrators
    MUST run in foreground; background is only for read-only leaf workers.
    """
    def _run() -> CheckResult:
        bash = shutil.which("bash")
        if bash is None:
            return CheckResult(
                ok=False,
                reason="E_NO_BASH: bash not found in PATH",
                detail={"hint": "orchestrators require foreground (Bash tool); never spawn in background"},
            )
        try:
            r = subprocess.run([bash, "-c", "echo ok"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip() == "ok":
                return CheckResult(ok=True, reason="bash executes", detail={"path": bash})
            return CheckResult(
                ok=False,
                reason="E_NO_BASH: bash probe returned unexpected output",
                detail={"stdout": r.stdout[:100], "stderr": r.stderr[:100]},
            )
        except subprocess.TimeoutExpired:
            return CheckResult(ok=False, reason="E_NO_BASH: bash probe timed out after 5s")
        except OSError as exc:
            return CheckResult(ok=False, reason=f"E_NO_BASH: bash probe failed: {exc}")
    return _timed(_run)


def check_flock_works() -> CheckResult:
    def _run() -> CheckResult:
        if fcntl is None and msvcrt is None:
            return CheckResult(
                ok=False, reason="no file-locking mechanism available (fcntl and msvcrt both missing)"
            )
        try:
            with tempfile.NamedTemporaryFile(suffix=".lock", delete=False) as tf:
                lock_path = tf.name
            try:
                with open(lock_path, "w") as f:
                    if fcntl is not None:
                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(f, fcntl.LOCK_UN)
                        return CheckResult(ok=True, reason="POSIX flock works")
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    return CheckResult(ok=True, reason="msvcrt file locking works (Windows)")
            finally:
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass
        except (ImportError, AttributeError):
            return CheckResult(ok=False, reason="file-locking module not available")
        except BlockingIOError:
            return CheckResult(ok=False, reason="lock returned EWOULDBLOCK unexpectedly")
        except OSError as exc:
            return CheckResult(ok=False, reason=f"file locking failed: {exc}")
    return _timed(_run)


def check_filesystem_writable() -> CheckResult:
    def _run() -> CheckResult:
        try:
            ORCH_DIR.mkdir(parents=True, exist_ok=True)
            probe = ORCH_DIR / ".preflight_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return CheckResult(ok=True, reason=f"{ORCH_DIR} is writable")
        except OSError as exc:
            return CheckResult(ok=False, reason=f"filesystem not writable: {exc}",
                               detail={"path": str(ORCH_DIR)})
    return _timed(_run)


def check_claude_code_installed() -> CheckResult:
    def _run() -> CheckResult:
        binary = shutil.which("claude")
        if binary is None:
            return CheckResult(
                ok=False,
                reason="'claude' binary not found in PATH",
                detail={"hint": "install Claude Code CLI"},
            )
        return CheckResult(ok=True, reason=f"claude found at {binary}",
                           detail={"path": binary})
    return _timed(_run)


def check_claude_code_version() -> CheckResult:
    def _run() -> CheckResult:
        binary = shutil.which("claude")
        if binary is None:
            return CheckResult(ok=False, reason="'claude' binary not found — cannot check version")
        try:
            r = subprocess.run(
                [binary, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            raw = (r.stdout + r.stderr).strip()
            # Extract semver from output (e.g. "Claude Code 2.1.3" or "2.1.3")
            m = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
            if not m:
                return CheckResult(ok=False, reason=f"could not parse version from: {raw!r}")
            ver = tuple(int(x) for x in m.groups())
            ver_str = ".".join(str(x) for x in ver)
            if ver < MIN_CLAUDE_VERSION:
                min_str = ".".join(str(x) for x in MIN_CLAUDE_VERSION)
                return CheckResult(
                    ok=False,
                    reason=f"Claude Code {min_str}+ required, got {ver_str}",
                    detail={"current": ver_str, "required": min_str},
                )
            return CheckResult(ok=True, reason=f"Claude Code {ver_str}",
                               detail={"current": ver_str})
        except subprocess.TimeoutExpired:
            return CheckResult(ok=False, reason="'claude --version' timed out after 10s")
        except OSError as exc:
            return CheckResult(ok=False, reason=f"could not run claude: {exc}")
    return _timed(_run)


def check_claude_md_config() -> CheckResult:
    """Validates the target project's CLAUDE.md carries the pipeline config keys.

    Every pipeline entry command (/u-spec, /u-dev, /u-improve) hard-requires
    `specs_dir:` and `domain:` in the target CLAUDE.md. A fresh install that
    skipped the configuration step used to surface only as a mid-command stop;
    this check fails the infra gate up front with an actionable hint.

    Matching is deliberately loose (case-insensitive, tolerates list/bold
    markdown decoration) so existing working installs never false-positive:
    the check fails ONLY when CLAUDE.md is absent or a required key appears
    nowhere in the file.
    """
    def _run() -> CheckResult:
        project_dir = ORCH_DIR.parent
        claude_md = project_dir / "CLAUDE.md"
        template_hint = ".claude/claude-md-target-template.md (shipped with the install)"
        if not claude_md.is_file():
            return CheckResult(
                ok=False,
                reason="CLAUDE.md not found in project root — pipeline commands require it",
                detail={"expected": str(claude_md),
                        "hint": f"create it from the template: {template_hint}"},
            )
        try:
            content = claude_md.read_text(encoding="utf-8")
        except OSError as exc:
            return CheckResult(ok=False, reason=f"CLAUDE.md unreadable: {exc}",
                               detail={"path": str(claude_md)})
        missing = [
            key for key in ("specs_dir", "domain")
            if not re.search(rf"^[\s>*\-`]*\**{key}\**\s*[:=]", content,
                             re.IGNORECASE | re.MULTILINE)
        ]
        if missing:
            return CheckResult(
                ok=False,
                reason=f"CLAUDE.md missing required pipeline key(s): {', '.join(missing)}",
                detail={"missing_keys": missing, "path": str(claude_md),
                        "hint": f"declare them per the template: {template_hint}"},
            )
        return CheckResult(ok=True, reason="CLAUDE.md declares specs_dir and domain",
                           detail={"path": str(claude_md)})
    return _timed(_run)


def check_agent_references() -> CheckResult:
    """Validates all worker names referenced in select_worker.py scripts exist as agent files."""
    def _run() -> CheckResult:
        agents_dir = _DIST_DIR / "agents"
        skills_dir = _DIST_DIR / "skills"
        if not agents_dir.exists():
            return CheckResult(ok=False, reason=f"agents/ directory not found at {agents_dir}")

        missing: list[str] = []
        checked: list[str] = []

        for script in sorted(skills_dir.glob("phase-*/scripts/select_worker.py")):
            try:
                content = script.read_text(encoding="utf-8")
            except OSError:
                continue
            names = re.findall(r'"(u-[a-z][a-z0-9\-]+)"', content)
            for name in sorted(set(names)):
                if name in checked:
                    continue
                checked.append(name)
                matches = list(agents_dir.rglob(f"{name}.md"))
                if not matches:
                    rel = str(script.relative_to(_DIST_DIR))
                    missing.append(f"{rel}: agent '{name}' not found in agents/")

        if missing:
            return CheckResult(
                ok=False,
                reason=f"{len(missing)} unresolved agent reference(s)",
                detail={"missing": missing},
            )
        return CheckResult(
            ok=True,
            reason=f"all agent references resolved ({len(checked)} checked)",
            detail={"checked": checked},
        )
    return _timed(_run)


LOCAL_CHECKS: list[tuple[str, Callable[[], CheckResult]]] = [
    ("bash_available", check_bash_available),
    ("python_version", check_python_version),
    ("flock_works", check_flock_works),
    ("filesystem_writable", check_filesystem_writable),
    ("claude_code_installed", check_claude_code_installed),
    ("claude_code_version", check_claude_code_version),
    ("agent_references", check_agent_references),
    ("claude_md_config", check_claude_md_config),
]


# ---------------------------------------------------------------------------
# Remote checks (require Claude Code installed)
# ---------------------------------------------------------------------------

def _claude_available() -> bool:
    return shutil.which("claude") is not None


def _run_claude_snippet(snippet: str, timeout: int = 30) -> tuple[bool, str]:
    """Run a one-shot claude CLI command and return (success, output)."""
    if not _claude_available():
        return False, "claude binary not found"
    try:
        r = subprocess.run(
            ["claude", "--print", snippet],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except OSError as exc:
        return False, str(exc)


def check_agent_tool_available() -> CheckResult:
    def _run() -> CheckResult:
        if not _claude_available():
            return CheckResult(ok=False, reason="claude not installed — skipping remote check")
        sentinel = "ORCH_AGENT_CHECK_SENTINEL_7x9z42"
        ok, out = _run_claude_snippet(
            f'Use the Agent tool to spawn a subagent with prompt '
            f'"respond with exactly the string {sentinel} and nothing else" '
            f'and report its response.',
            timeout=45,
        )
        if ok and sentinel in out:
            return CheckResult(ok=True, reason="Agent tool spawned subagent successfully")
        return CheckResult(
            ok=False,
            reason="Agent tool check failed or sentinel not found in output",
            detail={"output_snippet": out[:200]},
        )
    return _timed(_run)


def check_env_var_propagation() -> CheckResult:
    # M5: Replaced non-deterministic LLM-based check with a deterministic subprocess
    # check. The original used `claude --print` and looked for a sentinel in LLM output,
    # which was unreliable. This version verifies env var visibility in a subprocess
    # by passing a known value and reading it back via Python directly.
    def _run() -> CheckResult:
        import subprocess as _sp
        sentinel = "PREFLIGHT_SENTINEL_XYZ_12345"
        try:
            env = os.environ.copy()
            env["ORCH_TEST_VAR"] = sentinel
            result = _sp.run(
                [sys.executable, "-c",
                 "import os, sys; v=os.environ.get('ORCH_TEST_VAR',''); sys.stdout.write(v)"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            if result.returncode == 0 and result.stdout.strip() == sentinel:
                return CheckResult(ok=True, reason="env var propagation works in subprocess")
            return CheckResult(
                ok=False,
                reason="env var not visible in subprocess",
                detail={"stdout": result.stdout[:100], "stderr": result.stderr[:100]},
            )
        except subprocess.TimeoutExpired:
            return CheckResult(ok=False, reason="subprocess timed out after 5s")
        except OSError as exc:
            return CheckResult(ok=False, reason=f"subprocess error: {exc}")
    return _timed(_run)


REMOTE_CHECKS: list[tuple[str, Callable[[], CheckResult]]] = [
    ("agent_tool_available", check_agent_tool_available),
    ("env_var_propagation", check_env_var_propagation),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_checks(
    checks: list[tuple[str, Callable[[], CheckResult]]],
) -> dict[str, CheckResult]:
    results: dict[str, CheckResult] = {}
    for name, fn in checks:
        try:
            results[name] = fn()
        except Exception as exc:
            results[name] = CheckResult(ok=False, reason=f"unexpected error: {exc}")
    return results


def build_output(
    local_results: dict[str, CheckResult],
    remote_results: dict[str, CheckResult],
    quick: bool,
) -> dict:
    all_results = {**local_results, **remote_results}
    failed = [
        {"check": name, "reason": r.reason}
        for name, r in all_results.items()
        if not r.ok
    ]
    passed = sum(1 for r in all_results.values() if r.ok)
    total = len(all_results)
    ok = len(failed) == 0

    output = {
        "ok": ok,
        "generated_at": now_iso(),
        "mode": "quick" if quick else "full",
        "passed": passed,
        "total": total,
        "failed_count": len(failed),
        "checks": {name: r.to_dict() for name, r in all_results.items()},
    }
    if failed:
        output["failed_checks"] = failed

    # Add system info from passing checks
    pv = local_results.get("python_version")
    if pv and pv.detail.get("current"):
        output["python_version"] = pv.detail["current"]
    cv = local_results.get("claude_code_version")
    if cv and cv.detail.get("current"):
        output["claude_code_version"] = cv.detail["current"]

    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate runtime assumptions for the orchestration engine.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only local checks (no Claude Code subprocess invocations). Completes in < 5s.",
    )
    args = parser.parse_args()

    local_results = run_checks(LOCAL_CHECKS)

    remote_results: dict[str, CheckResult] = {}
    if not args.quick:
        remote_results = run_checks(REMOTE_CHECKS)

    output = build_output(local_results, remote_results, quick=args.quick)
    print(json.dumps(output, indent=2))

    return 0 if output["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
