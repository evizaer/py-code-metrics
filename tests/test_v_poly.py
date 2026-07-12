"""Tests for v_poly override expansion."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.analyze import analyze_path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def test_v_poly_on_chorus():
    report = analyze_path(FIXTURE)
    chorus = None
    for mod in report.modules:
        for fn in mod.functions:
            if fn.name == "chorus":
                chorus = fn
    assert chorus is not None
    assert chorus.cyclomatic == 1
    # Animal/Dog/Cat.speak → +2 expansion
    assert chorus.v_poly == 3
