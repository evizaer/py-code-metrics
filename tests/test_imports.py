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
