"""Module-native depth / reuse metrics (MDI, PIW, PTR, import Ca/Ce).

See ``docs/module-metrics-research.md``. Coefficients (OQ-1 defaults):
alpha=beta=1, gamma omitted, K=3 reserved for P2 IC ladder.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass

from py_code_metrics.metrics.call_graph import CallGraph, collect_calls_in_function
from py_code_metrics.metrics.imports import ImportGraph
from py_code_metrics.model import (
    CallableMetrics,
    ModuleDepthMetrics,
    ModuleDepthOverall,
    ModuleHubEntry,
)
from py_code_metrics.resolve import CallableInfo, SymbolIndex, resolve_call

# PIW weights (research OQ-1).
ALPHA = 1.0
BETA = 1.0

# Soft anti-split: modules with a real public surface but thin implementation.
LOW_MDI_THRESHOLD = 10.0
# Leaf scripts: no real library surface — don't demand depth.
LEAF_SCRIPT_MAX_PIW = 0.5


@dataclass(frozen=True)
class _PublicSurface:
    """Public callables and types that form a module's formal interface."""

    callables: list[tuple[CallableInfo, CallableMetrics]]
    n_public_types: int


def _is_public_name(name: str) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


def compute_module_depth(
    mod_name: str,
    *,
    index: SymbolIndex,
    callable_metrics: dict[str, CallableMetrics],
    call_graph: CallGraph,
    import_graph: ImportGraph,
) -> ModuleDepthMetrics:
    """Compute P1 module-native metrics for one module."""
    surface = _public_surface(mod_name, index, callable_metrics)
    pub = surface.callables
    n_exports = len(pub)
    n_types = surface.n_public_types

    mean_params = (sum(cm.params for _, cm in pub) / n_exports) if n_exports else 0.0
    piw = n_exports + ALPHA * mean_params + BETA * n_types

    c_iface = sum(_iface_cost(info) for info, _ in pub)
    f_impl = _implementation_tokens(mod_name, pub, index, callable_metrics, call_graph)
    mdi = f_impl / (1.0 + c_iface)

    ptr = _pass_through_rate(mod_name, pub, index)
    ca = import_graph.afferent(mod_name)
    ce = import_graph.efferent(mod_name)
    denom = ca + ce
    instability = (ce / denom) if denom else 0.0
    sum_public_s = sum(max(cm.S, 0.0) for _, cm in pub)
    role = "leaf_script" if piw <= LEAF_SCRIPT_MAX_PIW else "library"

    return ModuleDepthMetrics(
        mdi=mdi,
        piw=piw,
        ptr=ptr,
        ca=ca,
        ce=ce,
        instability=instability,
        hub_risk=ca * ce,
        f_impl=f_impl,
        c_iface=float(c_iface),
        n_public_exports=n_exports,
        n_public_types=n_types,
        sum_public_S=sum_public_s,
        role=role,  # type: ignore[arg-type]
    )


def aggregate_module_depth(modules: list[ModuleDepthMetrics]) -> ModuleDepthOverall:
    """Corpus soft signals: sum PIW and low-MDI library module count."""
    if not modules:
        return ModuleDepthOverall(low_mdi_threshold=LOW_MDI_THRESHOLD)
    n = len(modules)
    sum_piw = sum(m.piw for m in modules)
    n_low = sum(
        1 for m in modules if m.role == "library" and m.piw >= 1.0 and m.mdi < LOW_MDI_THRESHOLD
    )
    return ModuleDepthOverall(
        sum_piw=sum_piw,
        n_low_mdi=n_low,
        low_mdi_threshold=LOW_MDI_THRESHOLD,
        mean_mdi=sum(m.mdi for m in modules) / n,
        mean_piw=sum_piw / n,
        mean_ptr=sum(m.ptr for m in modules) / n,
    )


def aggregate_module_depth_from_reports(
    depths: list[tuple[str, str, ModuleDepthMetrics]],
) -> ModuleDepthOverall:
    """Like ``aggregate_module_depth`` but stamp hub rows with path/name."""
    overall = aggregate_module_depth([d for _, _, d in depths])
    hubs: list[ModuleHubEntry] = []
    ranked = sorted(depths, key=lambda row: (-row[2].hub_risk, -row[2].ca, row[0]))
    for path, name, d in ranked:
        if d.hub_risk <= 0:
            continue
        hubs.append(
            ModuleHubEntry(
                path=path,
                name=name,
                ca=d.ca,
                ce=d.ce,
                hub_risk=d.hub_risk,
                mdi=d.mdi,
                piw=d.piw,
            )
        )
        if len(hubs) >= 10:
            break
    overall.hubs = hubs
    return overall


def _counts_as_public_export(info: CallableInfo, mod_name: str) -> bool:
    if info.module != mod_name or not info.is_public:
        return False
    if info.kind == "nested_function":
        return False
    if not info.class_qname:
        return True
    class_name = info.class_qname.rsplit(".", 1)[-1]
    return _is_public_name(class_name)


def _public_surface(
    mod_name: str,
    index: SymbolIndex,
    callable_metrics: dict[str, CallableMetrics],
) -> _PublicSurface:
    callables: list[tuple[CallableInfo, CallableMetrics]] = []
    for qname, info in index.callables.items():
        if not _counts_as_public_export(info, mod_name):
            continue
        cm = callable_metrics.get(qname)
        if cm is None:
            continue
        callables.append((info, cm))
    n_types = sum(
        1 for ci in index.classes.values() if ci.module == mod_name and _is_public_name(ci.name)
    )
    return _PublicSurface(callables=callables, n_public_types=n_types)


