"""Orchestration for static test-quality (oracle / smell) analysis."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.discover import discover_python_files, discover_tests
from py_code_metrics.metrics.test_coverage import apply_coverage, load_coverage_json
from py_code_metrics.metrics.test_delta import changed_python_paths
from py_code_metrics.metrics.test_oracles import extract_test_functions
from py_code_metrics.metrics.test_smells import derive_smells, summarize_oracles
from py_code_metrics.metrics.test_sut import resolve_production_calls
from py_code_metrics.model import (
    TestCaseMetrics,
    TestMetricsReport,
    TestModuleReport,
    TestModuleRollup,
    TestOverallReport,
)
from py_code_metrics.parse import parse_files
from py_code_metrics.resolve import ModuleInfo, SymbolIndex, build_symbol_index


def analyze_tests_path(
    root: Path,
    *,
    coverage_path: Path | None = None,
    delta: bool = False,
) -> TestMetricsReport:
    """Discover test modules and emit oracle/smell (+ optional coverage) report."""
    root = root.resolve()
    all_parsed, skipped = parse_files(discover_python_files(root))
    index = build_symbol_index(all_parsed, root)
    test_paths = {p.resolve() for p in discover_tests(root)}
    modules = [
        _module_report(root, pf.path, pf.tree, index)
        for pf in all_parsed
        if pf.path.resolve() in test_paths
    ]
    modules.sort(key=lambda m: m.path)

    meta: dict = {
        "root": str(root),
        "files_analyzed": len(modules),
        "files_skipped": [{"path": str(s.path), "reason": s.reason} for s in skipped],
    }
    report = TestMetricsReport(
        input=meta,
        overall=_overall(modules),
        modules=modules,
    )

    if coverage_path is not None:
        ingest = load_coverage_json(coverage_path)
        apply_coverage(report, index, ingest, root)
        meta["coverage_path"] = str(coverage_path.resolve())
        meta["coverage_has_contexts"] = ingest.has_contexts

    if delta:
        paths, note = changed_python_paths(root)
        meta["delta"] = True
        meta["files_in_delta"] = paths
        if note:
            meta["delta_note"] = note
        _apply_delta_filter(report, set(paths))

    return report


def _module_info_for_path(index: SymbolIndex, path: Path) -> ModuleInfo | None:
    resolved = path.resolve()
    for mi in index.modules.values():
        if mi.path.resolve() == resolved:
            return mi
    return None


def _module_report(root: Path, path: Path, tree, index: SymbolIndex) -> TestModuleReport:
    rel = _rel(root, path)
    mod_name = _module_name(root, path)
    mi = _module_info_for_path(index, path)
    tests: list[TestCaseMetrics] = []
    for info in extract_test_functions(tree):
        case = _to_metrics(rel, info)
        if mi is not None:
            case.calls_production = resolve_production_calls(index, mi, info)
        tests.append(case)
    return TestModuleReport(
        path=rel,
        name=mod_name,
        metrics=_module_rollup(tests),
        tests=tests,
    )


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def _module_name(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        rel = path
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _infer_framework(info) -> str:
    hints = info.framework_hints
    if "pytest" in hints and "unittest" not in hints:
        return "pytest"
    if "unittest" in hints and "pytest" not in hints:
        return "unittest"
    if info.class_name:
        return "unittest"
    if info.markers:
        return "pytest"
    return "pytest"


def _to_metrics(file_path: str, info) -> TestCaseMetrics:
    tier, kinds, count = summarize_oracles(info)
    smells, severity, exempt = derive_smells(info)
    return TestCaseMetrics(
        name=info.name,
        qualified_name=info.qualified_name,
        lineno=info.lineno,
        file=file_path,
        framework=_infer_framework(info),  # type: ignore[arg-type]
        assertion_count=count,
        oracle_tier=tier,  # type: ignore[arg-type]
        oracle_kinds=kinds,
        smell_codes=smells,
        severity=severity,  # type: ignore[arg-type]
        markers=list(info.markers),
        exempt=exempt,
    )


def _module_rollup(tests: list[TestCaseMetrics]) -> TestModuleRollup:
    n = len(tests)
    if n == 0:
        return TestModuleRollup()
    none = sum(1 for t in tests if t.oracle_tier == "none")
    weak = sum(1 for t in tests if t.oracle_tier == "weak")
    strong = sum(1 for t in tests if t.oracle_tier == "strong")
    return TestModuleRollup(
        test_count=n,
        frac_oracle_none=none / n,
        frac_oracle_weak=weak / n,
        frac_oracle_strong=strong / n,
        mean_assertion_density=sum(t.assertion_count for t in tests) / n,
        high_severity_count=sum(1 for t in tests if t.severity == "high"),
    )


def _overall(modules: list[TestModuleReport]) -> TestOverallReport:
    tests = [t for m in modules for t in m.tests]
    n = len(tests)
    overall = TestOverallReport(module_count=len(modules), test_count=n)
    if not n:
        return overall
    hist = {"none": 0, "weak": 0, "strong": 0}
    for t in tests:
        hist[t.oracle_tier] = hist.get(t.oracle_tier, 0) + 1
    high = [t for t in tests if t.severity == "high"]
    overall.frac_oracle_none = hist["none"] / n
    overall.frac_oracle_weak = hist["weak"] / n
    overall.frac_oracle_strong = hist["strong"] / n
    overall.mean_assertion_density = sum(t.assertion_count for t in tests) / n
    overall.high_severity_count = len(high)
    overall.oracle_histogram = hist
    overall.high_severity_findings = [
        {
            "file": t.file,
            "name": t.qualified_name,
            "lineno": t.lineno,
            "smell_codes": t.smell_codes,
            "oracle_tier": t.oracle_tier,
        }
        for t in high
    ]
    return overall


def _apply_delta_filter(report: TestMetricsReport, delta_paths: set[str]) -> None:
    """Keep modules / findings that touch changed paths (empty delta → no filter)."""
    if not delta_paths:
        return
    normalized = {p.replace("\\", "/") for p in delta_paths}
    saved_line = report.overall.coverage_line
    saved_branch = report.overall.coverage_branch
    saved_weak = report.overall.weak_oracle_covered_lines
    saved_unchecked = report.overall.unchecked_covered_callables

    report.modules = [m for m in report.modules if _path_in_delta(m.path, normalized)]
    report.overall = _overall(report.modules)
    report.overall.coverage_line = saved_line
    report.overall.coverage_branch = saved_branch
    report.overall.weak_oracle_covered_lines = [
        item for item in saved_weak if _path_in_delta(item["file"], normalized)
    ]
    report.overall.weak_oracle_covered_line_count = len(report.overall.weak_oracle_covered_lines)
    report.overall.unchecked_covered_callables = [
        q for q in saved_unchecked if _qname_in_delta(q, normalized)
    ]
    report.overall.unchecked_covered_callable_count = len(
        report.overall.unchecked_covered_callables
    )


def _path_in_delta(path: str, delta_paths: set[str]) -> bool:
    p = path.replace("\\", "/")
    if p in delta_paths:
        return True
    return any(p.endswith(d) or d.endswith(p) for d in delta_paths)


def _qname_in_delta(qname: str, delta_paths: set[str]) -> bool:
    parts = qname.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:i]) + ".py"
        if _path_in_delta(candidate, delta_paths):
            return True
    return False
