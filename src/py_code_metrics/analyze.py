"""Orchestration: discover → parse → index → metrics → report."""

from __future__ import annotations

from pathlib import Path

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
    CallableMetrics,
    ClassMetrics,
    MetricsReport,
    ModuleReport,
    ModuleRollup,
    OverallReport,
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


def analyze_path(root: Path) -> MetricsReport:
    """Leaf pipeline: discover → index → score → assemble report."""
    root = root.resolve()
    parsed, skipped = parse_files(discover_python_files(root))
    index = build_symbol_index(parsed, root)
    call_graph = build_call_graph(index)
    import_graph = build_import_graph(set(index.modules.keys()), index.imports_by_module)
    override_sets = build_override_index(
        {cq: ci.node for cq, ci in index.classes.items()},
        {cq: ci.bases_resolved for cq, ci in index.classes.items()},
    )
    call_costs = _collect_call_costs(index, call_graph)
    callable_metrics = {
        qname: _score_callable(index, call_graph, override_sets, call_costs, qname, info)
        for qname, info in index.callables.items()
    }
    modules_out = [
        _module_report(root, index, import_graph, callable_metrics, mod_name)
        for mod_name in sorted(index.modules)
    ]
    return MetricsReport(
        input={
            "root": str(root),
            "files_analyzed": len(parsed),
            "files_skipped": [{"path": str(s.path), "reason": s.reason} for s in skipped],
        },
        overall=_overall(modules_out, callable_metrics, index, import_graph),
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
    return CallableMetrics(
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
    )


def _module_report(
    root: Path,
    index: SymbolIndex,
    import_graph: ImportGraph,
    callable_metrics: dict[str, CallableMetrics],
    mod_name: str,
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
        classes_out.append(
            ClassMetrics(
                name=ci.name,
                qualified_name=cq,
                lineno=ci.node.lineno,
                lcom4=lcom4,
                wmc=compute_wmc(method_ccs) if method_ccs else 0,
                nom=nom,
                methods=sorted(method_cms, key=lambda m: m.lineno),
            )
        )
    all_callables = functions + [m for c in classes_out for m in c.methods]
    return ModuleReport(
        path=rel_path,
        name=mod_name,
        metrics=_rollup(all_callables, class_count=len(classes_out)),
        imports=sorted(import_graph.edges.get(mod_name, ())),
        scc_id=import_graph.scc_of.get(mod_name),
        functions=functions,
        classes=classes_out,
    )


def _rollup(callables: list[CallableMetrics], class_count: int) -> ModuleRollup:
    n = len(callables)
    if n == 0:
        return ModuleRollup(class_count=class_count)
    roles = {"core": 0, "leaf": 0, "helper": 0}
    for c in callables:
        roles[c.role] = roles.get(c.role, 0) + 1
    return ModuleRollup(
        callable_count=n,
        class_count=class_count,
        sum_S=sum(c.S for c in callables),
        frac_S_le_0=sum(1 for c in callables if c.S <= 0) / n,
        frac_fan_in_le_1=sum(1 for c in callables if c.fan_in_ext <= 1) / n,
        max_v_poly=max(c.v_poly for c in callables),
        max_nesting=max(c.max_nesting for c in callables),
        mean_cyclomatic=sum(c.cyclomatic for c in callables) / n,
        mean_cognitive=sum(c.cognitive for c in callables) / n,
        mean_car=sum(c.car for c in callables) / n,
        mean_lmd=sum(c.lmd for c in callables) / n,
        roles=roles,
    )


def _overall(
    modules: list[ModuleReport],
    callable_metrics: dict[str, CallableMetrics],
    index: SymbolIndex,
    import_graph: ImportGraph,
) -> OverallReport:
    all_c = list(callable_metrics.values())
    n = len(all_c)
    roles = {"core": 0, "leaf": 0, "helper": 0}
    for c in all_c:
        roles[c.role] = roles.get(c.role, 0) + 1

    overall = OverallReport(
        totals={
            "modules": len(modules),
            "classes": len(index.classes),
            "functions": sum(1 for c in all_c if c.kind in {"function", "nested_function"}),
            "methods": sum(1 for c in all_c if c.kind in {"method", "classmethod", "staticmethod"}),
        },
        roles=roles,
        imports={
            "edge_count": import_graph.edge_count,
            "cycle_count": len(import_graph.cycles),
            "cycles": import_graph.cycles,
        },
    )
    if not n:
        return overall
    overall.complexity = {
        "max_v_poly": max(c.v_poly for c in all_c),
        "max_nesting": max(c.max_nesting for c in all_c),
        "mean_cyclomatic": sum(c.cyclomatic for c in all_c) / n,
        "mean_cognitive": sum(c.cognitive for c in all_c) / n,
    }
    overall.etspa = {
        "sum_S": sum(c.S for c in all_c),
        "frac_S_le_0": sum(1 for c in all_c if c.S <= 0) / n,
        "frac_fan_in_le_1": sum(1 for c in all_c if c.fan_in_ext <= 1) / n,
    }
    overall.expression = {
        "mean_car": sum(c.car for c in all_c) / n,
        "mean_lmd": sum(c.lmd for c in all_c) / n,
        "mean_cvr": sum(c.cvr for c in all_c) / n,
    }
    return overall
