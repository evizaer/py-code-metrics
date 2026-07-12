"""Class cohesion metrics: LCOM4, WMC, NOM."""

from __future__ import annotations

import ast


def _method_kind(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "staticmethod":
            return "staticmethod"
        if isinstance(dec, ast.Name) and dec.id == "classmethod":
            return "classmethod"
        if isinstance(dec, ast.Attribute) and dec.attr in ("staticmethod", "classmethod"):
            return dec.attr
    return "method"


def _self_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    kind = _method_kind(node)
    if kind == "staticmethod":
        return None
    if node.args.args:
        return node.args.args[0].arg
    return None


def _nodes_in_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """AST nodes in this method, excluding nested function/class defs."""
    result: list[ast.AST] = []

    def walk(n: ast.AST, *, inside_nested: bool = False) -> None:
        if inside_nested:
            return
        result.append(n)
        for child in ast.iter_child_nodes(n):
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and child is not node
            ):
                continue
            walk(child)

    for stmt in node.body:
        walk(stmt)
    return result


def _instance_attrs_used(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    self_name = _self_name(node)
    if not self_name:
        return set()
    attrs: set[str] = set()
    for child in _nodes_in_method(node):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == self_name
        ):
            attrs.add(child.attr)
    return attrs


def _methods_called_on_self(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    self_name = _self_name(node)
    if not self_name:
        return set()
    called: set[str] = set()
    for child in _nodes_in_method(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == self_name
        ):
            called.add(child.func.attr)
    return called


def compute_lcom4(class_node: ast.ClassDef) -> tuple[int, int, dict[str, int]]:
    """
    Return (LCOM4, NOM, method_name -> 1 placeholder).

    LCOM4 = number of connected components in the method graph where
    methods share an instance field or one calls the other.
    """
    methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        stmt
        for stmt in class_node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    nom = len(methods)
    if nom == 0:
        return 0, 0, {}

    names = [m.name for m in methods]
    name_set = set(names)
    attrs_by_method = {m.name: _instance_attrs_used(m) for m in methods}
    calls_by_method = {m.name: _methods_called_on_self(m) for m in methods}

    adj: dict[str, set[str]] = {n: set() for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if attrs_by_method[a] & attrs_by_method[b]:
                adj[a].add(b)
                adj[b].add(a)
        for callee in calls_by_method[a]:
            if callee in name_set:
                adj[a].add(callee)
                adj[callee].add(a)

    seen: set[str] = set()
    components = 0
    for n in names:
        if n in seen:
            continue
        components += 1
        stack = [n]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj[cur] - seen)

    return components, nom, {m.name: 1 for m in methods}


def compute_wmc(method_cyclomatics: dict[str, int]) -> int:
    return sum(method_cyclomatics.values())
