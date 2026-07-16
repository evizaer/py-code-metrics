#!/usr/bin/env python3
"""Compare two py-code-metrics JSON reports for self-analysis gates.

Thin wrapper around ``py_code_metrics.compare`` / ``py-code-metrics diff``.

Usage:
  uv run py-code-metrics analyze src/py_code_metrics > /tmp/pcm-after.json
  uv run python scripts/compare_self_metrics.py /tmp/pcm-before.json /tmp/pcm-after.json

Prefer:
  uv run py-code-metrics diff /tmp/pcm-before.json /tmp/pcm-after.json
  uv run py-code-metrics diff --json /tmp/pcm-before.json /tmp/pcm-after.json

Exit codes:
  0 — no unpaid-hotspot / max_v_poly regression (or only accepted noise)
  1 — regression on gated signals
  2 — usage / IO error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from py_code_metrics.compare import compare, load_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="Baseline metrics JSON")
    parser.add_argument("after", type=Path, help="New metrics JSON")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit compact JSON gate envelope instead of text",
    )
    args = parser.parse_args(argv)
    try:
        before = load_report(args.before)
        after = load_report(args.after)
    except OSError as exc:
        print(f"IO error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"IO error: invalid JSON: {exc}", file=sys.stderr)
        return 2
    code, lines, diff_dict = compare(before, after)
    if args.json:
        print(json.dumps(diff_dict, indent=2))
    else:
        print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
