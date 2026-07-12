"""AST extraction and classification of test oracles."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Literal

from py_code_metrics.astutil import leading_docstring, strip_docstring_body

OracleKind = Literal[
    "equality",
    "identity",
    "truthiness",
    "membership",
    "comparison",
    "raises",
    "warns",
    "mock",
    "approx",
    "unittest",
    "tautology",
]

OracleStrength = Literal["none", "weak", "strong", "tautology"]

EXEMPT_MARKERS = frozenset({"smoke", "import_ping", "property", "hypothesis"})
ALLOW_NO_ORACLE_COMMENT = "pcm:allow-no-oracle"

UNITTEST_RAISES = frozenset(
    {
        "assertraises",
        "assertraisesregex",
        "assertwarns",
        "assertwarnsregex",
    }
)
UNITTEST_CM_RAISES = frozenset(
    {
        "assertRaises",
        "assertRaisesRegex",
        "assertWarns",
        "assertWarnsRegex",
    }
)
UNITTEST_WEAK_KIND: dict[str, OracleKind] = {
    "asserttrue": "truthiness",
    "assertfalse": "truthiness",
    "assertis": "identity",
    "assertisnot": "identity",
    "assertisnone": "identity",
    "assertisnotnone": "identity",
    "assertin": "membership",
    "assertnotin": "membership",
}
MOCK_ASSERT_NAMES = frozenset(
    {
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
        "assert_not_called",
        "assert_awaited",
        "assert_awaited_once",
        "assert_awaited_with",
        "assert_awaited_once_with",
        "assert_any_await",
        "assert_has_awaits",
        "assert_not_awaited",
    }
)
_SKIP_DECOS = frozenset({"skip", "skipIf", "skipUnless", "expectedFailure"})


@dataclass
class OracleHit:
    kind: OracleKind
    strength: OracleStrength
    lineno: int


@dataclass
class TestFunctionInfo:
    name: str
    qualified_name: str
    lineno: int
    node: ast.FunctionDef | ast.AsyncFunctionDef
    class_name: str | None = None
    markers: list[str] = field(default_factory=list)
    oracles: list[OracleHit] = field(default_factory=list)
    has_swallowed_error: bool = False
    has_skip_in_except: bool = False
    empty_body: bool = False
    allow_no_oracle: bool = False
    framework_hints: set[str] = field(default_factory=set)


def extract_test_functions(tree: ast.Module) -> list[TestFunctionInfo]:
    """Collect pytest-style and unittest-style test callables from a module AST."""
    tests: list[TestFunctionInfo] = []
    for node in tree.body:
        tests.extend(_tests_from_toplevel(node))
    return tests


def classify_oracle_tier(oracles: list[OracleHit]) -> Literal["none", "weak", "strong"]:
    """Best real oracle wins; tautologies do not count as verification."""
    real = [o for o in oracles if o.strength != "tautology"]
    if not real:
        return "none"
    if any(o.strength == "strong" for o in real):
        return "strong"
    return "weak"


def oracle_kinds(oracles: list[OracleHit]) -> list[str]:
    kinds: list[str] = []
    seen: set[str] = set()
    for o in oracles:
        if o.kind not in seen:
            seen.add(o.kind)
            kinds.append(o.kind)
    return kinds


def _tests_from_toplevel(node: ast.stmt) -> list[TestFunctionInfo]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_name(node.name):
        return [_analyze_test_function(node, class_name=None)]
    if not isinstance(node, ast.ClassDef) or not _is_test_class(node):
        return []
    return [
        _analyze_test_function(item, class_name=node.name)
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_name(item.name)
    ]


def _is_test_name(name: str) -> bool:
    return name.startswith("test")


def _is_test_class(node: ast.ClassDef) -> bool:
    if node.name.startswith("Test"):
        return True
    return any(_attr_name(base) == "TestCase" for base in node.bases)


def _analyze_test_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    class_name: str | None,
) -> TestFunctionInfo:
    qname = f"{class_name}.{node.name}" if class_name else node.name
    info = TestFunctionInfo(
        name=node.name,
        qualified_name=qname,
        lineno=node.lineno,
        node=node,
        class_name=class_name,
        markers=_collect_markers(node),
        empty_body=_is_empty_body(node),
        allow_no_oracle=_has_allow_comment(node),
    )
    if class_name:
        info.framework_hints.add("unittest")
    collector = _OracleCollector(info)
    collector.visit(node)
    info.oracles = collector.oracles
    info.has_swallowed_error = collector.swallowed_error
    info.has_skip_in_except = collector.skip_in_except
    info.framework_hints |= collector.framework_hints
    return info


def _collect_markers(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [m for dec in node.decorator_list if (m := _marker_from_decorator(dec))]


def _marker_from_decorator(dec: ast.expr) -> str | None:
    call = dec if isinstance(dec, ast.Call) else None
    parts = _dotted_parts(call.func if call else dec)
    if len(parts) >= 3 and parts[0] == "pytest" and parts[1] == "mark":
        return parts[2]
    if len(parts) >= 2 and parts[0] == "mark":
        return parts[1]
    if parts and parts[-1] in _SKIP_DECOS:
        return parts[-1].lower()
    return None


def _has_allow_comment(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    doc = leading_docstring(node)
    return doc is not None and ALLOW_NO_ORACLE_COMMENT in doc


def _is_empty_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = strip_docstring_body(node)
    return not body or all(isinstance(s, ast.Pass) for s in body)


class _OracleCollector(ast.NodeVisitor):
    def __init__(self, info: TestFunctionInfo) -> None:
        self.info = info
        self.oracles: list[OracleHit] = []
        self.swallowed_error = False
        self.skip_in_except = False
        self.framework_hints: set[str] = set()
        self._in_except = 0

    def visit_Assert(self, node: ast.Assert) -> None:
        self.oracles.append(_classify_assert_test(node.test, node.lineno))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self._record_context_oracle(item.context_expr)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self._record_context_oracle(item.context_expr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        parts = _dotted_parts(node.func)
        hit = _call_oracle(node)
        if hit is not None:
            self.oracles.append(hit)
            if parts and parts[0] == "self":
                self.framework_hints.add("unittest")
        if self._in_except and _is_skip_call(node):
            self.skip_in_except = True
            self.framework_hints.add("pytest")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_swallowed_handler(node):
            self.swallowed_error = True
        self._in_except += 1
        self.generic_visit(node)
        self._in_except -= 1

    def _record_context_oracle(self, expr: ast.expr) -> None:
        hit = _context_oracle(expr, default_lineno=self.info.lineno)
        if hit is None:
            return
        self.oracles.append(hit)
        if hit.kind in {"raises", "warns"} and _is_pytest_parts(
            _dotted_parts(_call_func(expr) or expr)
        ):
            self.framework_hints.add("pytest")
        elif hit.kind == "raises":
            self.framework_hints.add("unittest")


def _call_func(expr: ast.expr) -> ast.expr | None:
    return expr.func if isinstance(expr, ast.Call) else None


def _is_pytest_parts(parts: list[str]) -> bool:
    return bool(parts) and (parts[0] == "pytest" or "pytest" in parts or len(parts) == 1)


def _context_oracle(expr: ast.expr, *, default_lineno: int) -> OracleHit | None:
    target = _call_func(expr) or expr
    parts = _dotted_parts(target)
    if not parts:
        return None
    lineno = getattr(expr, "lineno", default_lineno)
    last = parts[-1]
    if last in {"raises", "warns"} and _is_pytest_parts(parts):
        kind: OracleKind = "raises" if last == "raises" else "warns"
        return OracleHit(kind, "strong", lineno)
    if last in UNITTEST_CM_RAISES:
        return OracleHit("raises", "strong", lineno)
    return None


def _call_oracle(node: ast.Call) -> OracleHit | None:
    parts = _dotted_parts(node.func)
    if not parts:
        return None
    attr, lower, lineno = parts[-1], parts[-1].lower(), node.lineno
    if attr in MOCK_ASSERT_NAMES:
        return OracleHit("mock", "strong", lineno)
    if parts[0] != "self" or not lower.startswith("assert"):
        return None
    if lower in UNITTEST_RAISES:
        return OracleHit("raises", "strong", lineno)
    if lower in UNITTEST_WEAK_KIND:
        if lower == "asserttrue" and _const_is(node, True):
            return OracleHit("tautology", "tautology", lineno)
        if lower == "assertfalse" and _const_is(node, False):
            return OracleHit("tautology", "tautology", lineno)
        return OracleHit(UNITTEST_WEAK_KIND[lower], "weak", lineno)
    return OracleHit("unittest", "strong", lineno)


def _classify_assert_test(test: ast.expr, lineno: int) -> OracleHit:
    if _is_tautology(test):
        return OracleHit("tautology", "tautology", lineno)
    if isinstance(test, ast.Compare):
        return _classify_compare(test, lineno)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        operand = test.operand
        if isinstance(operand, ast.Compare):
            return _classify_compare(operand, lineno)
        inner = _classify_assert_test(operand, lineno)
        if inner.strength == "tautology":
            return inner
        return OracleHit("truthiness", "weak", lineno)
    if isinstance(test, ast.BoolOp):
        return _combine_oracle_hits(
            [_classify_assert_test(v, lineno) for v in test.values],
            lineno,
        )
    if isinstance(test, ast.Call) and _is_approx_call(test):
        return OracleHit("approx", "strong", lineno)
    return OracleHit("truthiness", "weak", lineno)


def _combine_oracle_hits(parts: list[OracleHit], lineno: int) -> OracleHit:
    """Collapse `and`/`or` assert chains to the strongest constituent oracle."""
    if parts and all(p.strength == "tautology" for p in parts):
        return OracleHit("tautology", "tautology", lineno)
    for strength in ("strong", "weak"):
        hit = next((p for p in parts if p.strength == strength), None)
        if hit is not None:
            return OracleHit(hit.kind, strength, lineno)  # type: ignore[arg-type]
    return OracleHit("truthiness", "weak", lineno)


def _classify_compare(node: ast.Compare, lineno: int) -> OracleHit:
    left, op, right = node.left, node.ops[0], node.comparators[0]
    if _is_approx_call(left) or _is_approx_call(right):
        return OracleHit("approx", "strong", lineno)
    if isinstance(op, (ast.Is, ast.IsNot)):
        if _is_none(right) or _is_none(left):
            return OracleHit("identity", "weak", lineno)
        if _ast_equal(left, right) and isinstance(op, ast.Is):
            return OracleHit("tautology", "tautology", lineno)
        return OracleHit("identity", "strong", lineno)
    if isinstance(op, (ast.In, ast.NotIn)):
        if _is_str_call(left) or _is_str_call(right):
            return OracleHit("membership", "weak", lineno)
        if _is_len_compared_to_zero(node):
            return OracleHit("comparison", "weak", lineno)
        return OracleHit("membership", "strong", lineno)
    if isinstance(op, (ast.Eq, ast.NotEq)):
        if _ast_equal(left, right):
            return OracleHit("tautology", "tautology", lineno)
        return OracleHit("equality", "strong", lineno)
    if _is_len_compared_to_zero(node):
        return OracleHit("comparison", "weak", lineno)
    return OracleHit("comparison", "strong", lineno)


def _is_tautology(test: ast.expr) -> bool:
    if isinstance(test, ast.Constant) and test.value is True:
        return True
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and _ast_equal(test.left, test.comparators[0])
        and isinstance(test.ops[0], (ast.Eq, ast.Is, ast.GtE, ast.LtE))
    )


def _ast_equal(a: ast.expr, b: ast.expr) -> bool:
    return ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_approx_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    parts = _dotted_parts(node.func)
    return parts[-1:] == ["approx"] or parts[-2:] == ["pytest", "approx"]


def _is_str_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _attr_name(node.func) == "str"


def _is_len_compared_to_zero(node: ast.Compare) -> bool:
    """`len(x) > 0` / `len(x) >= 1` style weak checks."""
    if len(node.ops) != 1:
        return False
    left, right, op = node.left, node.comparators[0], node.ops[0]
    if _is_len_call(left) and _is_int_const(right, {0, 1}):
        return isinstance(op, (ast.Gt, ast.GtE, ast.NotEq))
    if _is_len_call(right) and _is_int_const(left, {0, 1}):
        return isinstance(op, (ast.Lt, ast.LtE, ast.NotEq))
    return False


def _is_len_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _attr_name(node.func) == "len"


def _is_int_const(node: ast.expr, values: set[int]) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value in values


def _const_is(call: ast.Call, value: object) -> bool:
    if not call.args or not isinstance(call.args[0], ast.Constant):
        return False
    return call.args[0].value is value


def _is_swallowed_handler(node: ast.ExceptHandler) -> bool:
    """Broad except with pass / ellipsis / bare return and no re-raise."""
    if node.type is not None and not _is_broad_exception_type(node.type):
        return False
    body = node.body
    if not body:
        return True
    if all(isinstance(s, (ast.Pass, ast.Expr)) and _is_pass_or_ellipsis(s) for s in body):
        return True
    return len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is None


def _is_pass_or_ellipsis(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is ...
    )


def _is_broad_exception_type(node: ast.expr) -> bool:
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception_type(elt) for elt in node.elts)
    return _attr_name(node) in {"Exception", "BaseException"}


def _is_skip_call(node: ast.Call) -> bool:
    parts = _dotted_parts(node.func)
    return parts[-1:] == ["skip"] or parts[-2:] == ["pytest", "skip"]


def _attr_name(node: ast.expr) -> str:
    parts = _dotted_parts(node)
    return parts[-1] if parts else ""


def _dotted_parts(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*_dotted_parts(node.value), node.attr]
    return []
