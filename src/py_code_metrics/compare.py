"""Compare two structural metrics reports for self-analysis gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from py_code_metrics.views import iter_callables


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def complexity(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("overall", {}).get("complexity", {})


def etspa(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("overall", {}).get("etspa", {})


def hotspot_names(report: dict[str, Any]) -> set[str]:
    return {h["qualified_name"] for h in report.get("overall", {}).get("hotspots", [])}


def max_v_poly_symbol(report: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_v = -1
    for _path, fn in iter_callables(report):
        v = fn.get("v_poly", 0)
        if v > best_v:
            best, best_v = fn, v
    return best


_COMPLEXITY_KEYS = (
    "max_v_poly",
    "max_nesting",
    "mean_cyclomatic",
    "mean_cognitive",
    "n_v_poly_gt_15",
    "n_nesting_gt_3",
    "n_unpaid_v_poly_gt_15",
    "n_unpaid_nesting_gt_3",
    "n_unpaid_hotspots",
)


def _row(lines: list[str], label: str, before: Any, after: Any) -> None:
    lines.append(f"  {label}: {before} → {after}")


def _collect_complexity_deltas(
    lines: list[str],
    deltas: dict[str, list[Any]],
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    lines.append("Complexity / hotspot board")
    for key in _COMPLEXITY_KEYS:
        if key in before or key in after:
            _row(lines, key, before.get(key), after.get(key))
            deltas[key] = [before.get(key), after.get(key)]


def _collect_etspa_deltas(
    lines: list[str],
    deltas: dict[str, list[Any]],
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    lines.append("ETSPA (global + helpers_cores)")
    for key in ("sum_S", "frac_S_le_0", "frac_fan_in_le_1"):
        _row(lines, key, before.get(key), after.get(key))
        deltas[key] = [before.get(key), after.get(key)]
    bh, ah = before.get("helpers_cores", {}), after.get("helpers_cores", {})
    if not (bh or ah):
        return
    _row(lines, "helpers_cores.sum_S", bh.get("sum_S"), ah.get("sum_S"))
    _row(
        lines,
        "helpers_cores.frac_fan_in_le_1",
        bh.get("frac_fan_in_le_1"),
        ah.get("frac_fan_in_le_1"),
    )
    deltas["helpers_cores.sum_S"] = [bh.get("sum_S"), ah.get("sum_S")]
    deltas["helpers_cores.frac_fan_in_le_1"] = [
        bh.get("frac_fan_in_le_1"),
        ah.get("frac_fan_in_le_1"),
    ]


def _hotspot_set_lines(
    lines: list[str], before: dict[str, Any], after: dict[str, Any]
) -> tuple[list[str], list[str]]:
    before_hs, after_hs = hotspot_names(before), hotspot_names(after)
    added = sorted(after_hs - before_hs)
    removed = sorted(before_hs - after_hs)
    if added:
        lines.append("New unpaid hotspots: " + ", ".join(added))
    if removed:
        lines.append("Cleared unpaid hotspots: " + ", ".join(removed))
    if not added and not removed and "hotspots" in before.get("overall", {}):
        lines.append("Unpaid hotspot set unchanged.")
    return added, removed


def _gate_hotspot_count(
    lines: list[str], failures: list[str], before_c: dict[str, Any], after_c: dict[str, Any]
) -> bool:
    b_hot = before_c.get("n_unpaid_hotspots")
    a_hot = after_c.get("n_unpaid_hotspots")
    if b_hot is not None and a_hot is not None and a_hot > b_hot:
        msg = f"n_unpaid_hotspots rose ({b_hot} → {a_hot})"
        lines.append(f"FAIL: {msg}")
        failures.append(msg)
        return True
    return False


def _gate_max_v_poly(
    lines: list[str],
    failures: list[str],
    before_c: dict[str, Any],
    after_c: dict[str, Any],
    after: dict[str, Any],
) -> bool:
    b_max, a_max = before_c.get("max_v_poly"), after_c.get("max_v_poly")
    if b_max is None or a_max is None or a_max <= b_max:
        return False
    max_sym = max_v_poly_symbol(after)
    if max_sym and (max_sym.get("unpaid") is False or max_sym.get("reduction_like")):
        lines.append(
            f"NOTE: max_v_poly rose ({b_max} → {a_max}) on "
            f"{max_sym.get('qualified_name')} "
            f"(unpaid={max_sym.get('unpaid')}, "
            f"reduction_like={max_sym.get('reduction_like')}) — not a gate failure."
        )
        return False
    msg = f"max_v_poly rose ({b_max} → {a_max})"
    lines.append(f"FAIL: {msg}")
    failures.append(msg)
    return True


def compare(before: dict[str, Any], after: dict[str, Any]) -> tuple[int, list[str], dict[str, Any]]:
    """Return (exit_code, text_lines, diff_dict).

    Exit 0 = pass, 1 = gated regression.
    Text lines stay verbose; JSON deltas stay gate-focused and compact.
    """
    lines: list[str] = []
    failures: list[str] = []
    text_deltas: dict[str, list[Any]] = {}
    bc, ac = complexity(before), complexity(after)
    be, ae = etspa(before), etspa(after)

    _collect_complexity_deltas(lines, text_deltas, bc, ac)
    _collect_etspa_deltas(lines, text_deltas, be, ae)
    added, removed = _hotspot_set_lines(lines, before, after)

    failed = _gate_hotspot_count(lines, failures, bc, ac)
    failed = _gate_max_v_poly(lines, failures, bc, ac, after) or failed
    if not failed:
        lines.append("PASS: no rise in n_unpaid_hotspots or unpaid max_v_poly.")

    bh, ah = be.get("helpers_cores", {}), ae.get("helpers_cores", {})
    compact_deltas = {
        "n_unpaid_hotspots": [bc.get("n_unpaid_hotspots"), ac.get("n_unpaid_hotspots")],
        "max_v_poly": [bc.get("max_v_poly"), ac.get("max_v_poly")],
        "helpers_cores.sum_S": [bh.get("sum_S"), ah.get("sum_S")],
        "helpers_cores.frac_fan_in_le_1": [
            bh.get("frac_fan_in_le_1"),
            ah.get("frac_fan_in_le_1"),
        ],
    }
    diff_dict: dict[str, Any] = {
        "version": 1,
        "view": "diff",
        "pass": not failed,
        "failures": failures,
        "deltas": compact_deltas,
        "hotspots_added": added,
        "hotspots_removed": removed,
    }
    return (1 if failed else 0), lines, diff_dict
