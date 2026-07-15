"""Compare two structural metrics reports for self-analysis gates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from py_code_metrics.model import CallableMetrics, ComplexityBoard, EtspaOverall, MetricsReport
from py_code_metrics.views import iter_callables


@dataclass
class DiffDeltas:
    n_unpaid_hotspots: list[int]
    max_v_poly: list[int]
    helpers_cores_sum_S: list[float]
    helpers_cores_frac_fan_in_le_1: list[float]
    n_dou_sites: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_unpaid_hotspots": self.n_unpaid_hotspots,
            "max_v_poly": self.max_v_poly,
            "helpers_cores.sum_S": self.helpers_cores_sum_S,
            "helpers_cores.frac_fan_in_le_1": self.helpers_cores_frac_fan_in_le_1,
            "n_dou_sites": self.n_dou_sites,
        }


@dataclass
class DiffResult:
    version: int = 1
    view: str = "diff"
    pass_: bool = True
    failures: list[str] = field(default_factory=list)
    deltas: DiffDeltas | None = None
    hotspots_added: list[str] = field(default_factory=list)
    hotspots_removed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "view": self.view,
            "pass": self.pass_,
            "failures": list(self.failures),
            "deltas": self.deltas.to_dict() if self.deltas is not None else {},
            "hotspots_added": list(self.hotspots_added),
            "hotspots_removed": list(self.hotspots_removed),
        }


def load_report(path: Path) -> MetricsReport:
    return MetricsReport.from_dict(json.loads(path.read_text(encoding="utf-8")))


def complexity(report: MetricsReport) -> ComplexityBoard:
    return report.overall.complexity


def etspa(report: MetricsReport) -> EtspaOverall:
    return report.overall.etspa


def hotspot_names(report: MetricsReport) -> set[str]:
    return {h.qualified_name for h in report.overall.hotspots}


def max_v_poly_symbol(report: MetricsReport) -> CallableMetrics | None:
    best: CallableMetrics | None = None
    best_v = -1
    for _path, fn in iter_callables(report):
        if fn.v_poly > best_v:
            best, best_v = fn, fn.v_poly
    return best


_COMPLEXITY_KEYS = tuple(f.name for f in fields(ComplexityBoard))


def _row(lines: list[str], label: str, before: Any, after: Any) -> None:
    lines.append(f"  {label}: {before} → {after}")


def _append_board_lines(
    lines: list[str],
    before: MetricsReport,
    after: MetricsReport,
    bc: ComplexityBoard,
    ac: ComplexityBoard,
    be: EtspaOverall,
    ae: EtspaOverall,
) -> tuple[list[str], list[str]]:
    """Named leaf step: verbose text board (complexity, ETSPA, hotspot set)."""
    lines.append("Complexity / hotspot board")
    for key in _COMPLEXITY_KEYS:
        _row(lines, key, getattr(bc, key), getattr(ac, key))

    lines.append("ETSPA (global + helpers_cores)")
    for key in ("sum_S", "frac_S_le_0", "frac_fan_in_le_1"):
        _row(lines, key, getattr(be, key), getattr(ae, key))
    bh, ah = be.helpers_cores, ae.helpers_cores
    _row(lines, "helpers_cores.sum_S", bh.sum_S, ah.sum_S)
    _row(lines, "helpers_cores.frac_fan_in_le_1", bh.frac_fan_in_le_1, ah.frac_fan_in_le_1)

    lines.append("DOU (emit-only; not gated)")
    _row(lines, "n_dou_sites", before.overall.dou.n_dou_sites, after.overall.dou.n_dou_sites)
    _row(
        lines,
        "n_dou_callables",
        before.overall.dou.n_dou_callables,
        after.overall.dou.n_dou_callables,
    )

    before_hs, after_hs = hotspot_names(before), hotspot_names(after)
    added = sorted(after_hs - before_hs)
    removed = sorted(before_hs - after_hs)
    if added:
        lines.append("New unpaid hotspots: " + ", ".join(added))
    if removed:
        lines.append("Cleared unpaid hotspots: " + ", ".join(removed))
    if not added and not removed and before.overall.hotspots is not None:
        lines.append("Unpaid hotspot set unchanged.")
    return added, removed


def _check_gates(
    lines: list[str],
    failures: list[str],
    before_c: ComplexityBoard,
    after_c: ComplexityBoard,
    after: MetricsReport,
) -> bool:
    """Named leaf step: unpaid-hotspot and unpaid max_v_poly gates."""
    failed = False
    b_hot = before_c.n_unpaid_hotspots
    a_hot = after_c.n_unpaid_hotspots
    if a_hot > b_hot:
        msg = f"n_unpaid_hotspots rose ({b_hot} → {a_hot})"
        lines.append(f"FAIL: {msg}")
        failures.append(msg)
        failed = True

    b_max, a_max = before_c.max_v_poly, after_c.max_v_poly
    if a_max > b_max:
        max_sym = max_v_poly_symbol(after)
        if max_sym is not None and (not max_sym.unpaid or max_sym.reduction_like):
            lines.append(
                f"NOTE: max_v_poly rose ({b_max} → {a_max}) on "
                f"{max_sym.qualified_name} "
                f"(unpaid={max_sym.unpaid}, "
                f"reduction_like={max_sym.reduction_like}) — not a gate failure."
            )
        else:
            msg = f"max_v_poly rose ({b_max} → {a_max})"
            lines.append(f"FAIL: {msg}")
            failures.append(msg)
            failed = True
    return failed


def compare(
    before: MetricsReport | dict[str, Any],
    after: MetricsReport | dict[str, Any],
) -> tuple[int, list[str], dict[str, Any]]:
    """Return (exit_code, text_lines, diff_dict).

    Exit 0 = pass, 1 = gated regression.
    Text lines stay verbose; JSON deltas stay gate-focused and compact.
    Accepts ``MetricsReport`` or a raw report mapping (rehydrated via ``from_dict``).
    """
    before_r = before if isinstance(before, MetricsReport) else MetricsReport.from_dict(before)
    after_r = after if isinstance(after, MetricsReport) else MetricsReport.from_dict(after)

    lines: list[str] = []
    failures: list[str] = []
    bc, ac = complexity(before_r), complexity(after_r)
    be, ae = etspa(before_r), etspa(after_r)

    added, removed = _append_board_lines(lines, before_r, after_r, bc, ac, be, ae)
    failed = _check_gates(lines, failures, bc, ac, after_r)
    if not failed:
        lines.append("PASS: no rise in n_unpaid_hotspots or unpaid max_v_poly.")

    bh, ah = be.helpers_cores, ae.helpers_cores
    result = DiffResult(
        pass_=not failed,
        failures=failures,
        deltas=DiffDeltas(
            n_unpaid_hotspots=[bc.n_unpaid_hotspots, ac.n_unpaid_hotspots],
            max_v_poly=[bc.max_v_poly, ac.max_v_poly],
            helpers_cores_sum_S=[bh.sum_S, ah.sum_S],
            helpers_cores_frac_fan_in_le_1=[bh.frac_fan_in_le_1, ah.frac_fan_in_le_1],
            n_dou_sites=[before_r.overall.dou.n_dou_sites, after_r.overall.dou.n_dou_sites],
        ),
        hotspots_added=added,
        hotspots_removed=removed,
    )
    return (1 if failed else 0), lines, result.to_dict()
