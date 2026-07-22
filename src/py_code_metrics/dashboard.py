"""Dashboard predicates: unpaid debt, hotspots, reduction-like."""

from __future__ import annotations

from py_code_metrics.model import (
    CallableMetrics,
    DouHotspotEntry,
    DouImpact,
    DouSite,
    HelpersCoresEtspa,
    HotspotEntry,
    LeavesExpressionBoard,
    Thresholds,
)


def is_unpaid(c: CallableMetrics) -> bool:
    """Unpaid = low reuse or non-positive ETSPA."""
    return c.fan_in_ext <= 1 or c.S <= 0


def is_reduction_like(c: CallableMetrics) -> bool:
    """
    Flat fan-out of similar branches (aggregations), not deep spaghetti.

    High v_poly with shallow nesting and cognitive not much above cyclomatic.
    """
    if c.max_nesting > 1:
        return False
    if c.v_poly < 8:
        return False
    # Cognitive tracks nesting; reduction leaves stay near raw branch count.
    return c.cognitive <= max(c.v_poly * 0.75, float(c.cyclomatic + 2))


def is_hotspot(c: CallableMetrics, thresholds: Thresholds) -> bool:
    """High complexity AND unpaid; reduction-like v_poly alone does not qualify."""
    if not is_unpaid(c):
        return False
    if c.max_nesting > thresholds.nesting_depth:
        return True
    if c.cognitive > thresholds.cognitive:
        return True
    return c.v_poly > thresholds.v_poly_lenient and not c.reduction_like


def hotspot_entry(c: CallableMetrics) -> HotspotEntry:
    return HotspotEntry(
        qualified_name=c.qualified_name,
        v_poly=c.v_poly,
        nesting=c.max_nesting,
        cognitive=c.cognitive,
        fan_in_ext=c.fan_in_ext,
        S=c.S,
        role=c.role,
        unpaid=True,
        reduction_like=c.reduction_like,
    )


def dou_impact_sort_key(impact: DouImpact) -> tuple:
    """Higher impact first: cross-module, fan-out, key vocab, public API."""
    return (
        int(impact.cross_module),
        impact.fan_out_sites,
        impact.key_vocab_size,
        int(impact.on_public_api),
    )


def aggregate_dou_impact(sites: list[DouSite]) -> DouImpact:
    if not sites:
        return DouImpact()
    return DouImpact(
        fan_out_sites=max(s.impact.fan_out_sites for s in sites),
        key_vocab_size=max(s.impact.key_vocab_size for s in sites),
        cross_module=any(s.impact.cross_module for s in sites),
        on_public_api=any(s.impact.on_public_api for s in sites),
    )


def dou_hotspot_entry(c: CallableMetrics, path: str | None = None) -> DouHotspotEntry:
    impact = aggregate_dou_impact(c.dou_sites)
    primary = max(
        c.dou_sites,
        key=lambda s: (*dou_impact_sort_key(s.impact), s.annotation),
        default=None,
    )
    return DouHotspotEntry(
        qualified_name=c.qualified_name,
        n_dou_sites=c.n_dou_sites,
        annotation=primary.annotation if primary is not None else "",
        impact=impact,
        path=path,
    )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _frac(pred_count: int, n: int) -> float:
    return pred_count / n if n else 0.0


def etspa_board(callables: list[CallableMetrics]) -> HelpersCoresEtspa:
    """ETSPA summary for a callable subset (typically helpers+cores)."""
    n = len(callables)
    if n == 0:
        return HelpersCoresEtspa()
    return HelpersCoresEtspa(
        callable_count=n,
        sum_S=sum(c.S for c in callables),
        frac_S_le_0=_frac(sum(1 for c in callables if c.S <= 0), n),
        frac_fan_in_le_1=_frac(sum(1 for c in callables if c.fan_in_ext <= 1), n),
    )


def expression_board(callables: list[CallableMetrics]) -> LeavesExpressionBoard:
    """Expression / nesting board for leaves."""
    n = len(callables)
    if n == 0:
        return LeavesExpressionBoard()
    return LeavesExpressionBoard(
        callable_count=n,
        mean_car=_mean([c.car for c in callables]),
        mean_lmd=_mean([c.lmd for c in callables]),
        mean_nesting=_mean([float(c.max_nesting) for c in callables]),
        mean_cognitive=_mean([float(c.cognitive) for c in callables]),
    )
