"""Tests for P2 mutation report ingest."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from py_code_metrics.analyze_tests import analyze_tests_path
from py_code_metrics.cli import main
from py_code_metrics.metrics.test_mutation import (
    MutationLoadError,
    load_mutation_json,
)

SUT = Path(__file__).parent / "fixtures" / "sut_pkg"


def test_load_pcm_v1():
    ingest = load_mutation_json(SUT / "mutation_pcm_v1.json")
    assert ingest.format_name == "pcm_v1"
    assert ingest.killed == 8
    assert ingest.survived == 2
    assert ingest.mutation_score == pytest.approx(0.8)
    assert len(ingest.survivors) == 2
    assert ingest.survivors[0].file == "prod.py"
    assert ingest.survivors[0].line == 5


def test_load_mutmut_cicd():
    ingest = load_mutation_json(SUT / "mutation_mutmut_cicd.json")
    assert ingest.format_name == "mutmut_cicd"
    assert ingest.mutation_score == pytest.approx(0.8)
    assert ingest.survivors == []


def test_load_cosmic_ray_ndjson():
    ingest = load_mutation_json(SUT / "mutation_cosmic_ray.ndjson")
    assert ingest.format_name == "cosmic_ray"
    assert ingest.killed == 1
    assert ingest.survived == 2
    assert ingest.mutation_score == pytest.approx(1 / 3)
    lines = {s.line for s in ingest.survivors}
    assert lines == {5, 13}


def test_apply_mutation_survivors():
    report = analyze_tests_path(SUT, mutation_path=SUT / "mutation_pcm_v1.json")
    assert report.overall.mutation_score == pytest.approx(0.8)
    assert report.overall.survivor_count == 2
    assert report.input.mutation_format == "pcm_v1"
    files = {s.file for s in report.overall.survivors}
    assert "prod.py" in files


def test_mutation_overlap_with_coverage():
    report = analyze_tests_path(
        SUT,
        coverage_path=SUT / "coverage_with_contexts.json",
        mutation_path=SUT / "mutation_pcm_v1.json",
    )
    by_line = {s.line: s for s in report.overall.survivors}
    assert "weak_oracle_covered_line" in by_line[5].overlap_flags
    assert "unchecked_covered_callable" in by_line[13].overlap_flags


def test_cli_mutation_flag():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["--tests", "--mutation", str(SUT / "mutation_pcm_v1.json"), str(SUT)])
    finally:
        sys.stdout = old
    assert code == 0
    data = json.loads(buf.getvalue())
    assert data["overall"]["survivor_count"] == 2
    assert data["overall"]["mutation_score"] == pytest.approx(0.8)


def test_cli_mutation_requires_tests():
    code = main(["--mutation", str(SUT / "mutation_pcm_v1.json"), str(SUT)])
    assert code == 2


def test_unknown_mutation_shape(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(MutationLoadError):
        load_mutation_json(bad)


def test_delta_filters_survivors(monkeypatch: pytest.MonkeyPatch):
    import py_code_metrics.analyze_tests as at

    monkeypatch.setattr(
        at,
        "changed_python_paths",
        lambda root: (["prod.py", "test_prod.py"], None),
    )
    report = analyze_tests_path(
        SUT,
        mutation_path=SUT / "mutation_pcm_v1.json",
        delta=True,
    )
    assert report.overall.survivor_count == 2
    assert all(s.file == "prod.py" for s in report.overall.survivors)
