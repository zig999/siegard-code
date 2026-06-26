#!/usr/bin/env python3
"""
check_suite_freshness.py — Decide whether the current suite_run can be reused
or a new one must be triggered.

The orchestrator computes a signature over (active review tasks, their
attempts, the SHA-256 of each delivery file) and compares against the
signature stored in the current run's manifest. If anything changed (new TC,
retry round, redelivery) the run is stale.

Usage:
    python3 check_suite_freshness.py \
      --session-dir <abs path to .orch/sessions/<wf>> \
      --project-dir <abs path> \
      --tasks '<JSON list: [{"task_id":"...","attempts":N,"delivery_path":"..."}]>'

Output (stdout, exit 0):
    {
      "fresh": bool,
      "reason": "<text>",
      "current_sr_id": "sr-N"|null,
      "next_sr_id": "sr-(N+1)",
      "signature": "<hex>"
    }

Exit 1 only on internal error; "no current run" returns fresh=false with
current_sr_id=null and reason="no_current_run".
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def _compute_signature(tasks: list[dict], project_dir: Path) -> str:
    h = hashlib.sha256()
    # Sort for determinism
    for entry in sorted(tasks, key=lambda x: x.get("task_id", "")):
        tid = entry.get("task_id", "")
        attempts = int(entry.get("attempts", 0) or 0)
        delivery_rel = entry.get("delivery_path", "") or ""
        h.update(tid.encode("utf-8"))
        h.update(b"|")
        h.update(str(attempts).encode("utf-8"))
        h.update(b"|")
        h.update(delivery_rel.encode("utf-8"))
        h.update(b"|")
        delivery_abs = project_dir / delivery_rel if delivery_rel else None
        if delivery_abs and delivery_abs.exists():
            try:
                h.update(hashlib.sha256(delivery_abs.read_bytes()).digest())
            except OSError:
                h.update(b"<unreadable>")
        else:
            h.update(b"<missing>")
        h.update(b"\n")
    return h.hexdigest()


_SR_RE = re.compile(r"^sr-(\d+)$")


def _next_sr_id(suite_run_root: Path, current_sr_id: str | None) -> str:
    """Pick sr-(max(existing)+1). Falls back to sr-1 when nothing exists."""
    max_n = 0
    if suite_run_root.exists():
        for entry in suite_run_root.iterdir():
            if not entry.is_dir():
                continue
            m = _SR_RE.match(entry.name)
            if m:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
    if current_sr_id:
        m = _SR_RE.match(current_sr_id)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"sr-{max_n + 1}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-dir", required=True)
    ap.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--tasks", required=True,
                    help='JSON list: [{"task_id":"...","attempts":N,"delivery_path":"..."}]')
    args = ap.parse_args()

    session_dir = Path(args.session_dir).resolve()
    project_dir = Path(args.project_dir).resolve()

    try:
        tasks = json.loads(args.tasks)
        if not isinstance(tasks, list):
            raise ValueError("tasks must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "status": "error", "reason": "bad_tasks", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)

    signature = _compute_signature(tasks, project_dir)
    suite_run_root = session_dir / "qa" / "_suite-run"
    current_pointer = suite_run_root / "current.txt"

    current_sr_id: str | None = None
    if current_pointer.exists():
        try:
            current_sr_id = current_pointer.read_text(encoding="utf-8").strip() or None
        except OSError:
            current_sr_id = None

    if not current_sr_id:
        print(json.dumps({
            "fresh": False,
            "reason": "no_current_run",
            "current_sr_id": None,
            "next_sr_id": _next_sr_id(suite_run_root, None),
            "signature": signature,
        }))
        return

    manifest_path = suite_run_root / current_sr_id / "manifest.json"
    if not manifest_path.exists():
        print(json.dumps({
            "fresh": False,
            "reason": "manifest_missing",
            "current_sr_id": current_sr_id,
            "next_sr_id": _next_sr_id(suite_run_root, current_sr_id),
            "signature": signature,
        }))
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "fresh": False,
            "reason": f"manifest_unreadable:{exc}",
            "current_sr_id": current_sr_id,
            "next_sr_id": _next_sr_id(suite_run_root, current_sr_id),
            "signature": signature,
        }))
        return

    stored_sig = ((manifest.get("scope") or {}).get("signature") or "")
    if stored_sig == signature:
        print(json.dumps({
            "fresh": True,
            "reason": "signature_match",
            "current_sr_id": current_sr_id,
            "next_sr_id": _next_sr_id(suite_run_root, current_sr_id),
            "signature": signature,
        }))
        return

    print(json.dumps({
        "fresh": False,
        "reason": "signature_mismatch",
        "current_sr_id": current_sr_id,
        "next_sr_id": _next_sr_id(suite_run_root, current_sr_id),
        "signature": signature,
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
