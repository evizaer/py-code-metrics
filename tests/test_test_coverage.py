"""Tests for P1 SUT linkage and coverage ingest."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from py_code_metrics.analyze_tests import analyze_tests_path
from py_code_metrics.cli import main
from py_code_metrics.metrics.test_coverage import load_coverage_json, parse_run_context

SUT = Path(__file__).parent / "fixtures" / "sut_pkg"


def test_resolve_production_calls():
    report = analyze_tests_path(SUT)
    by = {t.qualified_name: t for m in report.modules for t in m.tests}

    assert "prod.add" in by["test_add_strong"].calls_production
    assert by["test_add_strong"].oracle_tier == "strong"
    assert "prod.add" in by["test_add_none"].calls_production
    assert "prod.incidental" in by["test_add_none"].calls_production
    assert by["test_add_none"].oracle_tier == "none"
    assert "prod.multiply" in by["test_multiply_strong"].calls_production


def test_coverage_floors_without_contexts():
    cov = SUT / "coverage_no_contexts.json"
    report = analyze_tests_path(SUT, coverage_path=cov)
    assert report.overall.coverage_line == 87.5
    assert report.overall.coverage_branch == 50.0
    assert report.input["coverage_has_contexts"] is False
    assert report.overall.weak_oracle_covered_line_count == 0
    # incidental covered and only called by none-oracle test
    assert "prod.incidental" in report.overall.unchecked_covered_callables
    assert "prod.add" not in report.overall.unchecked_covered_callables


def test_coverage_weak_oracle_lines_with_contexts():
    cov = SUT / "coverage_with_contexts.json"
    report = analyze_tests_path(SUT, coverage_path=cov)
    assert report.overall.coverage_line == 100.0
    assert report.input["coverage_has_contexts"] is True

    lines = {(item["file"], item["line"]) for item in report.overall.weak_oracle_covered_lines}
    assert ("prod.py", 5) in lines
    assert ("prod.py", 13) in lines
    assert ("prod.py", 9) not in lines  # strong oracle covers multiply

    assert "prod.incidental" in report.overall.unchecked_covered_callables


def test_parse_run_context():
    assert parse_run_context("test_prod.py::test_add_none|run") == (
        "test_prod.py",
        "test_add_none",
    )
    assert parse_run_context("test_prod.py::TestAdd::test_x|setup") is None
    assert parse_run_context("a.py::TestAdd::test_x|run") == ("a.py", "TestAdd.test_x")
    assert parse_run_context("a.py::test_p[1-2]|run") == ("a.py", "test_p")


def test_load_coverage_json_shapes():
    with_ctx = load_coverage_json(SUT / "coverage_with_contexts.json")
    assert with_ctx.has_contexts
    assert 5 in with_ctx.contexts["prod.py"]
    bare = load_coverage_json(SUT / "coverage_no_contexts.json")
    assert not bare.has_contexts
    assert bare.coverage_line == 87.5


def test_cli_coverage_flag():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["--tests", "--coverage", str(SUT / "coverage_with_contexts.json"), str(SUT)])
    finally:
        sys.stdout = old
    assert code == 0
    data = json.loads(buf.getvalue())
    assert data["mode"] == "tests"
    assert data["overall"]["coverage_line"] == 100.0
    assert data["overall"]["weak_oracle_covered_line_count"] >= 1


def test_cli_coverage_requires_tests():
    code = main(["--coverage", str(SUT / "coverage_no_contexts.json"), str(SUT)])
    assert code == 2