def _iface_cost(info: CallableInfo) -> int:
    """C_iface term: 1 + n_params + 1_kwonly (header-token gamma term omitted)."""
    node = info.node
    n_params = len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs)
    if node.args.vararg is not None:
        n_params += 1
    if node.args.kwarg is not None:
        n_params += 1
    if info.kind in {"method", "classmethod"}:
        n_params = max(0, n_params - 1)
    kwonly = 1 if node.args.kwonlyargs else 0
    return 1 + n_params + kwonly


def _module_fan_out(mod_name: str, call_graph: CallGraph) -> dict[str, set[str]]:
    fan_out: dict[str, set[str]] = defaultdict(set)
    for site in call_graph.sites:
        if not site.callee_qname or site.module != mod_name:
            continue
        fan_out[site.caller_qname].add(site.callee_qname)
    return fan_out


def _reachable_qnames(
    seeds: list[str],
    mod_name: str,
    index: SymbolIndex,
    fan_out: dict[str, set[str]],
) -> set[str]:
    reachable: set[str] = set()
    queue: deque[str] = deque(seeds)
    while queue:
        q = queue.popleft()
        if q in reachable:
            continue
        info = index.callables.get(q)
        if info is None or info.module != mod_name:
            continue
        reachable.add(q)
        for callee in fan_out.get(q, ()):
            if callee not in reachable:
                queue.append(callee)
    return reachable


def _implementation_tokens(
    mod_name: str,
    pub: list[tuple[CallableInfo, CallableMetrics]],
    index: SymbolIndex,
    callable_metrics: dict[str, CallableMetrics],
    call_graph: CallGraph,
) -> int:
    """F_impl: body tokens behind public entrypoints; same-module helpers once."""
    if not pub:
        return 0
    fan_out = _module_fan_out(mod_name, call_graph)
    seeds = [info.qname for info, _ in pub]
    reachable = _reachable_qnames(seeds, mod_name, index, fan_out)
    return sum(callable_metrics[q].body_tokens for q in reachable if q in callable_metrics)


def _pass_through_rate(
    mod_name: str,
    pub: list[tuple[CallableInfo, CallableMetrics]],
    index: SymbolIndex,
) -> float:
    if not pub:
        return 0.0
    n_pt = sum(1 for info, _ in pub if _is_passthrough(mod_name, info, index))
    return n_pt / len(pub)


def _is_echo_callee(mod_name: str, caller: CallableInfo, callee: CallableInfo) -> bool:
    """True when callee is a cross-layer (or public re-export) target, not a private helper."""
    if callee.qname == caller.qname:
        return False
    return not (callee.module == mod_name and not callee.is_public)


def _is_passthrough(mod_name: str, info: CallableInfo, index: SymbolIndex) -> bool:
    """Thin wrapper with signature echo to another module/class."""
    dominant = _dominant_call(info.node)
    if dominant is None:
        return False
    mi = index.modules[mod_name]
    callee_qname = resolve_call(index, mi, info, dominant)
    if callee_qname is None:
        calls = collect_calls_in_function(info.node)
        if len(calls) != 1:
            return False
        return _signature_echo_unresolved(info, dominant)

    callee = index.callables.get(callee_qname)
    if callee is None or not _is_echo_callee(mod_name, info, callee):
        return False
    return _signature_similar(info, callee)


def _dominant_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    """Return the sole substantive Call if the body is a thin wrapper."""
    body = _strip_docstring(node.body)
    if not body or len(body) > 2:
        return None
    if len(body) == 1:
        return _call_from_stmt(body[0])
    return _assign_return_call(node, body[0], body[1])


def _assign_return_call(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    first: ast.stmt,
    second: ast.stmt,
) -> ast.Call | None:
    if not isinstance(first, ast.Assign) or len(first.targets) != 1:
        return None
    if not isinstance(first.targets[0], ast.Name):
        return None
    if not isinstance(first.value, ast.Call):
        return None
    if not isinstance(second, ast.Return) or not isinstance(second.value, ast.Name):
        return None
    if second.value.id != first.targets[0].id:
        return None
    if len(collect_calls_in_function(node)) != 1:
        return None
    return first.value


def _call_from_stmt(stmt: ast.stmt) -> ast.Call | None:
    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
        return stmt.value
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return stmt.value
    if (
        isinstance(stmt, ast.Return)
        and isinstance(stmt.value, ast.Await)
        and isinstance(stmt.value.value, ast.Call)
    ):
        return stmt.value.value
    return None


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if not body:
        return body
    first = body[0]
    if not isinstance(first, ast.Expr):
        return body
    if not isinstance(first.value, ast.Constant):
        return body
    if not isinstance(first.value.value, str):
        return body
    return body[1:]


def _param_names(info: CallableInfo) -> list[str]:
    node = info.node
    names = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
    if info.kind in {"method", "classmethod"} and names:
        names = names[1:]
    if node.args.vararg:
        names.append(node.args.vararg.arg)
    if node.args.kwarg:
        names.append(node.args.kwarg.arg)
    return names


def _signature_similar(a: CallableInfo, b: CallableInfo) -> bool:
    na, nb = _param_names(a), _param_names(b)
    if abs(len(na) - len(nb)) > 1:
        return False
    if not na and not nb:
        return True
    sa, sb = set(na), set(nb)
    if not sa or not sb:
        return len(na) == len(nb)
    overlap = len(sa & sb) / len(sa | sb)
    return overlap >= 0.5 or (len(na) == len(nb) and overlap >= 0.34)


def _signature_echo_unresolved(info: CallableInfo, call: ast.Call) -> bool:
    """Heuristic when callee is outside the corpus: arity echo via call args."""
    n_params = len(_param_names(info))
    n_args = len(call.args) + len(call.keywords)
    return abs(n_params - n_args) <= 1
