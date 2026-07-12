"""Tests for ETSPA and expression metrics."""

from __future__ import annotations

import ast

from py_code_metrics.metrics.etspa import compute_etspa, is_trivial_body
from py_code_metrics.metrics.expression import analyze_expression


def test_etspa_shared_helper_beats_micro_helpers():
    shared = compute_etspa(body_tokens=100, header_tokens=5, fan_in_ext=40, mean_call_cost=3)
    micros = [
        compute_etspa(body_tokens=10, header_tokens=5, fan_in_ext=4, mean_call_cost=3)
        for _ in range(10)
    ]
    assert sum(m.S for m in micros) < shared.S


def test_etspa_fan_in_one_is_nonpositive_or_low():
    r = compute_etspa(body_tokens=20, header_tokens=8, fan_in_ext=1, mean_call_cost=3)
    # S = 0*B - H - F*C = -H - C < 0
    assert r.S < 0


def test_trivial_body_forced_nonpositive():
    node = ast.parse("def f():\n    pass\n").body[0]
    assert is_trivial_body(node)  # type: ignore[arg-type]
    r = compute_etspa(body_tokens=1, header_tokens=3, fan_in_ext=5, mean_call_cost=1, trivial=True)
    assert r.S <= 0


def test_car_high_for_call_heavy_leaf():
    node = ast.parse(
        """
def leaf(rows):
    return list(filter(None, map(str, rows)))
"""
    ).body[0]
    expr = analyze_expression(node, body_tokens=20)  # type: ignore[arg-type]
    assert expr.call_count >= 3
    assert expr.car > 1.0
    assert expr.cvr > 0


def test_lmd_high_for_accumulator_loop():
    node = ast.parse(
        """
def accum(xs):
    out = []
    for x in xs:
        out.append(x)
    return out
"""
    ).body[0]
    expr = analyze_expression(node, body_tokens=30)  # type: ignore[arg-type]
    assert expr.local_stores >= 1
    assert expr.lmd > 0
