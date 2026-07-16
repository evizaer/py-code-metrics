"""Unit tests for compare gate logic."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from py_code_metrics.compare import compare, count_dou_on_paths, infer_changed_paths
from py_code_metrics.model import MetricsReport


def _minimal_report(**complexity_overrides: Any) -> dict[str, Any]:
    complexity: dict[str, Any] = {
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
        "version": 2,
        "overall": {
            "complexity": complexity,
            "etspa": {
                "sum_S": 10.0,
                "frac_S_le_0": 0.1,
                "frac_fan_in_le_1": 0.2,
                "helpers_cores": {"sum_S": 8.0, "frac_fan_in_le_1": 0.1},
            },
            "dou": {"n_dou_sites": 0, "n_dou_callables": 0},
            "hotspots": [{"qualified_name": "a.fn", "v_poly": 20}],
        },
        "modules": [
            {
                "path": "a.py",
                "functions": [
                    {
                        "qualified_name": "a.fn",
                        "name": "fn",
                        "kind": "function",
                        "lineno": 1,
                        "v_poly": 20,
                        "unpaid": True,
                        "reduction_like": False,
                        "n_dou_sites": 0,
                    }
                ],
                "classes": [],
            },
            {
                "path": "legacy.py",
                "functions": [
                    {
                        "qualified_name": "legacy.bag",
                        "name": "bag",
                        "kind": "function",
                        "lineno": 1,
                        "v_poly": 1,
                        "unpaid": True,
                        "n_dou_sites": 3,
                    }
                ],
                "classes": [],
            },
        ],
    }


def test_compare_pass_identical():
    report = _minimal_report()
    code, lines, diff = compare(report, report)
    assert code == 0
    assert diff["pass"] is True
    assert diff["view"] == "diff"
    assert diff["deltas"]["n_dou_sites_on_delta"] == [0, 0]
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


def test_compare_corpus_dou_rise_without_delta_path_pass():
    """Legacy DOU on an untouched module must not fail the gate."""
    before = _minimal_report()
    before["overall"]["dou"] = {"n_dou_sites": 3, "n_dou_callables": 1}
    after = deepcopy(before)
    # Touch only a.py complexity; legacy.py DOU unchanged; corpus stays 3.
    after["modules"][0]["functions"][0]["cognitive"] = 5
    after["overall"]["dou"] = {"n_dou_sites": 3, "n_dou_callables": 1}
    code, _lines, diff = compare(before, after)
    assert code == 0
    assert diff["pass"] is True
    assert "legacy.py" not in diff["dou_delta_paths"]
    assert diff["deltas"]["n_dou_sites_on_delta"][1] == diff["deltas"]["n_dou_sites_on_delta"][0]


def test_compare_dou_rise_on_delta_path_fails():
    before = _minimal_report()
    before["overall"]["dou"] = {"n_dou_sites": 3, "n_dou_callables": 1}
    after = deepcopy(before)
    after["modules"][0]["functions"][0]["n_dou_sites"] = 2
    after["overall"]["dou"] = {"n_dou_sites": 5, "n_dou_callables": 2}
    code, lines, diff = compare(before, after)
    assert code == 1
    assert diff["pass"] is False
    assert any("n_dou_sites_on_delta" in f for f in diff["failures"])
    assert diff["deltas"]["n_dou_sites_on_delta"] == [0, 2]
    assert "a.py" in diff["dou_delta_paths"]
    assert any("n_dou_sites_on_delta" in line for line in lines)


def test_compare_explicit_delta_paths_scopes_dou_gate():
    before = _minimal_report()
    before["overall"]["dou"] = {"n_dou_sites": 3, "n_dou_callables": 1}
    after = deepcopy(before)
    # Raise DOU on legacy.py only; scope gate to a.py → pass.
    after["modules"][1]["functions"][0]["n_dou_sites"] = 5
    after["overall"]["dou"] = {"n_dou_sites": 5, "n_dou_callables": 1}
    code, _lines, diff = compare(before, after, delta_paths={"a.py"})
    assert code == 0
    assert diff["dou_delta_paths"] == ["a.py"]
    assert diff["deltas"]["n_dou_sites_on_delta"] == [0, 0]
    assert diff["deltas"]["n_dou_sites"] == [3, 5]


def test_count_dou_on_paths_and_infer():
    before = MetricsReport.from_dict(_minimal_report())
    after_d = _minimal_report()
    after_d["modules"][0]["functions"][0]["n_dou_sites"] = 1
    after = MetricsReport.from_dict(after_d)
    assert count_dou_on_paths(before, {"legacy.py"}) == 3
    assert count_dou_on_paths(after, {"a.py"}) == 1
    assert infer_changed_paths(before, after) == ["a.py"]
