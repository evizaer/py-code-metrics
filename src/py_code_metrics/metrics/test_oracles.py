"""AST extraction and classification of test oracles."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Literal

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

UNITTEST_ASSERT_PREFIXES = (
    "assertEqual",
    "assertnotequal",
    "assertalmostequal",
    "assertnotalmostequal",
    "assertdictEqual",
    "assertlistequal",
    "asserttupleequal",
    "assertsetequal",
    "assertsequenceequal",
    "assertcountequal",
    "assertmultilinesequal",
    "assertlessequal",
    "assertgreaterequal",
    "assertless",
    "assertgreater",
    "assertregex",
    "assertnotregex",
    "assertraises",
    "assertraisesregex",
    "assertraiseswarning",
    "assertwarns",
    "assertwarnsregex",
    "assertlogs",
    "assertnocalls",
)

UNITTEST_WEAK = frozenset(
    {
        "asserttrue",
        "assertfalse",
        "assertis",
        "assertisnot",
        "assertisnone",
        "assertisnotnone",
        "assertin",
        "assertnotin",
    }
)

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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_name(node.name):
            tests.append(_analyze_test_function(node, class_name=None))
        elif isinstance(node, ast.ClassDef) and _is_test_class(node):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_name(
                    item.name
                ):
                    tests.append(_analyze_test_function(item, class_name=node.name))
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


def _is_test_name(name: str) -> bool:
    return name.startswith("test")


def _is_test_class(node: ast.ClassDef) -> bool:
    if node.name.startswith("Test"):
        return True
    for base in node.bases:
        if _attr_name(base) in {"TestCase", "unittest.TestCase"}:
            return True
        if isinstance(base, ast.Attribute) and base.attr == "TestCase":
            return True
    return False


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
    markers: list[str] = []
    for dec in node.decorator_list:
        mark = _marker_from_decorator(dec)
        if mark:
            markers.append(mark)
    return markers


def _marker_from_decorator(dec: ast.expr) -> str | None:
    # @pytest.mark.X / @pytest.mark.X(...)
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    parts = _dotted_parts(target)
    if len(parts) >= 3 and parts[0] == "pytest" and parts[1] == "mark":
        return parts[2]
    if len(parts) >= 2 and parts[0] == "mark":
        return parts[1]
    # @unittest.skip / @skip
    if parts and parts[-1] in {"skip", "skipIf", "skipUnless", "expectedFailure"}:
        return parts[-1].lower()
    return None


def _has_allow_comment(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    # Decorators / leading comments are not on the node; check docstring / body strings.
    return (
        bool(node.body)
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
        and ALLOW_NO_ORACLE_COMMENT in node.body[0].value.value
    )


def _is_empty_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return True
    return all(isinstance(s, ast.Pass) for s in body)


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
            self._maybe_context_oracle(item.context_expr)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self._maybe_context_oracle(item.context_expr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._maybe_call_oracle(node)
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

    def _maybe_context_oracle(self, expr: ast.expr) -> None:
        call = expr if isinstance(expr, ast.Call) else None
        target = call.func if call else expr
        parts = _dotted_parts(target)
        lineno = getattr(expr, "lineno", self.info.lineno)
        if (
            parts
            and parts[-1] == "raises"
            and (parts == ["raises"] or parts[:1] == ["pytest"] or "pytest" in parts)
        ):
            self.framework_hints.add("pytest")
            self.oracles.append(OracleHit("raises", "strong", lineno))
            return
        if (
            parts
            and parts[-1] == "warns"
            and (parts == ["warns"] or parts[:1] == ["pytest"] or "pytest" in parts)
        ):
            self.framework_hints.add("pytest")
            self.oracles.append(OracleHit("warns", "strong", lineno))
            return
        if parts and parts[-1] in {
            "assertRaises",
            "assertRaisesRegex",
            "assertWarns",
            "assertWarnsRegex",
        }:
            self.framework_hints.add("unittest")
            self.oracles.append(OracleHit("raises", "strong", lineno))

    def _maybe_call_oracle(self, node: ast.Call) -> None:
        parts = _dotted_parts(node.func)
        if not parts:
            return
        attr = parts[-1]
        lower = attr.lower()
        lineno = node.lineno

        if attr in MOCK_ASSERT_NAMES:
            self.oracles.append(OracleHit("mock", "strong", lineno))
            return

        if parts[0] == "self" and lower.startswith("assert"):
            self.framework_hints.add("unittest")
            if lower in {"assertraises", "assertraisesregex", "assertwarns", "assertwarnsregex"}:
                self.oracles.append(OracleHit("raises", "strong", lineno))
            elif lower in UNITTEST_WEAK:
                # assertIsNone / assertTrue etc.
                kind: OracleKind = "truthiness"
                if "none" in lower:
                    kind = "identity"
                elif lower in {"assertin", "assertnotin"}:
                    kind = "membership"
                elif lower in {"assertis", "assertisnot"}:
                    kind = "identity"
                strength: OracleStrength = "weak"
                if lower in {"assertfalse"} and _const_is(node, False):
                    strength = "tautology"
                    kind = "tautology"
                if lower in {"asserttrue"} and _const_is(node, True):
                    strength = "tautology"
                    kind = "tautology"
                hit_kind: OracleKind = "tautology" if strength == "tautology" else kind
                self.oracles.append(OracleHit(hit_kind, strength, lineno))
            elif any(lower.startswith(p) for p in UNITTEST_ASSERT_PREFIXES) or lower.startswith(
                "assert"
            ):
                self.oracles.append(OracleHit("unittest", "strong", lineno))
            return

        # pytest.approx used inside comparisons is handled in assert classification;
        # bare pytest.fail is not an oracle.


def _classify_assert_test(test: ast.expr, lineno: int) -> OracleHit:
    if _is_tautology(test):
        return OracleHit("tautology", "tautology", lineno)

    if isinstance(test, ast.Compare):
        return _classify_compare(test, lineno)

    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _classify_assert_test(test.operand, lineno)
        if inner.strength == "tautology":
            return inner
        # `assert not x` is still truthiness-tier unless operand is a comparison we already handled
        if isinstance(test.operand, ast.Compare):
            return inner
        return OracleHit("truthiness", "weak", lineno)

    if isinstance(test, ast.BoolOp):
        parts = [_classify_assert_test(v, lineno) for v in test.values]
        if any(p.strength == "tautology" for p in parts) and all(
            p.strength in {"tautology", "none"} for p in parts
        ):
            return OracleHit("tautology", "tautology", lineno)
        if any(p.strength == "strong" for p in parts):
            # Prefer first strong kind
            strong = next(p for p in parts if p.strength == "strong")
            return OracleHit(strong.kind, "strong", lineno)
        if any(p.strength == "weak" for p in parts):
            weak = next(p for p in parts if p.strength == "weak")
            return OracleHit(weak.kind, "weak", lineno)
        return OracleHit("truthiness", "weak", lineno)

    if isinstance(test, ast.Call) and _is_approx_call(test):
        return OracleHit("approx", "strong", lineno)

    # Bare name / call / attribute → truthiness
    return OracleHit("truthiness", "weak", lineno)


def _classify_compare(node: ast.Compare, lineno: int) -> OracleHit:
    # Chain: only inspect first comparator pair for classification.
    left = node.left
    op = node.ops[0]
    right = node.comparators[0]

    if _is_approx_call(left) or _is_approx_call(right):
        return OracleHit("approx", "strong", lineno)

    if isinstance(op, (ast.Is, ast.IsNot)):
        if _is_none(right) or _is_none(left):
            # `x is not None` / `x is None` — weak identity
            return OracleHit("identity", "weak", lineno)
        if _ast_equal(left, right) and isinstance(op, ast.Is):
            return OracleHit("tautology", "tautology", lineno)
        return OracleHit("identity", "strong", lineno)

    if isinstance(op, (ast.In, ast.NotIn)):
        # `"x" in str(y)` style is weak; membership with literal container can be strong
        if _is_str_call(left) or _is_str_call(right):
            return OracleHit("membership", "weak", lineno)
        if _is_len_gt_zero_shape(node):
            return OracleHit("comparison", "weak", lineno)
        return OracleHit("membership", "strong", lineno)

    if isinstance(op, (ast.Eq, ast.NotEq)):
        if _ast_equal(left, right):
            return OracleHit("tautology", "tautology", lineno)
        return OracleHit("equality", "strong", lineno)

    # Inequalities (< > <= >=)
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
    left, right = node.left, node.comparators[0]
    op = node.ops[0]
    if _is_len_call(left) and _is_int_const(right, {0, 1}):
        return isinstance(op, (ast.Gt, ast.GtE, ast.NotEq))
    if _is_len_call(right) and _is_int_const(left, {0, 1}):
        return isinstance(op, (ast.Lt, ast.LtE, ast.NotEq))
    return False


def _is_len_gt_zero_shape(node: ast.Compare) -> bool:
    return _is_len_compared_to_zero(node)


def _is_len_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _attr_name(node.func) == "len"


def _is_int_const(node: ast.expr, values: set[int]) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value in values


def _const_is(call: ast.Call, value: object) -> bool:
    if not call.args:
        return False
    arg = call.args[0]
    return isinstance(arg, ast.Constant) and arg.value is value


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
    name = _attr_name(node)
    return name in {"Exception", "BaseException"}


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
