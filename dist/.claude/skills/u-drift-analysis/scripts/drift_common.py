#!/usr/bin/env python3
"""Shared deterministic helpers for the u-drift-analysis scripts.

Zero external dependencies (stdlib + the bundled minimal_yaml loader only).
Every function here is pure and order-independent so the drift pipeline is
byte-for-byte reproducible: same inputs -> identical outputs.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# HTTP methods recognized on an OpenAPI path item.
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# Directories never treated as spec/code content.
IGNORED_DIR_PARTS = frozenset(
    {"_temp", "_validation", "_meta", "node_modules", ".git", "dist", "build", "__pycache__"}
)


def normalize_path(raw: str) -> str:
    """Normalize an HTTP route for side-independent matching (plan R6).

    Rules (deterministic, single-side — no knowledge of the other inventory):
      - drop query string and fragment
      - every path parameter segment collapses to the literal `{param}`
        (`:id`, `{id}`, `<id>` all become `{param}` — names are ignored so a
        spec `{id}` matches a code `:userId`)
      - trailing slash removed; empty path becomes `/`
    """
    if not raw:
        return "/"
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    out: list[str] = []
    for seg in raw.split("/"):
        if seg == "":
            continue
        if (
            seg.startswith(":")
            or (seg.startswith("{") and seg.endswith("}"))
            or (seg.startswith("<") and seg.endswith(">"))
        ):
            out.append("{param}")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def strip_base_path(path: str, base_path: str) -> str:
    """Remove a router prefix from a normalized path. Returns `/` if the strip
    consumes the whole path. No-op when base_path is empty or absent."""
    if not base_path:
        return path
    base = normalize_path(base_path)
    if base != "/" and path.startswith(base):
        rest = path[len(base):]
        return rest if rest else "/"
    return path


def endpoint_key(method: str, path: str) -> str:
    """Canonical match key for an endpoint: `{method} {normalized_path}`."""
    return f"{method.lower()} {normalize_path(path)}"


def coerce_status_code(raw) -> int | None:
    """Extract an integer HTTP status from an OpenAPI response key such as
    `"201"`, `201`, or `2XX`. Returns None when no concrete code is present."""
    digits = re.findall(r"\d+", str(raw))
    if not digits:
        return None
    token = digits[0]
    if len(token) != 3:
        return None
    return int(token)


def sha256_of_files(files: list[Path], base_dir: Path | None = None) -> str:
    """SHA-256 over the CRLF-normalized concatenation of the given files,
    processed in sorted path order. Deterministic content fingerprint used as
    the staleness guard (spec_content_hash).

    Path components are recorded RELATIVE to base_dir (when given) so the hash is
    reproducible across checkouts / install locations — identical content under a
    different absolute path yields the same hash. Falls back to the absolute path
    only when a file is not under base_dir.
    """
    def _key(p: Path) -> str:
        if base_dir is not None:
            try:
                return str(p.relative_to(base_dir)).replace("\\", "/")
            except ValueError:
                pass
        return str(p).replace("\\", "/")

    h = hashlib.sha256()
    for f in sorted(files, key=_key):
        try:
            data = f.read_bytes()
        except OSError:
            continue
        # Normalize CRLF -> LF so Windows/Unix checkouts hash identically.
        data = data.replace(b"\r\n", b"\n")
        h.update(_key(f).encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest()


def parse_markdown_tables(lines: list[str]) -> list[list[list[str]]]:
    """Return every pipe-delimited table in `lines` as a list of tables, each a
    list of rows, each row a list of trimmed cell strings. The separator row
    (`|---|---|`) is dropped. Header row is kept as the first row."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= {"-", ":", " "} and c for c in cells):
                continue  # separator row
            current.append(cells)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def section_lines(text: str, header_regex: str) -> list[str]:
    """Return the lines belonging to the first `##`-level section whose header
    matches `header_regex`, up to the next `##` header (exclusive). Empty list
    when the section is absent."""
    lines = text.splitlines()
    pat = re.compile(header_regex)
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = bool(pat.search(line))
            continue
        if inside:
            out.append(line)
    return out


# Deterministic ordering for findings (shared by match_drift and merge_semantic).
STATUS_ORDER = {"missing_in_code": 0, "missing_in_spec": 1, "drifted": 2, "undecidable": 3}
TYPE_ORDER = {
    "base_path": 0, "endpoint": 1, "entity_field": 2, "state_machine": 3,
    "event": 4, "error_code": 5, "business_rule": 6,
}


def finalize_findings(findings: list[dict]) -> list[dict]:
    """Sort findings deterministically and assign stable sequential DRIFT ids."""
    ordered = sorted(
        findings,
        key=lambda x: (
            x["domain"],
            STATUS_ORDER.get(x["status"], 9),
            TYPE_ORDER.get(x["artifact_type"], 9),
            x["artifact_ref"],
        ),
    )
    out = []
    for i, f in enumerate(ordered, start=1):
        body = {k: v for k, v in f.items() if k != "id"}
        out.append({"id": f"DRIFT-{i:03d}", **body})
    return out


def recount(findings: list[dict], aligned: list, skipped: list, domains_analyzed: int) -> dict:
    """Recompute the drift-report summary from the current finding set."""
    return {
        "domains_analyzed": domains_analyzed,
        "aligned": len(aligned),
        "drifted": sum(1 for f in findings if f["status"] == "drifted"),
        "missing_in_code": sum(1 for f in findings if f["status"] == "missing_in_code"),
        "missing_in_spec": sum(1 for f in findings if f["status"] == "missing_in_spec"),
        "undecidable": sum(1 for f in findings if f["status"] == "undecidable"),
        "skipped_draft": sum(1 for s in skipped if s["reason"] == "draft_status"),
    }


def finding_key(f: dict) -> tuple:
    """Dedupe key for a finding: (domain, status, artifact_type, artifact_ref)."""
    return (f["domain"], f["status"], f["artifact_type"], f["artifact_ref"])


def extract_status(text: str) -> str:
    """Extract the lowercase Status token from a spec header line
    (`> Version: ... | Status: approved | Layer: ...`). Returns 'unknown' when
    absent. The first word after `Status:` is taken, so a real single-value
    header yields that value; template placeholders yield their first option."""
    m = re.search(r"Status:\s*([A-Za-z_]+)", text)
    return m.group(1).lower() if m else "unknown"
