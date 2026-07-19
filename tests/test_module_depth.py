"""Tests for module-native depth metrics (MDI, PIW, PTR, Ca/Ce)."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.analyze import analyze_path
from py_code_metrics.metrics.imports import build_import_graph
from py_code_metrics.metrics.module_depth import ALPHA, BETA, LOW_MDI_THRESHOLD
from py_code_metrics.views import board_view, module_board_view

FIXTURE = Path(__file__).parent / "fixtures" / "module_depth_pkg"


def _by_stem(report):
    return {Path(m.path).stem: m for m in report.modules}


def test_import_ca_ce():
    modules = {"a", "b", "c"}
    imports = {"a": ["b"], "b": ["c"], "c": []}
    g = build_import_graph(modules, imports)
    assert g.efferent("a") == 1
    assert g.afferent("b") == 1
    assert g.afferent("c") == 1
    assert g.afferent("a") == 0
    assert g.efferent("c") == 0


def test_module_depth_fixture_shapes():
    report = analyze_path(FIXTURE)
    by = _by_stem(report)

    deep = by["deep_core"].depth
    facade = by["facade"].depth
    wide = by["shallow_wide"].depth

    assert deep.n_public_exports == 2
    assert deep.mdi > facade.mdi
    assert deep.ptr == 0.0
    assert facade.ptr == 1.0

    assert wide.n_public_types == 3
    assert wide.piw > deep.piw
    assert wide.mdi < deep.mdi
    assert wide.role == "library"

    # PIW = N_exports + alpha * mean_params + beta * N_types
    mean_params = (wide.piw - wide.n_public_exports - BETA * wide.n_public_types) / ALPHA
    assert mean_params > 0

    assert facade.ce >= 1
    assert deep.ca >= 1

    overall = report.overall.module_depth
    assert overall.sum_piw > 0
    assert overall.low_mdi_threshold == LOW_MDI_THRESHOLD
    assert overall.n_low_mdi >= 1


def test_board_and_module_board_views():
    report = analyze_path(FIXTURE)
    board = board_view(report).to_dict()
    assert "module_depth" in board
    assert "sum_piw" in board["module_depth"]

    mb = module_board_view(report, limit=2).to_dict()
    assert mb["view"] == "module-board"
    assert len(mb["modules"]) == 2
    assert "mdi" in mb["modules"][0]
