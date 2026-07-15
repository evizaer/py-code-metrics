"""Compact agent-facing views over metrics reports."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

from py_code_metrics.model import (
    CallableMetrics,
    ClassMetrics,
    DouHotspotEntry,
    HotspotEntry,
    MetricsReport,
    TestCaseMetrics,
    TestMetricsReport,
    TestModuleReport,
)

_NEIGHBORS_NOTE = "callers/callees not in snapshot; use fan_in_* fields."


@dataclass
class BoardView:
    version: int
    view: str = "board"
    complexity: dict[str, Any] = field(default_factory=dict)
    etspa: dict[str, Any] = field(default_factory=dict)
    expression: dict[str, Any] = field(default_factory=dict)
    dou: dict[str, Any] = field(default_factory=dict)
    roles: dict[str, int] = field(default_factory=dict)
    imports: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HotspotsView:
    version: int
    view: str = "hotspots"
    n_unpaid_hotspots: int = 0
    hotspots: list[dict[str, Any]] = field(default_factory=list)
    filter: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": self.version,
            "view": self.view,
            "n_unpaid_hotspots": self.n_unpaid_hotspots,
            "hotspots": list(self.hotspots),
        }
        if self.filter is not None:
            out["filter"] = self.filter
        return out


@dataclass
class DouView:
    version: int
    view: str = "dou"
    n_dou_sites: int = 0
    n_dou_callables: int = 0
    dou_hotspots: list[dict[str, Any]] = field(default_factory=list)
    filter: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": self.version,
            "view": self.view,
            "n_dou_sites": self.n_dou_sites,
            "n_dou_callables": self.n_dou_callables,
            "dou_hotspots": list(self.dou_hotspots),
        }
        if self.filter is not None:
            out["filter"] = self.filter
        return out


@dataclass
class SymbolView:
    version: int
    kind: str
    path: str | None
    symbol: dict[str, Any]
    view: str = "symbol"
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)
    neighbors_note: str = _NEIGHBORS_NOTE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestFindingRow:
    qualified_name: str | None
    oracle_tier: str | None
    smell_codes: list[str]
    severity: str | None
    path: str | None
    lineno: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FindingsView:
    version: int
    view: str = "tests_findings"
    n_findings: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    overall: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iter_callables(report: MetricsReport) -> Iterator[tuple[str | None, CallableMetrics]]:
    """Yield ``(module_path, callable)`` for functions and methods."""
    for mod in report.modules:
        for fn in mod.functions:
            yield mod.path, fn
        for cls in mod.classes:
            for meth in cls.methods:
                yield mod.path, meth


def iter_classes(report: MetricsReport) -> Iterator[tuple[str | None, ClassMetrics]]:
    for mod in report.modules:
        for cls in mod.classes:
            yield mod.path, cls


def board_view(report: MetricsReport) -> BoardView:
    overall = report.overall
    return BoardView(
        version=report.version,
        complexity=overall.complexity.to_dict(),
        etspa={"helpers_cores": overall.etspa.helpers_cores.to_dict()},
        expression={"leaves": overall.expression.leaves.to_dict()},
        dou=overall.dou.to_dict(),
        roles=overall.roles.to_dict(),
        imports={"cycle_count": overall.imports.cycle_count},
    )


def hotspots_view(
    report: MetricsReport,
    *,
    limit: int | None = None,
    path_filter: set[str] | None = None,
) -> HotspotsView:
    hotspots = list(report.overall.hotspots)
    paths = callable_paths(report)
    if path_filter:
        normalized = {_norm_path(p) for p in path_filter}
        hotspots = [
            h for h in hotspots if _path_in_filter(paths.get(h.qualified_name, ""), normalized)
        ]
    enriched = [_with_path(h, paths) for h in hotspots]
    if limit is not None:
        enriched = enriched[:limit]
    view = HotspotsView(
        version=report.version,
        n_unpaid_hotspots=report.overall.complexity.n_unpaid_hotspots,
        hotspots=[h.to_dict() for h in enriched],
    )
    if path_filter is not None:
        view.filter = {
            "paths": sorted(path_filter),
            "note": (
                "Hotspot list filtered to listed paths; "
                "n_unpaid_hotspots remains the corpus-level count."
            ),
        }
    return view


def dou_view(
    report: MetricsReport,
    *,
    limit: int | None = None,
    path_filter: set[str] | None = None,
) -> DouView:
    entries = list(report.overall.dou_hotspots)
    paths = callable_paths(report)
    if path_filter:
        normalized = {_norm_path(p) for p in path_filter}
        entries = [
            e
            for e in entries
            if _path_in_filter(paths.get(e.qualified_name, e.path or ""), normalized)
        ]
    enriched = [_with_dou_path(e, paths) for e in entries]
    if limit is not None:
        enriched = enriched[:limit]
    view = DouView(
        version=report.version,
        n_dou_sites=report.overall.dou.n_dou_sites,
        n_dou_callables=report.overall.dou.n_dou_callables,
        dou_hotspots=[e.to_dict() for e in enriched],
    )
    if path_filter is not None:
        view.filter = {
            "paths": sorted(path_filter),
            "note": (
                "DOU hotspot list filtered to listed paths; "
                "n_dou_sites / n_dou_callables remain corpus-level counts."
            ),
        }
    return view


def symbol_view(report: MetricsReport, qname: str) -> SymbolView | None:
    found = find_symbol(report, qname)
    if found is None:
        return None
    kind, payload, path = found
    return SymbolView(
        version=report.version,
        kind=kind,
        path=path,
        symbol=payload.to_dict(),
    )


def findings_view(
    report: TestMetricsReport,
    *,
    limit: int | None = None,
) -> FindingsView:
    findings: list[dict[str, Any]] = []
    for mod in report.modules:
        for t in mod.tests:
            row = _finding_row(mod, t)
            if row is not None:
                findings.append(row.to_dict())
    overall = report.overall
    for survivor in overall.survivors:
        findings.append(
            {
                "kind": "mutation_survivor",
                "path": survivor.file,
                "lineno": survivor.line,
                "operator": survivor.operator,
                "id": survivor.id,
                "overlap_flags": list(survivor.overlap_flags),
                "severity": "low",
            }
        )
    for item in overall.uncovered_state_fields:
        findings.append(
            {
                "kind": "unchecked_state_field",
                "class": item.class_,
                "field": item.field,
                "severity": "low",
            }
        )
    if limit is not None:
        findings = findings[:limit]
    return FindingsView(
        version=report.version,
        n_findings=len(findings),
        findings=findings,
        overall={
            "test_count": overall.test_count,
            "frac_oracle_none": overall.frac_oracle_none,
            "frac_oracle_weak": overall.frac_oracle_weak,
            "frac_oracle_strong": overall.frac_oracle_strong,
            "high_severity_count": overall.high_severity_count,
            "weak_oracle_covered_line_count": overall.weak_oracle_covered_line_count,
            "unchecked_covered_callable_count": overall.unchecked_covered_callable_count,
            "mutation_score": overall.mutation_score,
            "survivor_count": overall.survivor_count,
            "mean_state_field_coverage": overall.mean_state_field_coverage,
            "uncovered_state_field_count": overall.uncovered_state_field_count,
        },
    )


def find_symbol(
    report: MetricsReport, qname: str
) -> tuple[str, CallableMetrics | ClassMetrics, str | None] | None:
    for path, fn in iter_callables(report):
        if fn.qualified_name == qname:
            return "callable", fn, path
    for path, cls in iter_classes(report):
        if cls.qualified_name == qname:
            return "class", cls, path
    return None


def callable_paths(report: MetricsReport) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path, fn in iter_callables(report):
        if path is not None:
            mapping[fn.qualified_name] = path
    return mapping


def _finding_row(mod: TestModuleReport, test: TestCaseMetrics) -> TestFindingRow | None:
    smells = test.smell_codes
    tier = test.oracle_tier
    if not smells and tier not in ("none", "weak"):
        return None
    return TestFindingRow(
        qualified_name=test.qualified_name or test.name,
        oracle_tier=tier,
        smell_codes=list(smells),
        severity=test.severity,
        path=mod.path or test.file,
        lineno=test.lineno,
    )


def _with_path(hotspot: HotspotEntry, paths: dict[str, str]) -> HotspotEntry:
    if hotspot.path is None and hotspot.qualified_name in paths:
        return HotspotEntry(
            qualified_name=hotspot.qualified_name,
            v_poly=hotspot.v_poly,
            nesting=hotspot.nesting,
            cognitive=hotspot.cognitive,
            fan_in_ext=hotspot.fan_in_ext,
            S=hotspot.S,
            role=hotspot.role,
            unpaid=hotspot.unpaid,
            reduction_like=hotspot.reduction_like,
            dispatch_exempt=hotspot.dispatch_exempt,
            path=paths[hotspot.qualified_name],
        )
    return hotspot


def _with_dou_path(entry: DouHotspotEntry, paths: dict[str, str]) -> DouHotspotEntry:
    if entry.path is None and entry.qualified_name in paths:
        return DouHotspotEntry(
            qualified_name=entry.qualified_name,
            n_dou_sites=entry.n_dou_sites,
            annotation=entry.annotation,
            impact=entry.impact,
            path=paths[entry.qualified_name],
        )
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
