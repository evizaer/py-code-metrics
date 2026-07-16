"""End-to-end analysis on a multi-file fixture package."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.analyze import analyze_path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def test_e2e_sample_pkg():
    report = analyze_path(FIXTURE)
    d = report.to_dict()

    assert d["version"] == 2
    assert d["tool"] == "py-code-metrics"
    assert d["input"]["files_analyzed"] >= 3
    assert d["overall"]["totals"]["modules"] >= 3
    assert d["overall"]["imports"]["cycle_count"] >= 1

    # Find strategy v_poly expansion
    methods = []
    for mod in d["modules"]:
        for cls in mod["classes"]:
            methods.extend(cls["methods"])
            if cls["name"] == "Split":
                assert cls["metrics"]["lcom4"] >= 2

    # Shared helper should have higher fan-in than private micro helper
    by_name = {}
    for mod in d["modules"]:
        for fn in mod["functions"]:
            by_name[fn["name"]] = fn

    if "shared_double" in by_name:
        assert by_name["shared_double"]["fan_in_ext"] >= 2

    # Nested if function has nesting
    if "deep_nest" in by_name:
        assert by_name["deep_nest"]["max_nesting"] >= 3
        assert by_name["deep_nest"]["v_poly"] >= by_name["deep_nest"]["cyclomatic"]


def test_cli_runs(tmp_path: Path):
    import io
    import sys

    from py_code_metrics.cli import main

    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["analyze", str(FIXTURE)])
    finally:
        sys.stdout = old
    assert code == 0
    assert '"tool": "py-code-metrics"' in buf.getvalue()
