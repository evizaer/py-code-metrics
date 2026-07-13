"""Unit tests for compare gate logic."""

from __future__ import annotations

from copy import deepcopy

from py_code_metrics.compare import compare


def _minimal_report(**complexity_overrides):
    complexity = {
        "max_v_poly": 10,
        "max_nesting": 2,
        "mean_cyclomatic": 1.0,
        "mean_cognitive": 1.0,
        "n_v_poly_gt_15": 0,
        "n_nesting_gt_3": 0,
        "n_unpaid_v_poly_gt_15": 0,
        "n_unpaid_nesting_gt_3": 0,
        "n_unpaid_hotspots": 1,
    }
    complexity.update(complexity_overrides)
    return {
        "version": 1,
        "overall": {
            "complexity": complexity,
            "etspa": {
                "sum_S": 10.0,
                "frac_S_le_0": 0.1,
                "frac_fan_in_le_1": 0.2,
                "helpers_cores": {"sum_S": 8.0, "frac_fan_in_le_1": 0.1},
            },
            "hotspots": [{"qualified_name": "a.fn", "v_poly": 20}],
        },
        "modules": [
            {
                "path": "a.py",
                "functions": [
                    {
                        "qualified_name": "a.fn",
                        "v_poly": 20,
                        "unpaid": True,
                        "reduction_like": False,
                    }
                ],
                "classes": [],
            }
        ],
    }


def test_compare_pass_identical():
    report = _minimal_report()
    code, lines, diff = compare(report, report)
    assert code == 0
    assert diff["pass"] is True
    assert diff["view"] == "diff"
    assert any("PASS" in line for line in lines)


def test_compare_fail_hotspots_rose():
    before = _minimal_report(n_unpaid_hotspots=1)
    after = deepcopy(before)
    after["overall"]["complexity"]["n_unpaid_hotspots"] = 2
    after["overall"]["hotspots"].append({"qualified_name": "b.fn", "v_poly": 20})
    code, _lines, diff = compare(before, after)
    assert code == 1
    assert diff["pass"] is False
    assert diff["hotspots_added"] == ["b.fn"]
    assert any("n_unpaid_hotspots" in f for f in diff["failures"])


def test_compare_max_v_poly_paid_not_fail():
    before = _minimal_report(max_v_poly=10)
    after = deepcopy(before)
    after["overall"]["complexity"]["max_v_poly"] = 30
    after["modules"][0]["functions"][0]["v_poly"] = 30
    after["modules"][0]["functions"][0]["unpaid"] = False
    code, _lines, diff = compare(before, after)
    assert code == 0
    assert diff["pass"] is True
