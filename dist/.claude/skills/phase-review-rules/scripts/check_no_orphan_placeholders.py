#!/usr/bin/env python3
"""
check_no_orphan_placeholders.py — Exit criterion: review / no_orphan_placeholders.

SIEGARD Rec #2 (R2). A Task Contract may legitimately ship a placeholder/stub whose
contract is "a later TC swaps the inner content". The framework split that left the
placeholder owned by one TC and its replacement owned by another — with no TC owning
the *composition* — produced a green, QA-"approved", non-functional entry surface
(`/curation` rendered the literal strings "Painel de decisão em construção" and
"A trilha de evidência aparecerá aqui" while 1006 FE unit tests were green).

Per-TC, spec/mock-bound QA cannot see this: the leftover placeholder is "someone
else's TC". This gate is the cross-cutting, deterministic net — it scans the delivered
source surface for incomplete-work markers and BLOCKS phase exit if any remain.

Criterion met when:
  - No scanned source file contains a placeholder/incomplete-work marker.

Detection is a case-insensitive line scan over source files under the configured
scan roots. Markers are deliberately high-signal idioms that do not appear in clean
production code; the set is overridable so projects tune false positives.

Scope is intentionally restricted so the gate is fast and low-noise:
  - Only source extensions (configurable) are read.
  - Test files (*.test.*, *.spec.*, __tests__/, /tests/) are skipped — a stub inside
    a fixture is not a shipped surface.
  - Vendored/build/runtime dirs (node_modules, dist, build, .orch, ...) are skipped.

Configuration (all optional; env vars, comma-separated where a list):
  ORCH_PROJECT_DIR              project root (default: ".")
  ORCH_PLACEHOLDER_SCAN_PATHS   scan roots relative to project (default: the common
                                source roots that exist — src, frontend/src, ...).
  ORCH_PLACEHOLDER_MARKERS      REPLACES the default marker set.
  ORCH_PLACEHOLDER_EXTRA_MARKERS  ADDS to the default marker set.
  ORCH_PLACEHOLDER_EXTENSIONS   REPLACES the default source-extension set.

Fail-open on empty scope: if no source file is in scope (no configured/known root
exists), the criterion is met with scanned=0 — the gate is additive and never breaks
a pipeline that simply has nothing to scan.

Output (exit 0):
    {"criterion": "no_orphan_placeholders", "met": bool, "evidence": {...}}
Output (exit 1):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import now_iso
except ImportError as exc:  # pragma: no cover - import guard mirrors sibling gates
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "no_orphan_placeholders"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))

# High-signal incomplete-work idioms. Each is matched case-insensitively as a
# substring of a single line, so file:line is reportable. Curated to NOT trip on
# clean production code; projects extend via ORCH_PLACEHOLDER_EXTRA_MARKERS.
_DEFAULT_MARKERS = [
    "em construção",
    "em construcao",
    "aparecerá aqui",
    "aparecera aqui",
    "swaps the inner content",
    "todo: tc-",
    "todo(tc-",
    "todo tc-",
    "fixme: tc-",
    "placeholder component",
    "out of scope (tc-",
    "wire later",
    "wire-later",
]

_DEFAULT_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".py", ".go", ".rb", ".java", ".kt", ".cs", ".php", ".rs", ".swift",
}

# Common source roots probed when ORCH_PLACEHOLDER_SCAN_PATHS is unset.
_DEFAULT_ROOTS = ["src", "frontend/src", "backend/src", "app/src", "app", "lib", "packages"]

_EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "build", "out", "coverage", ".orch",
    "vendor", "__pycache__", ".next", ".nuxt", ".svelte-kit", ".turbo",
    "specs", "target", ".venv", "venv",
}

_TEST_SEGMENTS = ("__tests__", "/tests/", "/test/", "/__mocks__/")
_TEST_INFIXES = (".test.", ".spec.")
_MAX_BYTES = 1_000_000  # skip very large files — a stub never lives in a 1 MB blob


def _csv_env(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _markers() -> list[str]:
    override = _csv_env("ORCH_PLACEHOLDER_MARKERS")
    base = override if override else list(_DEFAULT_MARKERS)
    base.extend(_csv_env("ORCH_PLACEHOLDER_EXTRA_MARKERS"))
    # Normalise to lowercase once; comparison is against a lowercased line.
    return [m.lower() for m in base]


def _extensions() -> set[str]:
    override = _csv_env("ORCH_PLACEHOLDER_EXTENSIONS")
    if not override:
        return set(_DEFAULT_EXTENSIONS)
    return {e if e.startswith(".") else f".{e}" for e in (x.lower() for x in override)}


def _scan_roots() -> list[Path]:
    configured = _csv_env("ORCH_PLACEHOLDER_SCAN_PATHS")
    names = configured if configured else _DEFAULT_ROOTS
    roots = []
    for name in names:
        candidate = (_PROJECT_DIR / name).resolve()
        if candidate.is_dir():
            roots.append(candidate)
    return roots


def _is_test_path(rel: str) -> bool:
    low = rel.lower().replace("\\", "/")
    if any(seg in f"/{low}/" for seg in _TEST_SEGMENTS):
        return True
    return any(infix in low for infix in _TEST_INFIXES)


def _iter_source_files(root: Path, extensions: set[str]):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in extensions:
            continue
        yield path


def evaluate() -> dict:
    markers = _markers()
    extensions = _extensions()
    roots = _scan_roots()

    scanned = 0
    hits = []
    seen_files = set()

    for root in roots:
        for path in _iter_source_files(root, extensions):
            if path in seen_files:  # roots may nest — never scan a file twice
                continue
            seen_files.add(path)
            try:
                rel = str(path.relative_to(_PROJECT_DIR))
            except ValueError:
                rel = str(path)
            if _is_test_path(rel):
                continue
            try:
                if path.stat().st_size > _MAX_BYTES:
                    continue
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scanned += 1
            for lineno, line in enumerate(content.splitlines(), start=1):
                low = line.lower()
                for marker in markers:
                    if marker in low:
                        hits.append({
                            "file": rel,
                            "line": lineno,
                            "marker": marker,
                            "text": line.strip()[:200],
                        })

    return {
        "criterion": CRITERION_ID,
        "met": len(hits) == 0,
        "evidence": {
            "scanned": scanned,
            "roots": [str(r.relative_to(_PROJECT_DIR)) if r.is_relative_to(_PROJECT_DIR) else str(r) for r in roots],
            "markers": markers,
            "hits": hits,
        },
    }


def main() -> None:
    result = evaluate()
    # Uniform gate schema — emit the full superset (matches sibling review gates).
    result.setdefault("check", result.get("criterion"))
    result.setdefault("status", "ok" if result.get("met") else "blocked")
    result.setdefault("timestamp", now_iso())
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — mirror sibling gates' fail-loud contract
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
