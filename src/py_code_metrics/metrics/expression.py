"""Expression-oriented metrics: CAR, LMD, CVR."""

from __future__ import annotations

import ast
from dataclasses import dataclass

DEFAULT_COMBINATOR_NAMES = frozenset(
    {
        "map",
        "filter",
        "reduce",
        "zip",
        "sorted",
        "reversed",
        "enumerate",
        "any",
        "all",
        "sum",
        "min",
        "max",
        "partial",
        "compose",
        "pipe",
        "chain",
        "groupby",
        "starmap",
        "accumulate",
        "islice",
        "takewhile",
        "dropwhile",
        "compress",
        "product",
        "permutations",
        "combinations",
    }
)

MUTATING_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "update",
        "setdefault",
        "add",
        "discard",
    }
)


@dataclass(frozen=True)
class ExpressionMetrics:
    call_count: int
    assign_count: int
    local_stores: int
    comprehension_count: int
    combinator_hits: int
    car: float
    lmd: float
    cvr: float


def _callee_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _ExpressionVisitor(ast.NodeVisitor):
    def __init__(self, param_names: set[str], combinators: frozenset[str]) -> None:
        self.param_names = param_names
        self.combinators = combinators
        self.call_count = 0
        self.assign_count = 0
        self.local_stores = 0
        self.comprehension_count = 0
        self.combinator_hits = 0
        self._locals: set[str] = set(param_names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        self.call_count += 1
        name = _callee_name(node.func)
        if name and name in self.combinators:
            self.combinator_hits += 1
        # Mutating method on a local counts as a local store
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in MUTATING_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self._locals
        ):
            self.local_stores += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.assign_count += 1
        for target in node.targets:
            self._count_store(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.assign_count += 1
            self._count_store(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.assign_count += 1
        self._count_store(node.target)
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.comprehension_count += 1
        self.combinator_hits += 1
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self.comprehension_count += 1
        self.combinator_hits += 1
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.comprehension_count += 1
        self.combinator_hits += 1
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self.comprehension_count += 1
        self.combinator_hits += 1
        self.generic_visit(node)

    def _count_store(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.local_stores += 1
            self._locals.add(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            for elt in target.elts:
                self._count_store(elt)
        elif isinstance(target, ast.Starred):
            self._count_store(target.value)


def analyze_expression(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    body_tokens: int,
    combinators: frozenset[str] = DEFAULT_COMBINATOR_NAMES,
) -> ExpressionMetrics:
    params = {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
    if node.args.vararg:
        params.add(node.args.vararg.arg)
    if node.args.kwarg:
        params.add(node.args.kwarg.arg)

    visitor = _ExpressionVisitor(params, combinators)
    for i, stmt in enumerate(node.body):
        if (
            i == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue
        visitor.visit(stmt)

    car = visitor.call_count / (1 + visitor.assign_count)
    lmd = (visitor.local_stores / body_tokens) if body_tokens > 0 else 0.0
    denom = visitor.call_count + visitor.comprehension_count
    cvr = (visitor.combinator_hits / denom) if denom > 0 else 0.0

    return ExpressionMetrics(
        call_count=visitor.call_count,
        assign_count=visitor.assign_count,
        local_stores=visitor.local_stores,
        comprehension_count=visitor.comprehension_count,
        combinator_hits=visitor.combinator_hits,
        car=car,
        lmd=lmd,
        cvr=cvr,
    )
