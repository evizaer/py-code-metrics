"""Local complexity metrics: cyclomatic, cognitive, nesting, size."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class LocalComplexity:
    cyclomatic: int
    cognitive: int
    max_nesting: int
    params: int
    statements: int
    returns: int


def _param_count(args: ast.arguments) -> int:
    count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg is not None:
        count += 1
    if args.kwarg is not None:
        count += 1
    return count


class _ComplexityVisitor(ast.NodeVisitor):
    """Compute McCabe-style CC, Sonar-style cognitive complexity, nesting."""

    def __init__(self) -> None:
        self.cyclomatic = 1
        self.cognitive = 0
        self.max_nesting = 0
        self.statements = 0
        self.returns = 0
        self._nesting = 0
        self._cognitive_nesting = 0

    def _enter_nest(self) -> None:
        self._nesting += 1
        self.max_nesting = max(self.max_nesting, self._nesting)

    def _leave_nest(self) -> None:
        self._nesting -= 1

    def _add_cognitive(self, base: int = 1) -> None:
        self.cognitive += base + self._cognitive_nesting

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_If(self, node: ast.If) -> None:
        self.statements += 1
        self.cyclomatic += 1
        self._add_cognitive(1)
        self._enter_nest()
        prev = self._cognitive_nesting
        self._cognitive_nesting += 1
        self.visit(node.test)
        for stmt in node.body:
            self.visit(stmt)
        self._cognitive_nesting = prev
        self._leave_nest()
        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                self.visit(node.orelse[0])
            else:
                self.cognitive += 1
                self._enter_nest()
                prev = self._cognitive_nesting
                self._cognitive_nesting += 1
                for stmt in node.orelse:
                    self.visit(stmt)
                self._cognitive_nesting = prev
                self._leave_nest()

    def visit_For(self, node: ast.For) -> None:
        self.statements += 1
        self.cyclomatic += 1
        self._add_cognitive(1)
        self._enter_nest()
        prev = self._cognitive_nesting
        self._cognitive_nesting += 1
        self.visit(node.target)
        self.visit(node.iter)
        for stmt in node.body:
            self.visit(stmt)
        self._cognitive_nesting = prev
        self._leave_nest()
        if node.orelse:
            self.cognitive += 1
            for stmt in node.orelse:
                self.visit(stmt)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit_For(node)  # type: ignore[arg-type]

    def visit_While(self, node: ast.While) -> None:
        self.statements += 1
        self.cyclomatic += 1
        self._add_cognitive(1)
        self._enter_nest()
        prev = self._cognitive_nesting
        self._cognitive_nesting += 1
        self.visit(node.test)
        for stmt in node.body:
            self.visit(stmt)
        self._cognitive_nesting = prev
        self._leave_nest()
        if node.orelse:
            self.cognitive += 1
            for stmt in node.orelse:
                self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        self.statements += 1
        for item in node.items:
            self.visit(item)
        self._enter_nest()
        for stmt in node.body:
            self.visit(stmt)
        self._leave_nest()

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.visit_With(node)  # type: ignore[arg-type]

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.cyclomatic += 1
        self._add_cognitive(1)
        self._enter_nest()
        prev = self._cognitive_nesting
        self._cognitive_nesting += 1
        if node.type is not None:
            self.visit(node.type)
        for stmt in node.body:
            self.visit(stmt)
        self._cognitive_nesting = prev
        self._leave_nest()

    def visit_Try(self, node: ast.Try) -> None:
        self.statements += 1
        for stmt in node.body:
            self.visit(stmt)
        for handler in node.handlers:
            self.visit(handler)
        for stmt in node.orelse:
            self.visit(stmt)
        for stmt in node.finalbody:
            self.visit(stmt)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.statements += 1
        self.cyclomatic += 1
        self._add_cognitive(1)
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        extra = max(0, len(node.values) - 1)
        self.cyclomatic += extra
        self.cognitive += extra
        for value in node.values:
            self.visit(value)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.cyclomatic += 1
        self._add_cognitive(1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.cyclomatic += 1
        self._add_cognitive(1)
        for if_clause in node.ifs:
            self.cyclomatic += 1
            self._add_cognitive(1)
            self.visit(if_clause)
        self.visit(node.target)
        self.visit(node.iter)

    def visit_Match(self, node: ast.Match) -> None:
        self.statements += 1
        self.visit(node.subject)
        for case in node.cases:
            self.cyclomatic += 1
            self.cognitive += 1
            if case.guard is not None:
                self.cyclomatic += 1
                self.cognitive += 1
                self.visit(case.guard)
            for stmt in case.body:
                self.visit(stmt)

    def visit_Return(self, node: ast.Return) -> None:
        self.statements += 1
        self.returns += 1
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.statements += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.statements += 1
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.statements += 1
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.statements += 1
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        self.statements += 1
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        self.statements += 1
        self.generic_visit(node)

    def visit_Pass(self, node: ast.Pass) -> None:
        self.statements += 1

    def visit_Break(self, node: ast.Break) -> None:
        self.statements += 1
        self.cognitive += 1

    def visit_Continue(self, node: ast.Continue) -> None:
        self.statements += 1
        self.cognitive += 1


def analyze_function_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> LocalComplexity:
    visitor = _ComplexityVisitor()
    for i, stmt in enumerate(node.body):
        if (
            i == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue
        visitor.visit(stmt)

    return LocalComplexity(
        cyclomatic=visitor.cyclomatic,
        cognitive=visitor.cognitive,
        max_nesting=visitor.max_nesting,
        params=_param_count(node.args),
        statements=visitor.statements,
        returns=visitor.returns,
    )


def effective_param_count(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    is_method: bool,
    is_classmethod: bool,
) -> int:
    """Parameter count excluding implicit self/cls for methods."""
    total = _param_count(node.args)
    if is_method or is_classmethod:
        return max(0, total - 1)
    return total
