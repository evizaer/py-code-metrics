"""Small AST helpers shared across metric passes."""

from __future__ import annotations

import ast


def leading_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    if not node.body:
        return None
    head = node.body[0]
    if (
        isinstance(head, ast.Expr)
        and isinstance(head.value, ast.Constant)
        and isinstance(head.value.value, str)
    ):
        return head.value.value
    return None


def strip_docstring_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if leading_docstring(node) is not None:
        return body[1:]
    return body
