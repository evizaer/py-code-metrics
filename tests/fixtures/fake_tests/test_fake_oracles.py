"""Intentional fake / weak / clean tests for oracle classifier validation.

These are not executed as part of the project suite (fixtures are excluded from
discovery when analyzing tests/ with name filters — this file is only under
fixtures/ and is analyzed explicitly by unit tests).
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    return a + b


def parse(text: str) -> dict:
    import json

    return json.loads(text)


# HIGH — no oracle (theater)
def test_add_no_oracle():
    add(2, 3)


# HIGH — tautology
def test_add_tautology():
    result = add(2, 3)
    assert True
    assert result == result


# LOW — weak oracle
def test_add_weak():
    assert add(2, 3)


# LOW — weak non-null
def test_add_not_none():
    assert add(2, 3) is not None


# CLEAN — strong oracle
def test_add_strong():
    assert add(2, 3) == 5


# HIGH — swallowed failure
def test_parse_swallowed():
    try:
        parse("{")
    except Exception:
        pass


# CLEAN — typed exception oracle
def test_parse_bad_json():
    import pytest

    with pytest.raises(ValueError, match="Expecting"):
        parse("{")


# HIGH — empty body
def test_empty():
    pass


# CLEAN — exempt smoke (no oracle but marked)
import pytest


@pytest.mark.smoke
def test_import_smoke():
    assert True  # still tautology; smoke demotes severity


# HIGH — skip in except
def test_skip_in_except():
    try:
        parse("{")
    except Exception:
        pytest.skip("whatever")


# Weak len check
def test_len_weak():
    assert len([1, 2, 3]) > 0


# Unittest-style
import unittest


class TestAdd(unittest.TestCase):
    def test_equal_strong(self):
        self.assertEqual(add(2, 3), 5)

    def test_true_weak(self):
        self.assertTrue(add(2, 3))

    def test_no_assert(self):
        add(1, 1)
