"""Polymorphism-aware cyclomatic complexity (v_poly)."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable


def _ancestry(
    qname: str,
    bases_resolved: dict[str, list[str]],
    cache: dict[str, list[str]],
    seen: set[str] | None = None,
) -> list[str]:
    if qname in cache:
        return cache[qname]
    seen = seen or set()
    if qname in seen:
        return []
    seen.add(qname)
    result = [qname]
    for base in bases_resolved.get(qname, []):
        result.extend(_ancestry(base, bases_resolved, cache, seen))
    cache[qname] = result
    return result


def build_override_index(
    classes: dict[str, ast.ClassDef],
    bases_resolved: dict[str, list[str]],
) -> dict[tuple[str, str], set[str]]:
    """
    Map (class_qname, method_name) → set of classes implementing that method
    in related hierarchies (shared ancestry).
    """
    defined: dict[str, set[str]] = {}
    for qname, node in classes.items():
        defined[qname] = {
            stmt.name
            for stmt in node.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    cache: dict[str, list[str]] = {}
    for qname in classes:
        _ancestry(qname, bases_resolved, cache)

    by_method: dict[str, set[str]] = defaultdict(set)
    for qname, methods in defined.items():
        for m in methods:
            by_method[m].add(qname)

    override_sets: dict[tuple[str, str], set[str]] = {}
    for method, definers in by_method.items():
        if len(definers) < 2:
            for d in definers:
                override_sets[(d, method)] = {d}
            continue
        for d in definers:
            d_anc = set(_ancestry(d, bases_resolved, cache))
            related = {
                other for other in definers if d_anc & set(_ancestry(other, bases_resolved, cache))
            }
            override_sets[(d, method)] = related or {d}

    return override_sets


def v_poly_for_callable(
    cyclomatic: int,
    call_nodes: list[ast.Call],
    *,
    resolve_call_targets: Callable[[ast.Call], list[tuple[str, str]]],
    override_sets: dict[tuple[str, str], set[str]],
) -> int:
    """v_poly(m) = v(G) + sum(|targets(c)| - 1) for polymorphic calls in m."""
    extra = 0
    for call in call_nodes:
        targets = resolve_call_targets(call)
        if not targets:
            continue
        all_targets: set[str] = set()
        for class_q, method in targets:
            key = (class_q, method)
            if key in override_sets:
                for impl_class in override_sets[key]:
                    all_targets.add(f"{impl_class}.{method}")
            else:
                all_targets.add(f"{class_q}.{method}")
        if len(all_targets) > 1:
            extra += len(all_targets) - 1
    return cyclomatic + extra
