#!/usr/bin/env python3
"""check_br_pairs.py — BR pair discipline between .spec.md and .back.md.

`.spec.md` is the single normative source for WHAT each business rule is; a
`.back.md` BR cites its source BR and declares only HOW the rule is enforced
(TEMPLATE.back.md §3). This script makes that contract mechanical:

- blocking `missing_source_citation` — a back BR has no `Source rule` citation
  (`{domain}.spec.md BR-NN`). Without the citation, restatement is untraceable
  and cross-file validators silently compare unrelated rules.
- blocking `unresolved_citation` — the cited BR-NN does not exist in the
  domain's .spec.md.
- warning `restatement_suspected` — the back BR body reproduces the cited spec
  BR body above a word-overlap threshold. Same-language heuristic only:
  cross-language duplicates score near zero (measured 0-23% on real duplicated
  pairs), which is exactly why the citation — not similarity — is the contract.

Exit codes (mirrors verify_evidence.py): 0 = no blocking violations,
2 = at least one blocking violation, 1 = script/usage error.

Usage:
  python3 check_br_pairs.py --specs-dir docs/specs [--domain <name>] [--json]

Zero external dependencies — stdlib 3.10+ only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SPEC_BR_RE = re.compile(r"^###\s+BR-(\d+)", re.M)
BACK_BR_RE = re.compile(r"^###\s+((?:BE-BR|BR-BE|BR)-\d+)", re.M)
CITATION_RE = re.compile(
    r"(?:\*\*Source rule:\*\*|(?:\bsee\b|\bver\b))[^\n]*?\.spec\.md[^\n]*?BR-(\d+)",
    re.I,
)
WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")

OVERLAP_THRESHOLD = 0.6
MIN_SPEC_WORDS = 12


def _blocks(text: str, heading_re: re.Pattern) -> dict:
    """Map BR id -> body text (heading to next ###/## heading)."""
    out = {}
    matches = list(heading_re.finditer(text))
    boundaries = [m.start() for m in re.finditer(r"^#{2,3}\s", text, re.M)] + [len(text)]
    for m in matches:
        end = min(b for b in boundaries if b > m.start())
        out[m.group(1)] = text[m.start():end]
    return out


def _content_words(text: str) -> set:
    return {w.lower() for w in WORD_RE.findall(text)}


def check_domain(domain_dir: Path) -> tuple[list, int]:
    domain = domain_dir.name
    spec_path = domain_dir / f"{domain}.spec.md"
    back_candidates = sorted(domain_dir.glob(f"**/{domain}.back.md"))
    if not spec_path.is_file() or not back_candidates:
        return [], 0

    spec_text = spec_path.read_text(encoding="utf-8", errors="replace")
    spec_brs = _blocks(spec_text, SPEC_BR_RE)
    violations = []
    checked = 0

    for back_path in back_candidates:
        back_text = back_path.read_text(encoding="utf-8", errors="replace")
        for back_id, body in _blocks(back_text, BACK_BR_RE).items():
            checked += 1
            cite = CITATION_RE.search(body)
            if not cite:
                violations.append({
                    "domain": domain,
                    "back_br": back_id,
                    "type": "missing_source_citation",
                    "severity": "blocking",
                    "detail": f"{back_path.name} {back_id} has no `Source rule` citation "
                              f"({domain}.spec.md BR-NN)",
                })
                continue
            cited = cite.group(1)
            if cited not in spec_brs:
                violations.append({
                    "domain": domain,
                    "back_br": back_id,
                    "type": "unresolved_citation",
                    "severity": "blocking",
                    "detail": f"{back_path.name} {back_id} cites BR-{cited}, "
                              f"not present in {spec_path.name}",
                })
                continue
            spec_words = _content_words(spec_brs[cited])
            if len(spec_words) >= MIN_SPEC_WORDS:
                overlap = len(spec_words & _content_words(body)) / len(spec_words)
                if overlap >= OVERLAP_THRESHOLD:
                    violations.append({
                        "domain": domain,
                        "back_br": back_id,
                        "type": "restatement_suspected",
                        "severity": "warning",
                        "detail": f"{back_path.name} {back_id} reproduces "
                                  f"{overlap:.0%} of BR-{cited} content words — "
                                  f"describe HOW it is enforced, not WHAT it is",
                    })
    return violations, checked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs-dir", required=True)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)

    domains_root = Path(args.specs_dir) / "domains"
    if not domains_root.is_dir():
        print(json.dumps({"status": "error",
                          "reason": f"not a directory: {domains_root}"}))
        return 1

    domain_dirs = ([domains_root / args.domain] if args.domain
                   else sorted(p for p in domains_root.iterdir() if p.is_dir()))
    all_violations, total_checked, checked_domains = [], 0, []
    for d in domain_dirs:
        if not d.is_dir():
            print(json.dumps({"status": "error", "reason": f"no such domain: {d.name}"}))
            return 1
        v, n = check_domain(d)
        if n:
            checked_domains.append(d.name)
        all_violations.extend(v)
        total_checked += n

    blocking = [v for v in all_violations if v["severity"] == "blocking"]
    print(json.dumps({
        "status": "fail" if blocking else "ok",
        "checked_domains": checked_domains,
        "brs_checked": total_checked,
        "blocking": len(blocking),
        "warnings": len(all_violations) - len(blocking),
        "violations": all_violations,
    }, ensure_ascii=False, indent=2))
    return 2 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
