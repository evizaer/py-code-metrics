"""Tests for P0 static test-quality (oracle / smell) analysis."""

from __future__ import annotations

import ast
from pathlib import Path

from py_code_metrics.analyze_tests import analyze_tests_path
from py_code_metrics.discover import discover_tests, is_test_file
from py_code_metrics.metrics.test_oracles import (
    classify_oracle_tier,
    extract_test_functions,
)
from py_code_metrics.metrics.test_smells import derive_smells, summarize_oracles

FAKE = Path(__file__).parent / "fixtures" / "fake_tests"
REPO_TESTS = Path(__file__).parent


def _by_name(src: str) -> dict:
    tree = ast.parse(src)
    infos = extract_test_functions(tree)
    return {i.qualified_name: i for i in infos}


def test_discover_tests_finds_test_modules_only():
    found = discover_tests(REPO_TESTS)
    names = {p.name for p in found}
    assert "test_complexity.py" in names
    assert "a.py" not in names  # fixture package modules
    assert all(is_test_file(p) for p in found)


def test_worked_examples_oracle_tiers():
    src = (FAKE / "test_fake_oracles.py").read_text(encoding="utf-8")
    by = _by_name(src)

    assert classify_oracle_tier(by["test_add_no_oracle"].oracles) == "none"
    assert classify_oracle_tier(by["test_add_tautology"].oracles) == "none"
    assert classify_oracle_tier(by["test_add_weak"].oracles) == "weak"
    assert classify_oracle_tier(by["test_add_not_none"].oracles) == "weak"
    assert classify_oracle_tier(by["test_add_strong"].oracles) == "strong"
    assert classify_oracle_tier(by["test_parse_bad_json"].oracles) == "strong"
    assert classify_oracle_tier(by["test_len_weak"].oracles) == "weak"
    assert classify_oracle_tier(by["TestAdd.test_equal_strong"].oracles) == "strong"
    assert classify_oracle_tier(by["TestAdd.test_true_weak"].oracles) == "weak"
    assert classify_oracle_tier(by["TestAdd.test_no_assert"].oracles) == "none"


def test_smell_codes_on_fakes():
    src = (FAKE / "test_fake_oracles.py").read_text(encoding="utf-8")
    by = _by_name(src)

    def codes(name: str) -> set[str]:
        return set(derive_smells(by[name])[0])

    assert "NO_ORACLE" in codes("test_add_no_oracle")
    assert "TAUTOLOGY" in codes("test_add_tautology")
    assert "NO_ORACLE" in codes("test_add_tautology")
    assert "WEAK_ORACLE" in codes("test_add_weak")
    assert codes("test_add_strong") == set()
    assert "SWALLOWED_ERROR" in codes("test_parse_swallowed")
    assert "EMPTY_BODY" in codes("test_empty")
    assert "SKIP_IN_EXCEPT" in codes("test_skip_in_except")
    assert "NO_ORACLE" in codes("TestAdd.test_no_assert")

    smells, severity, exempt = derive_smells(by["test_import_smoke"])
    assert exempt
    assert severity == "info"
    assert "TAUTOLOGY" in smells


def test_analyze_tests_path_fake_corpus():
    report = analyze_tests_path(FAKE)
    d = report.to_dict()
    assert d["mode"] == "tests"
    assert d["overall"]["test_count"] >= 12
    assert d["overall"]["high_severity_count"] >= 4
    assert d["overall"]["frac_oracle_none"] > 0
    assert d["thresholds"]["no_oracle"] == "high"

    by_qname = {t["qualified_name"]: t for m in d["modules"] for t in m["tests"]}
    assert by_qname["test_add_strong"]["oracle_tier"] == "strong"
    assert by_qname["test_add_strong"]["severity"] == "info"
    assert by_qname["test_add_no_oracle"]["severity"] == "high"
    assert "NO_ORACLE" in by_qname["test_add_no_oracle"]["smell_codes"]


def test_repo_tests_are_mostly_strong():
    """This project's own suite should be predominantly strong oracles."""
    report = analyze_tests_path(REPO_TESTS)
    # Exclude the intentional fake fixture module from the health check.
    real = [t for m in report.modules if "fixtures" not in m.path for t in m.tests]
    assert real
    strong = sum(1 for t in real if t.oracle_tier == "strong")
    assert strong / len(real) >= 0.8
    high = [t for t in real if t.severity == "high"]
    assert high == [], f"unexpected high-severity tests: {high}"


def test_cli_tests_flag():
    import io
    import sys

    from py_code_metrics.cli import main

    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["--tests", str(FAKE)])
    finally:
        sys.stdout = old
    assert code == 0
    out = buf.getvalue()
    assert '"mode": "tests"' in out
    assert "NO_ORACLE" in out


def test_summarize_counts_exclude_tautology():
    src = """
def test_t():
    assert True
    assert 1 == 2
"""
    info = _by_name(src)["test_t"]
    tier, kinds, count = summarize_oracles(info)
    assert tier == "strong"
    assert count == 1
    assert "equality" in kinds
    assert "tautology" in kinds
