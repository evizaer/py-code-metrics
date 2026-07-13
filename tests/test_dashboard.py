"""Unit tests for dashboard predicates (hotspots, dispatch, reduction-like)."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.analyze import analyze_path
from py_code_metrics.dashboard import is_hotspot, is_reduction_like, is_unpaid
from py_code_metrics.model import DEFAULT_THRESHOLDS, CallableMetrics

FIXTURE = Path(__file__).parent / "fixtures" / "dashboard_pkg"


def _cm(**kwargs) -> CallableMetrics:
    base = dict(
        name="f",
        qualified_name="m.f",
        kind="function",
        lineno=1,
        role="helper",
    )
    base.update(kwargs)
    return CallableMetrics(**base)  # type: ignore[arg-type]


def test_paid_high_complexity_is_not_hotspot():
    c = _cm(v_poly=15, cognitive=19, max_nesting=2, fan_in_ext=2, S=210.0)
    c.unpaid = is_unpaid(c)
    assert not c.unpaid
    assert not is_hotspot(c, DEFAULT_THRESHOLDS)


def test_unpaid_high_complexity_is_hotspot():
    c = _cm(v_poly=19, cognitive=33, max_nesting=3, fan_in_ext=1, S=-39.0, role="leaf")
    c.unpaid = is_unpaid(c)
    assert c.unpaid
    assert is_hotspot(c, DEFAULT_THRESHOLDS)


def test_dispatch_exempt_not_unpaid_or_hotspot():
    c = _cm(
        v_poly=5,
        cognitive=8,
        max_nesting=2,
        fan_in_ext=0,
        S=-20.0,
        dispatch_exempt=True,
    )
    c.unpaid = is_unpaid(c)
    assert not c.unpaid
    assert not is_hotspot(c, DEFAULT_THRESHOLDS)


def test_reduction_like_v_poly_alone_not_hotspot():
    c = _cm(
        v_poly=19,
        cyclomatic=19,
        cognitive=12,
        max_nesting=1,
        fan_in_ext=1,
        S=-40.0,
        role="leaf",
    )
    c.reduction_like = is_reduction_like(c)
    c.unpaid = is_unpaid(c)
    assert c.reduction_like
    assert c.unpaid
    # v_poly alone with reduction_like should not hotspot; nesting/cog still can.
    assert not is_hotspot(c, DEFAULT_THRESHOLDS)


def test_ltr_no_statements_threshold_long_flat_not_hotspot():
    """LTR: length is context; unpaid long/shallow bodies are not hotspots."""
    assert "statements" not in DEFAULT_THRESHOLDS.to_dict()
    c = _cm(
        v_poly=4,
        cyclomatic=4,
        cognitive=5,
        max_nesting=1,
        fan_in_ext=1,
        S=-80.0,
        statements=200,
        body_tokens=900,
        role="helper",
    )
    c.unpaid = is_unpaid(c)
    assert c.unpaid
    assert not is_hotspot(c, DEFAULT_THRESHOLDS)


def test_dashboard_fixture_e2e():
    report = analyze_path(FIXTURE)
    d = report.to_dict()
    overall = d["overall"]

    assert "hotspots" in overall
    assert "helpers_cores" in overall["etspa"]
    assert "leaves" in overall["expression"]
    assert "n_unpaid_hotspots" in overall["complexity"]

    by_qname = {}
    for mod in d["modules"]:
        for fn in mod["functions"]:
            by_qname[fn["qualified_name"]] = fn
        for cls in mod["classes"]:
            assert "dispatch_class" in cls["metrics"]
            for meth in cls["methods"]:
                by_qname[meth["qualified_name"]] = meth

    visitor = by_qname["visitors.Walk.visit_Name"]
    assert visitor["dispatch_exempt"] is True
    assert visitor["unpaid"] is False

    walk_cls = next(c for m in d["modules"] for c in m["classes"] if c["name"] == "Walk")
    assert walk_cls["metrics"]["dispatch_class"] is True
    assert walk_cls["metrics"]["lcom4_gate_exempt"] is True

    paid = by_qname["mod.shared_branchy"]
    assert paid["fan_in_ext"] >= 2
    assert paid["S"] > 0
    assert paid["unpaid"] is False
    hotspot_names = {h["qualified_name"] for h in overall["hotspots"]}
    assert paid["qualified_name"] not in hotspot_names

    unpaid_leaf = by_qname["mod.tangled_leaf"]
    assert unpaid_leaf["unpaid"] is True
    assert unpaid_leaf["qualified_name"] in hotspot_names
    assert "statements" in unpaid_leaf
    assert "statements" not in d["thresholds"]
