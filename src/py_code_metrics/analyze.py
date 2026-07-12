"""Orchestration: discover → parse → index → metrics → report."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from py_code_metrics.dashboard import (
    class_is_ast_dispatcher,
    etspa_board,
    expression_board,
    hotspot_entry,
    is_dispatch_method_name,
    is_hotspot,
    is_reduction_like,
    is_unpaid,
)
from py_code_metrics.discover import discover_python_files
from py_code_metrics.metrics.call_graph import CallGraph, collect_calls_in_function
from py_code_metrics.metrics.cohesion import compute_lcom4, compute_wmc
from py_code_metrics.metrics.complexity import analyze_function_body, effective_param_count
from py_code_metrics.metrics.etspa import (
    body_token_count,
    call_site_token_cost,
    compute_etspa,
    header_token_count,
    is_trivial_body,
)
from py_code_metrics.metrics.expression import analyze_expression
from py_code_metrics.metrics.imports import ImportGraph, build_import_graph
from py_code_metrics.metrics.v_poly import build_override_index, v_poly_for_callable
from py_code_metrics.model import (
    DEFAULT_THRESHOLDS,
    CallableMetrics,
    ClassMetrics,
    MetricsReport,
    ModuleReport,
    ModuleRollup,
    OverallReport,
    Thresholds,
)
from py_code_metrics.parse import parse_files
from py_code_metrics.resolve import (
    CallableInfo,
    SymbolIndex,
    build_call_graph,
    build_symbol_index,
    resolve_polymorphic_targets,
)
from py_code_metrics.roles import classify_role


class _CallableStats(TypedDict):
    sum_S: float
    frac_S_le_0: float
    frac_fan_in_le_1: float
    max_v_poly: int
    max_nesting: int
    mean_cyclomatic: float
    mean_cognitive: float
    mean_car: float
    mean_lmd: float
    n_v_poly_gt_15: int
    n_nesting_gt_3: int
    n_unpaid_v_poly_gt_15: int
    n_unpaid_nesting_gt_3: int
    n_unpaid_hotspots: int
    roles: dict[str, int]
    hotspots: list[dict[str, Any]]
    helpers_cores_etspa: dict[str, Any]
    leaves_expression: dict[str, Any]
    mean_cvr: float


def analyze_path(root: Path, *, thresholds: Thresholds | None = None) -> MetricsReport:
    """Leaf pipeline: discover → index → score → assemble report."""
    root = root.resolve()
    thresholds = thresholds or DEFAULT_THRESHOLDS
    parsed, skipped = parse_files(discover_python_files(root))
    index = build_symbol_index(parsed, root)
    call_graph = build_call_graph(index)
    import_graph = build_import_graph(set(index.modules.keys()), index.imports_by_module)
    override_sets = build_override_index(
        {cq: ci.node for cq, ci in index.classes.items()},
        {cq: ci.bases_resolved for cq, ci in index.classes.items()},
    )
    dispatcher_classes = {cq for cq in index.classes if class_is_ast_dispatcher(index, cq)}
    call_costs = _collect_call_costs(index, call_graph)
    callable_metrics = {
        qname: _score_callable(
            index,
            call_graph,
            override_sets,
            call_costs,
            dispatcher_classes,
            qname,
            info,
        )
        for qname, info in index.callables.items()
    }
    modules_out = [
        _module_report(
            root, index, import_graph, callable_metrics, dispatcher_classes, mod_name, thresholds
        )
        for mod_name in sorted(index.modules)
    ]
    return MetricsReport(
        input={
            "root": str(root),
            "files_analyzed": len(parsed),
            "files_skipped": [{"path": str(s.path), "reason": s.reason} for s in skipped],
        },
        thresholds=thresholds.to_dict(),
        overall=_overall(modules_out, callable_metrics, index, import_graph, thresholds),
        modules=modules_out,
    )


def _collect_call_costs(
    index: SymbolIndex,
    call_graph: CallGraph,
) -> dict[str, list[int]]:
    call_costs: dict[str, list[int]] = {}
    for site in call_graph.sites:
        if not site.callee_qname:
            continue
        mi = index.modules[site.module]
        cost = call_site_token_cost(site.call, mi.source_lines)
        call_costs.setdefault(site.callee_qname, []).append(cost)
    return call_costs


def _score_callable(
    index: SymbolIndex,
    call_graph: CallGraph,
    override_sets: dict,
    call_costs: dict[str, list[int]],
    dispatcher_classes: set[str],
    qname: str,
    info: CallableInfo,
) -> CallableMetrics:
    mi = index.modules[info.module]
    local = analyze_function_body(info.node)
    params = effective_param_count(
        info.node,
        is_method=info.kind == "method",
        is_classmethod=info.kind == "classmethod",
    )
    B = body_token_count(info.node, mi.source_lines)
    H = header_token_count(info.node, mi.source_lines)
    F_ext = call_graph.fan_in_ext(qname)
    costs = call_costs.get(qname, [])
    mean_C = sum(costs) / len(costs) if costs else None
    etspa = compute_etspa(
        body_tokens=B,
        header_tokens=H,
        fan_in_ext=F_ext,
        mean_call_cost=mean_C,
        trivial=is_trivial_body(info.node),
    )
    expr = analyze_expression(info.node, body_tokens=B)
    calls = collect_calls_in_function(info.node)
    v_poly = v_poly_for_callable(
        local.cyclomatic,
        calls,
        resolve_call_targets=lambda call, _info=info: resolve_polymorphic_targets(
            index, _info, call
        ),
        override_sets=override_sets,
    )
    role = classify_role(
        info,
        fan_in_ext=F_ext,
        call_count=expr.call_count,
        assign_count=expr.assign_count,
    )
    dispatch_exempt = bool(
        info.class_qname
        and info.class_qname in dispatcher_classes
        and is_dispatch_method_name(info.name)
    )
    metrics = CallableMetrics(
        name=info.name,
        qualified_name=qname,
        kind=info.kind,  # type: ignore[arg-type]
        lineno=info.lineno,
        role=role,
        parent=info.parent_qname,
        cyclomatic=local.cyclomatic,
        v_poly=v_poly,
        cognitive=local.cognitive,
        max_nesting=local.max_nesting,
        params=params,
        statements=local.statements,
        returns=local.returns,
        fan_in=call_graph.fan_in_total(qname),
        fan_in_ext=F_ext,
        fan_in_rec=call_graph.fan_in_rec(qname),
        body_tokens=etspa.body_tokens,
        header_tokens=etspa.header_tokens,
        mean_call_cost=etspa.mean_call_cost,
        S=etspa.S,
        etspa=etspa.etspa,
        car=expr.car,
        lmd=expr.lmd,
        cvr=expr.cvr,
        assign_count=expr.assign_count,
        call_count=expr.call_count,
        local_stores=expr.local_stores,
        comprehension_count=expr.comprehension_count,
        dispatch_exempt=dispatch_exempt,
    )
    metrics.reduction_like = is_reduction_like(metrics)
    metrics.unpaid = is_unpaid(metrics)
    return metrics


def _module_report(
    root: Path,
    index: SymbolIndex,
    import_graph: ImportGraph,
    callable_metrics: dict[str, CallableMetrics],
    dispatcher_classes: set[str],
    mod_name: str,
    thresholds: Thresholds,
) -> ModuleReport:
    mi = index.modules[mod_name]
    try:
        rel_path = str(mi.path.resolve().relative_to(root))
    except ValueError:
        rel_path = str(mi.path)

    functions = sorted(
        (
            cm
            for qname, cm in callable_metrics.items()
            if index.callables[qname].module == mod_name
            and index.callables[qname].kind in {"function", "nested_function"}
        ),
        key=lambda m: m.lineno,
    )
    classes_out: list[ClassMetrics] = []
    for cq, ci in sorted(index.classes.items()):
        if ci.module != mod_name:
            continue
        method_cms = [
            callable_metrics[q]
            for q, inf in index.callables.items()
            if inf.class_qname == cq and inf.kind in {"method", "classmethod", "staticmethod"}
        ]
        method_ccs = {m.name: m.cyclomatic for m in method_cms}
        lcom4, nom, _ = compute_lcom4(ci.node)
        is_dispatch = cq in dispatcher_classes
        classes_out.append(
            ClassMetrics(
                name=ci.name,
                qualified_name=cq,
                lineno=ci.node.lineno,
                lcom4=lcom4,
                wmc=compute_wmc(method_ccs) if method_ccs else 0,
                nom=nom,
                dispatch_class=is_dispatch,
                lcom4_gate_exempt=is_dispatch,
                methods=sorted(method_cms, key=lambda m: m.lineno),
            )
        )
    all_callables = functions + [m for c in classes_out for m in c.methods]
    return ModuleReport(
        path=rel_path,
        name=mod_name,
        metrics=_rollup(all_callables, class_count=len(classes_out), thresholds=thresholds),
        imports=sorted(import_graph.edges.get(mod_name, ())),
        scc_id=import_graph.scc_of.get(mod_name),
        functions=functions,
        classes=classes_out,
    )


def _rollup(
    callables: list[CallableMetrics],
    class_count: int,
    thresholds: Thresholds,
) -> ModuleRollup:
    n = len(callables)
    if n == 0:
        return ModuleRollup(class_count=class_count)
    stats = _callable_stats(callables, thresholds)
    return ModuleRollup(
        callable_count=n,
        class_count=class_count,
        sum_S=stats["sum_S"],
        frac_S_le_0=stats["frac_S_le_0"],
        frac_fan_in_le_1=stats["frac_fan_in_le_1"],
        max_v_poly=stats["max_v_poly"],
        max_nesting=stats["max_nesting"],
        mean_cyclomatic=stats["mean_cyclomatic"],
        mean_cognitive=stats["mean_cognitive"],
        mean_car=stats["mean_car"],
        mean_lmd=stats["mean_lmd"],
        n_v_poly_gt_15=stats["n_v_poly_gt_15"],
        n_nesting_gt_3=stats["n_nesting_gt_3"],
        n_unpaid_v_poly_gt_15=stats["n_unpaid_v_poly_gt_15"],
        n_unpaid_nesting_gt_3=stats["n_unpaid_nesting_gt_3"],
        n_unpaid_hotspots=stats["n_unpaid_hotspots"],
        roles=stats["roles"],
    )


def _overall(
    modules: list[ModuleReport],
    callable_metrics: dict[str, CallableMetrics],
    index: SymbolIndex,
    import_graph: ImportGraph,
    thresholds: Thresholds,
) -> OverallReport:
    all_c = list(callable_metrics.values())
    overall = OverallReport(
        totals={
            "modules": len(modules),
            "classes": len(index.classes),
            "functions": sum(1 for c in all_c if c.kind in {"function", "nested_function"}),
            "methods": sum(1 for c in all_c if c.kind in {"method", "classmethod", "staticmethod"}),
        },
        imports={
            "edge_count": import_graph.edge_count,
            "cycle_count": len(import_graph.cycles),
            "cycles": import_graph.cycles,
        },
    )
    if not all_c:
        return overall
    stats = _callable_stats(all_c, thresholds)
    overall.roles = stats["roles"]
    overall.complexity = {
        "max_v_poly": stats["max_v_poly"],
        "max_nesting": stats["max_nesting"],
        "mean_cyclomatic": stats["mean_cyclomatic"],
        "mean_cognitive": stats["mean_cognitive"],
        "n_v_poly_gt_15": stats["n_v_poly_gt_15"],
        "n_nesting_gt_3": stats["n_nesting_gt_3"],
        "n_unpaid_v_poly_gt_15": stats["n_unpaid_v_poly_gt_15"],
        "n_unpaid_nesting_gt_3": stats["n_unpaid_nesting_gt_3"],
        "n_unpaid_hotspots": stats["n_unpaid_hotspots"],
    }
    overall.etspa = {
        "sum_S": stats["sum_S"],
        "frac_S_le_0": stats["frac_S_le_0"],
        "frac_fan_in_le_1": stats["frac_fan_in_le_1"],
        "note": "Global fracs mix leaves+helpers; prefer helpers_cores for gates.",
        "helpers_cores": stats["helpers_cores_etspa"],
    }
    overall.expression = {
        "mean_car": stats["mean_car"],
        "mean_lmd": stats["mean_lmd"],
        "mean_cvr": stats["mean_cvr"],
        "leaves": stats["leaves_expression"],
    }
    overall.hotspots = stats["hotspots"]
    return overall


def _callable_stats(callables: list[CallableMetrics], thresholds: Thresholds) -> _CallableStats:
    """Shared module/overall aggregates over scored callables (single pass)."""
    n = len(callables)
    roles = {"core": 0, "leaf": 0, "helper": 0}
    v_gate = thresholds.v_poly_lenient
    nest_gate = thresholds.nesting_depth

    sum_S = sum_cyc = sum_cog = sum_car = sum_lmd = sum_cvr = 0.0
    n_s_le_0 = n_f_le_1 = 0
    max_v = max_n = 0
    n_v = n_nest = n_unpaid_v = n_unpaid_nest = 0
    helper_core: list[CallableMetrics] = []
    leaves: list[CallableMetrics] = []
    hotspot_cms: list[CallableMetrics] = []

    for c in callables:
        roles[c.role] = roles.get(c.role, 0) + 1
        sum_S += c.S
        sum_cyc += c.cyclomatic
        sum_cog += c.cognitive
        sum_car += c.car
        sum_lmd += c.lmd
        sum_cvr += c.cvr
        if c.S <= 0:
            n_s_le_0 += 1
        if c.fan_in_ext <= 1:
            n_f_le_1 += 1
        if c.v_poly > max_v:
            max_v = c.v_poly
        if c.max_nesting > max_n:
            max_n = c.max_nesting
        over_v = c.v_poly > v_gate
        over_n = c.max_nesting > nest_gate
        if over_v:
            n_v += 1
        if over_n:
            n_nest += 1
        if c.unpaid and over_v:
            n_unpaid_v += 1
        if c.unpaid and over_n:
            n_unpaid_nest += 1
        if c.role == "leaf":
            leaves.append(c)
        elif not c.dispatch_exempt:
            helper_core.append(c)
        if is_hotspot(c, thresholds):
            hotspot_cms.append(c)

    hotspot_cms.sort(key=lambda c: (-c.v_poly, -c.cognitive, -c.max_nesting, c.qualified_name))
    hotspot_dicts = [hotspot_entry(c) for c in hotspot_cms]

    return {
        "sum_S": sum_S,
        "frac_S_le_0": n_s_le_0 / n,
        "frac_fan_in_le_1": n_f_le_1 / n,
        "max_v_poly": max_v,
        "max_nesting": max_n,
        "mean_cyclomatic": sum_cyc / n,
        "mean_cognitive": sum_cog / n,
        "mean_car": sum_car / n,
        "mean_lmd": sum_lmd / n,
        "n_v_poly_gt_15": n_v,
        "n_nesting_gt_3": n_nest,
        "n_unpaid_v_poly_gt_15": n_unpaid_v,
        "n_unpaid_nesting_gt_3": n_unpaid_nest,
        "n_unpaid_hotspots": len(hotspot_dicts),
        "roles": roles,
        "hotspots": hotspot_dicts,
        "helpers_cores_etspa": etspa_board(helper_core),
        "leaves_expression": expression_board(leaves),
        "mean_cvr": sum_cvr / n,
    }
