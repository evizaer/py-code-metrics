"""Tests for import SCC detection."""

from __future__ import annotations

from py_code_metrics.metrics.imports import build_import_graph, tarjan_scc


def test_tarjan_finds_cycle():
    edges = {
        "a": {"b"},
        "b": {"c"},
        "c": {"a"},
        "d": set(),
    }
    sccs = tarjan_scc(edges)
    cyclic = [s for s in sccs if len(s) > 1]
    assert len(cyclic) == 1
    assert set(cyclic[0]) == {"a", "b", "c"}


def test_build_import_graph_cycle():
    modules = {"pkg.a", "pkg.b", "pkg.c"}
    imports = {
        "pkg.a": ["pkg.b"],
        "pkg.b": ["pkg.c"],
        "pkg.c": ["pkg.a"],
    }
    g = build_import_graph(modules, imports)
    assert len(g.cycles) == 1
    assert set(g.cycles[0]) == modules


def test_corpus_module_strips_package_prefix():
    """Absolute imports of in-package modules must not collapse onto __init__."""
    from py_code_metrics.metrics.imports import _corpus_module

    names = {"py_code_metrics", "model", "metrics.etspa", "analyze"}
    assert _corpus_module("py_code_metrics.model", names) == "model"
    assert _corpus_module("py_code_metrics.metrics.etspa", names) == "metrics.etspa"
    assert _corpus_module("py_code_metrics", names) == "py_code_metrics"
    assert _corpus_module("model", names) == "model"
    assert _corpus_module("outside.pkg", names) is None


def test_ca_ce_after_prefix_strip():
    modules = {"py_code_metrics", "model", "analyze"}
    imports = {
        "analyze": ["py_code_metrics.model"],
        "model": [],
        "py_code_metrics": [],
    }
    g = build_import_graph(modules, imports)
    assert g.efferent("analyze") == 1
    assert g.afferent("model") == 1
    assert g.afferent("py_code_metrics") == 0

