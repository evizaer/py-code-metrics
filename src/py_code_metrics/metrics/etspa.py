"""Token counting and ETSPA (Effective Tokens Saved per Abstraction)."""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass

from py_code_metrics.astutil import strip_docstring_body

DEFAULT_CALL_COST = 3.0


@dataclass(frozen=True)
class TokenSplit:
    body_tokens: int
    header_tokens: int


def count_tokens_in_source(source: str) -> int:
    """Count non-comment, non-NL tokens in a source fragment."""
    if not source.strip():
        return 0
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        count = 0
        for tok in tokens:
            if tok.type in (
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENCODING,
                tokenize.ENDMARKER,
            ):
                continue
            count += 1
        return count
    except tokenize.TokenError:
        return len(source.split())


def header_token_count(
    node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]
) -> int:
    """Approximate header tax: def line(s) through colon, plus decorators."""
    fragments: list[str] = []
    for dec in node.decorator_list:
        start = dec.lineno - 1
        end = (dec.end_lineno or dec.lineno) - 1
        fragments.extend(source_lines[start : end + 1])
    # Signature: from def line to body start - 1
    start = node.lineno - 1
    body_start = node.body[0].lineno - 1 if node.body else node.lineno
    fragments.extend(source_lines[start:body_start])
    return count_tokens_in_source("\n".join(fragments))


def body_token_count(node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]) -> int:
    body = strip_docstring_body(node)
    if not body:
        return 0
    start = body[0].lineno - 1
    end = (body[-1].end_lineno or body[-1].lineno) - 1
    return count_tokens_in_source("\n".join(source_lines[start : end + 1]))


def is_trivial_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = strip_docstring_body(node)
    if not body:
        return True
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is ...
    ):
        return True
    if isinstance(stmt, ast.Return):
        return stmt.value is None or isinstance(stmt.value, ast.Constant)
    return False


@dataclass(frozen=True)
class EtspaResult:
    body_tokens: int
    header_tokens: int
    fan_in_ext: int
    mean_call_cost: float
    S: float
    etspa: float
    trivial: bool


def compute_etspa(
    *,
    body_tokens: int,
    header_tokens: int,
    fan_in_ext: int,
    mean_call_cost: float | None = None,
    trivial: bool = False,
) -> EtspaResult:
    C = DEFAULT_CALL_COST if mean_call_cost is None else mean_call_cost
    F = fan_in_ext
    B = body_tokens
    H = header_tokens
    S = (F - 1) * B - H - F * C
    if trivial:
        S = min(0.0, S)
    return EtspaResult(
        body_tokens=B,
        header_tokens=H,
        fan_in_ext=F,
        mean_call_cost=C,
        S=S,
        etspa=S,  # U=1
        trivial=trivial,
    )


def call_site_token_cost(call: ast.Call, source_lines: list[str]) -> int:
    start = call.lineno - 1
    end = (call.end_lineno or call.lineno) - 1
    return max(1, count_tokens_in_source("\n".join(source_lines[start : end + 1])))
