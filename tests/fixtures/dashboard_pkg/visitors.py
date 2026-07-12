"""AST visitor — dispatch_exempt methods should not count as unpaid debt."""

from __future__ import annotations

import ast


class Walk(ast.NodeVisitor):
    def visit_Name(self, node: ast.Name) -> None:
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        self.generic_visit(node)
