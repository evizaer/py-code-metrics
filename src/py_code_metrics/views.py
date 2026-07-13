"""Compact agent-facing views over metrics report dicts."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

_NEIGHBORS_NOTE = "callers/callees not in snapshot; use fan_in_* fields."


def iter_callables(report: dict[str, Any]) -> Iterator[tuple[str | None, dict[str, Any]]]:
    """Yield ``(module_path, callable_dict)`` for functions and methods."""
    for mod in report.get("modules") or []:
        path = mod.get("path")
        for fn in mod.get("functions") or []:
            yield path, fn
        for cls in mod.get("classes") or []:
            for meth in cls.get("methods") or []:
                yield path, meth


def iter_classes(report: dict[str, Any]) -> Iterator[tuple[str | None, dict[str, Any]]]:
    for mod in report.get("modules") or []:
        path = mod.get("path")
        for cls in mod.get("classes") or []:
            yield path, cls


def board_view(report: dict[str, Any]) -> dict[str, Any]:
    overall = report.get("overall", {})
    etspa = overall.get("etspa") or {}
    expression = overall.get("expression") or {}
    imports = overall.get("imports") or {}
    return {
        "version": report.get("version", 1),
        "view": "board",
        "complexity": overall.get("complexity") or {},
        "etspa": {"helpers_cores": etspa.get("helpers_cores") or {}},
        "expression": {"leaves": expression.get("leaves") or {}},
        "roles": overall.get("roles") or {},
        "imports": {"cycle_count": imports.get("cycle_count", 0)},
    }


def hotspots_view(
    report: dict[str, Any],
    *,
    limit: int | None = None,
    path_filter: set[str] | None = None,
) -> dict[str, Any]:
    overall = report.get("overall", {})
    complexity = overall.get("complexity") or {}
    hotspots = list(overall.get("hotspots") or [])
    paths = callable_paths(report)
    if path_filter:
        normalized = {_norm_path(p) for p in path_filter}
        hotspots = [
            h
            for h in hotspots
            if _path_in_filter(paths.get(h.get("qualified_name", ""), ""), normalized)
        ]
    enriched = [_with_path(h, paths) for h in hotspots]
    if limit is not None:
        enriched = enriched[:limit]
    out: dict[str, Any] = {
        "version": report.get("version", 1),
        "view": "hotspots",
        "n_unpaid_hotspots": complexity.get("n_unpaid_hotspots", len(hotspots)),
        "hotspots": enriched,
    }
    if path_filter is not None:
        out["filter"] = {
            "paths": sorted(path_filter),
            "note": (
                "Hotspot list filtered to listed paths; "
                "n_unpaid_hotspots remains the corpus-level count."
            ),
        }
    return out


def symbol_view(report: dict[str, Any], qname: str) -> dict[str, Any] | None:
    found = find_symbol(report, qname)
    if found is None:
        return None
    kind, payload, path = found
    return {
        "version": report.get("version", 1),
        "view": "symbol",
        "kind": kind,
        "path": path,
        "symbol": payload,
        "callers": [],
        "callees": [],
        "neighbors_note": _NEIGHBORS_NOTE,
    }


def findings_view(
    report: dict[str, Any],
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for mod in report.get("modules") or []:
        for t in mod.get("tests") or []:
            row = _finding_row(mod, t)
            if row is not None:
                findings.append(row)
    if limit is not None:
        findings = findings[:limit]
    overall = report.get("overall") or {}
    return {
        "version": report.get("version", 1),
        "view": "tests_findings",
        "n_findings": len(findings),
        "findings": findings,
        "overall": {
            "test_count": overall.get("test_count"),
            "frac_oracle_none": overall.get("frac_oracle_none"),
            "frac_oracle_weak": overall.get("frac_oracle_weak"),
            "frac_oracle_strong": overall.get("frac_oracle_strong"),
            "high_severity_count": overall.get("high_severity_count"),
            "weak_oracle_covered_line_count": overall.get("weak_oracle_covered_line_count"),
            "unchecked_covered_callable_count": overall.get("unchecked_covered_callable_count"),
        },
    }


def find_symbol(
    report: dict[str, Any], qname: str
) -> tuple[str, dict[str, Any], str | None] | None:
    for path, fn in iter_callables(report):
        if fn.get("qualified_name") == qname:
            return "callable", fn, path
    for path, cls in iter_classes(report):
        if cls.get("qualified_name") == qname:
            return "class", cls, path
    return None


def callable_paths(report: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path, fn in iter_callables(report):
        qn = fn.get("qualified_name")
        if qn and path is not None:
            mapping[qn] = path
    return mapping


def _finding_row(mod: dict[str, Any], test: dict[str, Any]) -> dict[str, Any] | None:
    smells = test.get("smell_codes") or []
    tier = test.get("oracle_tier")
    if not smells and tier not in ("none", "weak"):
        return None
    return {
        "qualified_name": test.get("qualified_name") or test.get("name"),
        "oracle_tier": tier,
        "smell_codes": smells,
        "severity": test.get("severity"),
        "path": mod.get("path") or test.get("file"),
        "lineno": test.get("lineno"),
    }


def _with_path(hotspot: dict[str, Any], paths: dict[str, str]) -> dict[str, Any]:
    entry = dict(hotspot)
    qn = hotspot.get("qualified_name", "")
    if qn in paths:
        entry.setdefault("path", paths[qn])
    return entry


def _norm_path(path: str) -> str:
    return path.replace("\\", "/")


def _path_in_filter(path: str, delta_paths: set[str]) -> bool:
    p = _norm_path(path)
    if not p:
        return False
    if p in delta_paths:
        return True
    return any(p.endswith("/" + d) or p.endswith(d) for d in delta_paths)
