#!/usr/bin/env python3
"""Measure agent-facing CLI payload sizes for workflow success tracking.

Prints single-payload and workflow totals for ``src/py_code_metrics`` (and
``--tests .``), preferring real subcommand stdout when available.

Usage:
  uv run python scripts/measure_agent_payloads.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "py_code_metrics"


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _uv(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["uv", "run", *args], check=check)


def _size(text: str) -> tuple[int, int]:
    raw = text.encode()
    lines = raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1 if raw else 0)
    return len(raw), lines


def _try_cli(*args: str) -> str | None:
    proc = _uv("py-code-metrics", *args, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def main() -> int:
    full = _uv("py-code-metrics", str(PKG)).stdout
    full_b, full_l = _size(full)
    data = json.loads(full)

    tests_full = _uv("py-code-metrics", "--tests", str(ROOT)).stdout
    tests_b, tests_l = _size(tests_full)
    tests_data = json.loads(tests_full)

    tmp = Path("/tmp")
    before_path = tmp / "pcm-measure-before.json"
    after_path = tmp / "pcm-measure-after.json"
    before_path.write_text(full, encoding="utf-8")
    after_path.write_text(full, encoding="utf-8")

    # Prefer real subcommands; fall back to in-process views / script.
    from py_code_metrics.model import MetricsReport, TestMetricsReport
    from py_code_metrics.views import (
        board_view,
        findings_view,
        hotspots_view,
        symbol_view,
    )

    report = MetricsReport.from_dict(data)
    tests_report = TestMetricsReport.from_dict(tests_data)

    board_out = _try_cli("board", "-f", str(before_path))
    if board_out is None:
        board_out = json.dumps(board_view(report).to_dict(), indent=2) + "\n"
        board_src = "simulated"
    else:
        board_src = "cli"

    hot_out = _try_cli("hotspots", "-f", str(before_path))
    if hot_out is None:
        hot_out = json.dumps(hotspots_view(report).to_dict(), indent=2) + "\n"
        hot_src = "simulated"
    else:
        hot_src = "cli"

    hs = (data.get("overall") or {}).get("hotspots") or []
    qname = hs[0]["qualified_name"] if hs else None
    sym_out = None
    sym_src = "n/a"
    if qname:
        sym_out = _try_cli("symbol", "-f", str(before_path), qname)
        if sym_out is None:
            view = symbol_view(report, qname)
            sym_out = json.dumps(view.to_dict(), indent=2) + "\n" if view else ""
            sym_src = "simulated"
        else:
            sym_src = "cli"

    diff_out = _try_cli("diff", "--json", str(before_path), str(after_path))
    if diff_out is None:
        from py_code_metrics.compare import compare

        _, _, diff_dict = compare(data, data)
        diff_out = json.dumps(diff_dict, indent=2) + "\n"
        diff_src = "simulated"
    else:
        diff_src = "cli"

    tests_findings_out = _try_cli("tests", str(ROOT))
    if tests_findings_out is None:
        tests_findings_out = json.dumps(findings_view(tests_report).to_dict(), indent=2) + "\n"
        tests_src = "simulated"
    else:
        # If CLI still emits full tree (legacy only), detect and simulate findings.
        parsed = json.loads(tests_findings_out)
        if parsed.get("view") != "tests_findings":
            tests_findings_out = json.dumps(findings_view(tests_report).to_dict(), indent=2) + "\n"
            tests_src = "simulated"
        else:
            tests_src = "cli"

    overall = data.get("overall") or {}
    overall_only = {
        "overall": {
            "complexity": overall.get("complexity"),
            "etspa": overall.get("etspa"),
            "expression": overall.get("expression"),
            "hotspots": overall.get("hotspots"),
            "roles": overall.get("roles"),
            "imports": overall.get("imports"),
        }
    }
    overall_text = json.dumps(overall_only, indent=2) + "\n"

    rows: list[tuple[str, int, int, str]] = [
        ("full_structural", full_b, full_l, "cli"),
        ("overall_only_skim", *_size(overall_text), "extract"),
        ("board", *_size(board_out), board_src),
        ("hotspots", *_size(hot_out), hot_src),
        ("symbol", *_size(sym_out or ""), sym_src),
        ("diff_json", *_size(diff_out), diff_src),
        ("full_tests", tests_b, tests_l, "cli"),
        ("tests_findings", *_size(tests_findings_out), tests_src),
    ]

    print(f"{'payload':<22} {'bytes':>8} {'lines':>6}  source")
    for name, nbytes, nlines, src in rows:
        print(f"{name:<22} {nbytes:8d} {nlines:6d}  {src}")

    by_name = {r[0]: r[1] for r in rows}
    w1_naive = (
        by_name["full_structural"] * 2
        + _size(
            _uv(
                "python",
                "scripts/compare_self_metrics.py",
                str(before_path),
                str(after_path),
            ).stdout
        )[0]
    )
    w1_optimistic = by_name["overall_only_skim"] * 2 + 765  # approx text diff
    w1_pass = by_name["diff_json"]
    w1_fail = by_name["diff_json"] + by_name["hotspots"] + by_name["symbol"]
    w2 = by_name["hotspots"] + by_name["symbol"]
    w3 = by_name["tests_findings"]

    print()
    print("workflow interrogated bytes")
    print(f"  W1_naive_2x_full+diff_text   {w1_naive}")
    print(f"  W1_optimistic_2x_overall     {w1_optimistic}")
    print(f"  W1_pass_diff_json            {w1_pass}")
    print(f"  W1_fail_diff+hotspots+symbol {w1_fail}")
    print(f"  W2_hotspots+symbol           {w2}")
    print(f"  W3_tests_findings            {w3}")
    n_hot = (overall.get("complexity") or {}).get("n_unpaid_hotspots")
    print(f"  files_analyzed               {(data.get('input') or {}).get('files_analyzed')}")
    print(f"  n_unpaid_hotspots            {n_hot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
