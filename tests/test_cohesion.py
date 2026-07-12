"""Tests for LCOM4 cohesion."""

from __future__ import annotations

import ast

from py_code_metrics.metrics.cohesion import compute_lcom4, compute_wmc


def test_lcom4_cohesive_class():
    tree = ast.parse(
        """
class C:
    def __init__(self):
        self.x = 1
    def get(self):
        return self.x
    def bump(self):
        self.x += 1
"""
    )
    lcom4, nom, _ = compute_lcom4(tree.body[0])  # type: ignore[arg-type]
    assert nom == 3
    assert lcom4 == 1


def test_lcom4_split_class():
    tree = ast.parse(
        """
class C:
    def __init__(self):
        self.a = 1
        self.b = 2
    def use_a(self):
        return self.a
    def use_b(self):
        return self.b
"""
    )
    lcom4, nom, _ = compute_lcom4(tree.body[0])  # type: ignore[arg-type]
    assert nom == 3
    # __init__ shares both attrs so may connect use_a and use_b via __init__
    # If __init__ uses both a and b, components collapse to 1.
    # Use a class without shared __init__ fields:
    tree2 = ast.parse(
        """
class C:
    def use_a(self):
        return self.a
    def set_a(self):
        self.a = 1
    def use_b(self):
        return self.b
    def set_b(self):
        self.b = 2
"""
    )
    lcom4, nom, _ = compute_lcom4(tree2.body[0])  # type: ignore[arg-type]
    assert nom == 4
    assert lcom4 == 2


def test_wmc_sum():
    assert compute_wmc({"a": 3, "b": 5}) == 8
