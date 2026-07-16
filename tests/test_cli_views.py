"""CLI subcommand smoke tests for agent views."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from py_code_metrics.analyze import analyze_path
from py_code_metrics.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def _capture(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


def test_board_and_hotspots_cli():
    code, stdout, _ = _capture(["board", str(FIXTURE)])
    assert code == 0
    data = json.loads(stdout)
    assert data["view"] == "board"
    assert "complexity" in data

    code, stdout, _ = _capture(["hotspots", str(FIXTURE)])
    assert code == 0
    data = json.loads(stdout)
    assert data["view"] == "hotspots"
    assert "hotspots" in data


def test_snapshot_symbol_from_file(tmp_path: Path):
    snap = tmp_path / "snap.json"
    code, _, _ = _capture(["snapshot", str(FIXTURE), "-o", str(snap)])
    assert code == 0
    assert snap.exists()

    report = json.loads(snap.read_text(encoding="utf-8"))
    qname = None
    for mod in report["modules"]:
        for fn in mod.get("functions") or []:
            qname = fn["qualified_name"]
            break
        if qname:
            break
    assert qname

    code, stdout, _ = _capture(["symbol", "-f", str(snap), qname])
    assert code == 0
    data = json.loads(stdout)
    assert data["view"] == "symbol"
    assert data["symbol"]["qualified_name"] == qname

    code, _, err = _capture(["symbol", "-f", str(snap), "does.not.exist"])
    assert code == 2
    assert "not found" in err


def test_diff_json_pass(tmp_path: Path):
    report = analyze_path(FIXTURE).to_dict()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    text = json.dumps(report, indent=2)
    before.write_text(text, encoding="utf-8")
    after.write_text(text, encoding="utf-8")
    code, stdout, _ = _capture(["diff", "--json", str(before), str(after)])
    assert code == 0
    data = json.loads(stdout)
    assert data["view"] == "diff"
    assert data["pass"] is True


def test_hotspots_paths_filter():
    code, stdout, _ = _capture(["hotspots", str(FIXTURE), "--paths", "no/such/file.py"])
    assert code == 0
    data = json.loads(stdout)
    assert data["hotspots"] == []
    assert "filter" in data


def test_tests_findings_default():
    fake = Path(__file__).parent / "fixtures" / "fake_tests"
    code, stdout, _ = _capture(["tests", str(fake)])
    assert code == 0
    data = json.loads(stdout)
    assert data["view"] == "tests_findings"
    assert data["n_findings"] >= 1


def test_tests_full_flag():
    fake = Path(__file__).parent / "fixtures" / "fake_tests"
    code, stdout, _ = _capture(["tests", "--full", str(fake)])
    assert code == 0
    data = json.loads(stdout)
    assert data.get("mode") == "tests"
    assert "modules" in data


def test_analyze_cli_emits_full_report():
    code, stdout, _ = _capture(["analyze", str(FIXTURE)])
    assert code == 0
    data = json.loads(stdout)
    assert data["tool"] == "py-code-metrics"
    assert "modules" in data
