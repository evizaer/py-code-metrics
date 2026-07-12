"""Unit tests for local complexity metrics."""

from __future__ import annotations

import ast

from py_code_metrics.metrics.complexity import analyze_function_body


def _func(src: str) -> ast.FunctionDef:
    tree = ast.parse(src)
    return tree.body[0]  # type: ignore[return-value]


def test_simple_function_cc_one():
    node = _func("def f(x):\n    return x\n")
    m = analyze_function_body(node)
    assert m.cyclomatic == 1
    assert m.max_nesting == 0
    assert m.returns == 1


def test_nested_ifs_raise_nesting_and_cognitive():
    node = _func(
        """
def f(a, b, c):
    if a:
        if b:
            if c:
                return 1
    return 0
"""
    )
    m = analyze_function_body(node)
    assert m.cyclomatic == 4  # 1 + 3 ifs
    assert m.max_nesting == 3
    assert m.cognitive > m.cyclomatic  # nesting penalty


def test_flat_match_cheaper_cognitive_than_nested_ifs():
    nested = _func(
        """
def f(x, y, z):
    if x:
        if y:
            if z:
                return 1
            return 2
        return 3
    return 0
"""
    )
    flat = _func(
        """
def f(x):
    match x:
        case 1:
            return 1
        case 2:
            return 2
        case 3:
            return 3
        case _:
            return 0
"""
    )
    n = analyze_function_body(nested)
    f = analyze_function_body(flat)
    assert f.max_nesting < n.max_nesting
    assert n.max_nesting == 3
    assert f.cognitive < n.cognitive


def test_boolop_adds_cc():
    node = _func(
        """
def f(a, b, c):
    if a and b or c:
        return 1
    return 0
"""
    )
    m = analyze_function_body(node)
    # 1 base + 1 if + 2 bool extras (and, or)
    assert m.cyclomatic >= 3
