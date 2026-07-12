"""Resolve test call sites to production (non-test) corpus symbols."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.discover import is_test_file
from py_code_metrics.metrics.call_graph import collect_calls_in_function
from py_code_metrics.metrics.test_oracles import TestFunctionInfo
from py_code_metrics.resolve import (
    CallableInfo,
    ModuleInfo,
    SymbolIndex,
    resolve_call,
)


def resolve_production_calls(
    index: SymbolIndex,
    module: ModuleInfo,
    info: TestFunctionInfo,
) -> list[str]:
    """Return sorted unique production callable qnames invoked by *info*."""
    caller = _caller_info(index, module, info)
    hits: set[str] = set()
    for call in collect_calls_in_function(info.node):
        callee = resolve_call(index, module, caller, call)
        if callee and _is_production_callable(index, callee):
            hits.add(callee)
    return sorted(hits)


def _caller_info(
    index: SymbolIndex,
    module: ModuleInfo,
    info: TestFunctionInfo,
) -> CallableInfo:
    qname = _test_callable_qname(module.name, info)
    existing = index.callables.get(qname)
    if existing is not None:
        return existing
    class_qname = f"{module.name}.{info.class_name}" if info.class_name else None
    return CallableInfo(
        qname=qname,
        name=info.name,
        module=module.name,
        kind="method" if info.class_name else "function",
        node=info.node,
        class_qname=class_qname,
        parent_qname=class_qname,
        is_public=True,
        lineno=info.lineno,
    )


def _test_callable_qname(module_name: str, info: TestFunctionInfo) -> str:
    if info.class_name:
        return f"{module_name}.{info.class_name}.{info.name}"
    return f"{module_name}.{info.name}"


def _is_production_callable(index: SymbolIndex, qname: str) -> bool:
    info = index.callables.get(qname)
    if info is None:
        return False
    mi = index.modules.get(info.module)
    if mi is None:
        return False
    return not is_test_file(Path(mi.path))
