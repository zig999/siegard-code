"""Minimal YAML-subset loader — stdlib only (prod-hardening task 03).

Replaces the pyyaml dependency in dist/ so the engine honors the project's
"zero external dependencies — stdlib 3.10+ only" invariant. Supports the YAML
subset that Siegard artifacts actually use:

  - block mappings: ``key: value``
  - block sequences: ``- item`` (scalars) and ``- key: value`` (lists of maps)
  - nesting by indentation
  - single/double-quoted and plain scalars
  - inline ``#`` comments (a ``#`` is a comment only when preceded by whitespace
    or at start of line — so URLs/hashes are preserved)
  - block scalars: ``>`` (folded) and ``|`` (literal)

Coercion is deliberately minimal: only ``true``/``false``/``null`` and plain
integers are coerced — everything else stays a string (so ``1.0.0`` versions and
sha256 hexes are preserved, and the pyyaml ``yes``/``no`` boolean footgun is
avoided). This is NOT a general YAML parser.
"""
from __future__ import annotations

import re

__all__ = ["load", "MinimalYAMLError"]

_INT_RE = re.compile(r"^-?\d+$")
_BLOCK_INDICATORS = frozenset({">", "|", ">-", "|-", ">+", "|+"})


class MinimalYAMLError(ValueError):
    """Raised when the input cannot be parsed by the minimal loader."""


def _strip_comment(s: str) -> str:
    """Removes an inline '#' comment. A '#' starts a comment only when preceded by
    whitespace or start-of-line, and never inside quotes."""
    out: list[str] = []
    quote: str | None = None
    prev = ""
    for ch in s:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and prev in ("", " ", "\t"):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _coerce(raw: str):
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    if s == "[]":
        return []
    if s == "{}":
        return {}
    low = s.lower()
    if low in ("null", "~", ""):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(s):
        return int(s)
    return s


class _Parser:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.i = 0
        self.n = len(lines)

    def _next_significant(self) -> int | None:
        j = self.i
        while j < self.n:
            if _strip_comment(self.lines[j]).strip() != "":
                return j
            j += 1
        return None

    def parse_node(self, min_indent: int):
        j = self._next_significant()
        if j is None:
            return None
        indent = _indent(self.lines[j])
        if indent < min_indent:
            return None
        self.i = j
        content = _strip_comment(self.lines[j]).strip()
        if content == "-" or content.startswith("- "):
            return self._parse_seq(indent)
        return self._parse_map(indent)

    def _parse_map(self, indent: int) -> dict:
        result: dict = {}
        while True:
            j = self._next_significant()
            if j is None:
                break
            if _indent(self.lines[j]) != indent:
                break
            content = _strip_comment(self.lines[j]).strip()
            if content == "-" or content.startswith("- "):
                break
            key, sep, val = content.partition(":")
            if not sep:
                break
            self.i = j + 1
            result[key.strip()] = self._value_for(val.strip(), indent)
        return result

    def _value_for(self, val: str, indent: int):
        if val in _BLOCK_INDICATORS:
            return self._consume_block_scalar(indent, val)
        if val == "":
            nxt = self._next_significant()
            if nxt is not None and _indent(self.lines[nxt]) > indent:
                return self.parse_node(indent + 1)
            return None
        return _coerce(val)

    def _parse_seq(self, indent: int) -> list:
        items: list = []
        while True:
            j = self._next_significant()
            if j is None:
                break
            cur = _indent(self.lines[j])
            if cur != indent:
                break
            content = _strip_comment(self.lines[j]).strip()
            if not (content == "-" or content.startswith("- ")):
                break
            after = content[1:].strip()
            self.i = j + 1
            if after == "":
                items.append(self.parse_node(indent + 1))
                continue
            key, sep, val = after.partition(":")
            if sep and after[0] not in ("'", '"'):
                child_indent = cur + 2
                item = {key.strip(): self._value_for(val.strip(), child_indent)}
                more = self._parse_map(child_indent)
                if more:
                    item.update(more)
                items.append(item)
            else:
                items.append(_coerce(after))
        return items

    def _consume_block_scalar(self, indent: int, indicator: str) -> str:
        folded = indicator[0] == ">"
        parts: list[str] = []
        while self.i < self.n:
            line = self.lines[self.i]
            if line.strip() == "":
                parts.append("")
                self.i += 1
                continue
            if _indent(line) <= indent:
                break
            parts.append(line.strip())
            self.i += 1
        joined = " ".join(parts) if folded else "\n".join(parts)
        return joined.strip()


def load(text: str):
    """Parses a YAML-subset document and returns dict | list | scalar | None."""
    if not isinstance(text, str):
        raise MinimalYAMLError(f"expected str, got {type(text).__name__}")
    return _Parser(text.split("\n")).parse_node(0)
