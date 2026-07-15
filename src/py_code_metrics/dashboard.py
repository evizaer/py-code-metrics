"""Dashboard predicates: unpaid debt, hotspots, dispatch exemption, reduction-like."""

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
from py_code_metrics.resolve import ClassInfo, ModuleInfo, SymbolIndex

DISPATCH_BASE_SUFFIXES = frozenset({"NodeVisitor", "NodeTransformer"})
DISPATCH_METHOD_PREFIX = "visit_"
DISPATCH_METHOD_NAMES = frozenset({"generic_visit"})


def bases_mention_dispatcher(ci: ClassInfo, mi: ModuleInfo) -> bool:
    """True if a base name resolves to ast.NodeVisitor / NodeTransformer."""
    for raw in ci.bases_raw:
        short = raw.split(".")[-1]
        if short in DISPATCH_BASE_SUFFIXES:
            return True
        if raw in mi.local_names:
            target = mi.local_names[raw]
            if target.split(".")[-1] in DISPATCH_BASE_SUFFIXES:
                return True
    return False


def class_is_ast_dispatcher(index: SymbolIndex, class_qname: str) -> bool:
    """Walk corpus ancestry; external NodeVisitor bases are seen via bases_raw."""
    seen: set[str] = set()
    stack = [class_qname]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        ci = index.classes.get(cur)
        if ci is None:
            continue
        mi = index.modules[ci.module]
        if bases_mention_dispatcher(ci, mi):
            return True
        stack.extend(ci.bases_resolved)
    return False


def is_dispatch_method_name(name: str) -> bool:
    return name.startswith(DISPATCH_METHOD_PREFIX) or name in DISPATCH_METHOD_NAMES


def is_unpaid(c: CallableMetrics) -> bool:
    """Unpaid = low reuse or non-positive ETSPA; dispatch visitors are not debt."""
    if c.dispatch_exempt:
        return False
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
    if c.dispatch_exempt or not is_unpaid(c):
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
        dispatch_exempt=c.dispatch_exempt,
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
    """ETSPA summary for a callable subset (typically helpers+cores, non-exempt)."""
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
