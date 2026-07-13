"""Unit tests for agent-facing views."""

from __future__ import annotations

from py_code_metrics.views import board_view, findings_view, hotspots_view, symbol_view


def _structural_report():
    return {
        "version": 1,
        "overall": {
            "complexity": {"n_unpaid_hotspots": 1, "max_v_poly": 20},
            "etspa": {"helpers_cores": {"sum_S": 5.0, "frac_fan_in_le_1": 0.2}},
            "expression": {"leaves": {"mean_car": 1.5}},
            "roles": {"core": 1, "leaf": 1, "helper": 0},
            "imports": {"cycle_count": 0},
            "hotspots": [
                {
                    "qualified_name": "pkg.mod.fn",
                    "v_poly": 20,
                    "nesting": 4,
                    "cognitive": 16,
                    "fan_in_ext": 1,
                    "S": -1.0,
                    "role": "helper",
                    "unpaid": True,
                    "reduction_like": False,
                    "dispatch_exempt": False,
                }
            ],
        },
        "modules": [
            {
                "path": "pkg/mod.py",
                "functions": [
                    {
                        "qualified_name": "pkg.mod.fn",
                        "name": "fn",
                        "v_poly": 20,
                        "fan_in_ext": 1,
                    }
                ],
                "classes": [],
            }
        ],
    }


def test_board_view_shape():
    view = board_view(_structural_report())
    assert view["view"] == "board"
    assert "helpers_cores" in view["etspa"]
    assert "leaves" in view["expression"]
    assert view["imports"]["cycle_count"] == 0
    assert "modules" not in view


def test_hotspots_view_and_filter():
    report = _structural_report()
    view = hotspots_view(report)
    assert view["n_unpaid_hotspots"] == 1
    assert view["hotspots"][0]["path"] == "pkg/mod.py"

    filtered = hotspots_view(report, path_filter={"other.py"})
    assert filtered["hotspots"] == []
    assert "filter" in filtered

    kept = hotspots_view(report, path_filter={"pkg/mod.py"})
    assert len(kept["hotspots"]) == 1


def test_symbol_view():
    view = symbol_view(_structural_report(), "pkg.mod.fn")
    assert view is not None
    assert view["view"] == "symbol"
    assert view["symbol"]["qualified_name"] == "pkg.mod.fn"
    assert view["callers"] == []
    assert "neighbors_note" in view
    assert symbol_view(_structural_report(), "missing") is None


def test_findings_view():
    report = {
        "version": 1,
        "overall": {
            "test_count": 2,
            "module_count": 1,
            "frac_oracle_none": 0.5,
            "frac_oracle_weak": 0.0,
            "frac_oracle_strong": 0.5,
            "high_severity_count": 1,
        },
        "modules": [
            {
                "path": "tests/test_x.py",
                "tests": [
                    {
                        "qualified_name": "test_bad",
                        "oracle_tier": "none",
                        "smell_codes": ["NO_ORACLE"],
                        "severity": "high",
                        "lineno": 3,
                    },
                    {
                        "qualified_name": "test_ok",
                        "oracle_tier": "strong",
                        "smell_codes": [],
                        "severity": "info",
                        "lineno": 10,
                    },
                ],
            }
        ],
    }
    view = findings_view(report)
    assert view["view"] == "tests_findings"
    assert view["n_findings"] == 1
    assert view["findings"][0]["qualified_name"] == "test_bad"
