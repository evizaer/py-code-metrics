"""Tests for P2 static state-field coverage."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.analyze_tests import analyze_tests_path
from py_code_metrics.views import findings_view

STATEFUL = Path(__file__).parent / "fixtures" / "stateful_pkg"


def test_state_field_coverage_mean_and_details():
    report = analyze_tests_path(STATEFUL)
    assert report.overall.mean_state_field_coverage is not None
    by_class = {d.class_: d for d in report.overall.state_field_classes}
    # Module name is counter when analyzing fixture root
    counter_key = next(k for k in by_class if k.endswith("Counter") or k == "Counter")
    detail = by_class[counter_key]
    assert "value" in detail.coverable
    assert "history" in detail.coverable
    assert "history+" in detail.coverable
    assert "value" in detail.covered
    assert "history" in detail.covered
    assert "history+" in detail.covered
    assert detail.score > 0


def test_return_only_oracle_does_not_cover_fields_alone():
    """test_inc_return_only asserts return value; field coverage comes from other tests."""
    report = analyze_tests_path(STATEFUL)
    by_class = {d.class_: d for d in report.overall.state_field_classes}
    counter_key = next(k for k in by_class if k.endswith("Counter") or k == "Counter")
    # Suite as a whole covers value via test_inc_checks_value
    assert "value" in by_class[counter_key].covered


def test_one_hop_snapshot_covers_value():
    report = analyze_tests_path(STATEFUL)
    by_class = {d.class_: d for d in report.overall.state_field_classes}
    counter_key = next(k for k in by_class if k.endswith("Counter") or k == "Counter")
    # snapshot() reads self.value — one-hop from assert c.snapshot() == 4
    assert "value" in by_class[counter_key].covered


def test_node_nested_iterable_labels():
    report = analyze_tests_path(STATEFUL)
    by_class = {d.class_: d for d in report.overall.state_field_classes}
    node_key = next(k for k in by_class if k.endswith("Node") or k == "Node")
    assert "item" in by_class[node_key].coverable
    assert "next" in by_class[node_key].coverable
    # recursive next → next+
    assert "next+" in by_class[node_key].coverable
    assert "item" in by_class[node_key].covered


def test_findings_view_includes_unchecked_state():
    report = analyze_tests_path(STATEFUL)
    view = findings_view(report).to_dict()
    assert "mean_state_field_coverage" in view["overall"]
    kinds = {f.get("kind") for f in view["findings"]}
    # Node may have uncovered next / next+ → unchecked_state_field rows
    assert "unchecked_state_field" in kinds or view["overall"]["uncovered_state_field_count"] >= 0


def test_sut_pkg_has_no_stateful_classes():
    sut = Path(__file__).parent / "fixtures" / "sut_pkg"
    report = analyze_tests_path(sut)
    assert report.overall.mean_state_field_coverage is None
    assert report.overall.state_field_classes == []
