#!/usr/bin/env python3
"""Compare two py-code-metrics JSON reports for self-analysis gates (§11.5).

Usage:
  uv run py-code-metrics src/py_code_metrics > /tmp/pcm-after.json
  uv run python scripts/compare_self_metrics.py /tmp/pcm-before.json /tmp/pcm-after.json

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
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _complexity(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("overall", {}).get("complexity", {})


def _etspa(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("overall", {}).get("etspa", {})


def _hotspot_names(report: dict[str, Any]) -> set[str]:
    return {h["qualified_name"] for h in report.get("overall", {}).get("hotspots", [])}


def compare(before: dict[str, Any], after: dict[str, Any]) -> tuple[int, list[str]]:
    lines: list[str] = []
    bc, ac = _complexity(before), _complexity(after)
    be, ae = _etspa(before), _etspa(after)

    def row(label: str, b: Any, a: Any) -> None:
        lines.append(f"  {label}: {b} → {a}")

    lines.append("Complexity / hotspot board")
    for key in (
        "max_v_poly",
        "max_nesting",
        "mean_cyclomatic",
        "mean_cognitive",
        "n_v_poly_gt_15",
        "n_nesting_gt_3",
        "n_unpaid_v_poly_gt_15",
        "n_unpaid_nesting_gt_3",
        "n_unpaid_hotspots",
    ):
        if key in bc or key in ac:
            row(key, bc.get(key), ac.get(key))

    lines.append("ETSPA (global + helpers_cores)")
    row("sum_S", be.get("sum_S"), ae.get("sum_S"))
    row("frac_S_le_0", be.get("frac_S_le_0"), ae.get("frac_S_le_0"))
    row("frac_fan_in_le_1", be.get("frac_fan_in_le_1"), ae.get("frac_fan_in_le_1"))
    bh, ah = be.get("helpers_cores", {}), ae.get("helpers_cores", {})
    if bh or ah:
        row("helpers_cores.sum_S", bh.get("sum_S"), ah.get("sum_S"))
        row(
            "helpers_cores.frac_fan_in_le_1",
            bh.get("frac_fan_in_le_1"),
            ah.get("frac_fan_in_le_1"),
        )

    before_hs, after_hs = _hotspot_names(before), _hotspot_names(after)
    added = sorted(after_hs - before_hs)
    removed = sorted(before_hs - after_hs)
    if added:
        lines.append("New unpaid hotspots: " + ", ".join(added))
    if removed:
        lines.append("Cleared unpaid hotspots: " + ", ".join(removed))
    if not added and not removed and "hotspots" in before.get("overall", {}):
        lines.append("Unpaid hotspot set unchanged.")

    # Gate: unpaid hotspot count is primary (§11.2). max_v_poly is secondary and
    # ignored when the new corpus max is a paid and/or reduction_like symbol.
    failed = False
    b_hot = bc.get("n_unpaid_hotspots")
    a_hot = ac.get("n_unpaid_hotspots")
    if b_hot is not None and a_hot is not None and a_hot > b_hot:
        lines.append(f"FAIL: n_unpaid_hotspots rose ({b_hot} → {a_hot})")
        failed = True

    b_max, a_max = bc.get("max_v_poly"), ac.get("max_v_poly")
    if b_max is not None and a_max is not None and a_max > b_max:
        max_sym = _max_v_poly_symbol(after)
        if max_sym and (max_sym.get("unpaid") is False or max_sym.get("reduction_like")):
            lines.append(
                f"NOTE: max_v_poly rose ({b_max} → {a_max}) on "
                f"{max_sym.get('qualified_name')} "
                f"(unpaid={max_sym.get('unpaid')}, "
                f"reduction_like={max_sym.get('reduction_like')}) — not a gate failure."
            )
        else:
            lines.append(f"FAIL: max_v_poly rose ({b_max} → {a_max})")
            failed = True
    if not failed:
        lines.append("PASS: no rise in n_unpaid_hotspots or unpaid max_v_poly.")

    return (1 if failed else 0), lines


def _max_v_poly_symbol(report: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_v = -1
    for mod in report.get("modules", []):
        for fn in mod.get("functions", []):
            if fn.get("v_poly", 0) > best_v:
                best, best_v = fn, fn["v_poly"]
        for cls in mod.get("classes", []):
            for meth in cls.get("methods", []):
                if meth.get("v_poly", 0) > best_v:
                    best, best_v = meth, meth["v_poly"]
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="Baseline metrics JSON")
    parser.add_argument("after", type=Path, help="New metrics JSON")
    args = parser.parse_args(argv)
    try:
        before = _load(args.before)
        after = _load(args.after)
    except OSError as exc:
        print(f"IO error: {exc}", file=sys.stderr)
        return 2
    code, lines = compare(before, after)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
