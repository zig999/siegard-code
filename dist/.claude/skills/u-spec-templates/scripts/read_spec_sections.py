#!/usr/bin/env python3
"""
read_spec_sections.py — Load the sections a worker needs, plus an index of the rest.

Spec workers list whole files as inputs, so every one of them carries every
section of every artifact. Measured on real runs: 51,701 and 57,213 estimated
tokens against a 60,000 block threshold — 86% to 95% of the ceiling, with the
`.back.md` (1,374–2,028 lines) the largest single item. That ceiling is why
`targeted` mode is capped at one concurrent worker, so context pressure is not
just cost: it is the reason the cheap path cannot be parallel.

**This does not delete anything.** The artifacts keep every section they have;
what changes is how much of them a given worker loads. The `.back.md` is not
redundant with the `.spec.md` — measured textual similarity between their
same-named sections is 7–11%, so it is a second layer, not a copy. Removing
content was never the available saving; reading less of it is.

The safety property that makes partial loading acceptable: **full awareness,
partial bodies.** Output always carries the complete section index — every
section's number and title, marked `requested` or `omitted`. A worker therefore
always knows what exists and can ask for more, which is a different situation
from silently not knowing a section is there.

Precedent in this framework: `u-spec-front` already splits the design system into
a directory so "downstream agents load only the sections relevant to each task".

Usage:
    python3 read_spec_sections.py --file <spec.md> --sections 1,4,5
    python3 read_spec_sections.py --file <spec.md> --sections "Business Rules"
    python3 read_spec_sections.py --file <spec.md> --index-only
    python3 read_spec_sections.py --file <spec.md> --all        # explicit opt-out

Selectors match a section by number (`4`), by number with dot (`4.`), by `§4`, or
by a case-insensitive substring of its title. Unmatched selectors are reported
rather than ignored — a silent miss would hand the worker less than it asked for.

Output (stdout, JSON, exit 0):
    {
      "file": "<path>",
      "total_sections": int,
      "index": [{"number": "1", "title": "...", "lines": int, "state": "requested|omitted"}],
      "requested": ["1", "4"],
      "unmatched_selectors": [],
      "content": "<the requested sections, verbatim, in file order>",
      "lines_loaded": int,
      "lines_total": int,
      "reduction_pct": int
    }

Exit codes:
    0  sections returned
    2  one or more selectors matched nothing (content still returned for the rest)
    1  usage/IO error
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Sections are level-2 headings. Numbered (`## 4. State Machine (ST)`) in every
# shipped template; unnumbered ones (`## Changelog`) are addressable by title.
_H2 = re.compile(r"^##\s+(?:(\d+)\.\s*)?(.+?)\s*$")


def parse_sections(text: str) -> tuple[list[dict], list[str]]:
    """Split into sections. Returns (sections, preamble_lines).

    The preamble — everything before the first `##` — holds the title and any
    status/version frontmatter, and is ALWAYS included: it is small and it is how
    a worker knows which artifact and which version it is looking at.
    """
    lines = text.splitlines()
    sections: list[dict] = []
    preamble: list[str] = []
    current: dict | None = None

    for line in lines:
        m = _H2.match(line)
        if m:
            if current:
                sections.append(current)
            current = {
                "number": m.group(1) or "",
                "title": m.group(2),
                "body": [line],
            }
            continue
        if current is None:
            preamble.append(line)
        else:
            current["body"].append(line)

    if current:
        sections.append(current)
    return sections, preamble


def _matches(section: dict, selector: str) -> bool:
    sel = selector.strip().lstrip("§").rstrip(".").strip()
    if not sel:
        return False
    if section["number"] and sel == section["number"]:
        return True
    return sel.lower() in section["title"].lower()


def select(text: str, selectors: list[str], take_all: bool = False) -> dict:
    sections, preamble = parse_sections(text)
    total_lines = len(text.splitlines())

    chosen: set[int] = set()
    unmatched: list[str] = []
    if take_all:
        chosen = set(range(len(sections)))
    else:
        for selector in selectors:
            hits = [i for i, s in enumerate(sections) if _matches(s, selector)]
            if not hits:
                unmatched.append(selector)
            chosen.update(hits)

    index = [
        {
            "number": s["number"] or None,
            "title": s["title"],
            "lines": len(s["body"]),
            "state": "requested" if i in chosen else "omitted",
        }
        for i, s in enumerate(sections)
    ]

    body_lines = list(preamble)
    for i, s in enumerate(sections):
        if i in chosen:
            body_lines.extend(s["body"])
    content = "\n".join(body_lines).strip() + "\n"
    loaded = len(content.splitlines())

    return {
        "total_sections": len(sections),
        "index": index,
        "requested": [sections[i]["number"] or sections[i]["title"]
                      for i in sorted(chosen)],
        "unmatched_selectors": unmatched,
        "content": content,
        "lines_loaded": loaded,
        "lines_total": total_lines,
        "reduction_pct": (
            int(round(100 * (1 - loaded / total_lines))) if total_lines else 0
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--sections", default="",
                    help="comma-separated selectors: numbers (4), §4, or title text")
    ap.add_argument("--index-only", action="store_true",
                    help="return the section index with no bodies")
    ap.add_argument("--all", action="store_true",
                    help="load every section — explicit opt-out of scoping")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(json.dumps({
            "status": "error", "reason": "file_not_found", "detail": str(path),
        }), file=sys.stderr)
        sys.exit(1)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(json.dumps({
            "status": "error", "reason": "unreadable", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)

    selectors = [s for s in (args.sections or "").split(",") if s.strip()]
    if not selectors and not args.all and not args.index_only:
        print(json.dumps({
            "status": "error", "reason": "no_selectors",
            "detail": "pass --sections, --index-only, or --all",
        }), file=sys.stderr)
        sys.exit(1)

    result = select(text, selectors, take_all=args.all)
    result["file"] = str(path)
    if args.index_only:
        result["content"] = ""
        result["lines_loaded"] = 0
        result["reduction_pct"] = 100
    print(json.dumps(result))
    sys.exit(2 if result["unmatched_selectors"] else 0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
