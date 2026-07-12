"""Tests against sut_pkg.prod for P1 linkage checks."""

from prod import add, incidental, multiply


def test_add_strong():
    assert add(2, 3) == 5


def test_add_none():
    add(2, 3)
    incidental(1)


def test_add_weak():
    assert add(2, 3)


def test_multiply_strong():
    assert multiply(2, 4) == 8
