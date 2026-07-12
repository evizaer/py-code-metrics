"""Orchestration for static test-quality (oracle / smell) analysis."""

from __future__ import annotations

from pathlib import Path

from py_code_metrics.discover import discover_tests
from py_code_metrics.metrics.test_oracles import extract_test_functions
from py_code_metrics.metrics.test_smells import derive_smells, summarize_oracles
from py_code_metrics.model import (
    TestCaseMetrics,
    TestMetricsReport,
    TestModuleReport,
    TestModuleRollup,
    TestOverallReport,
)
from py_code_metrics.parse import parse_files


def analyze_tests_path(root: Path) -> TestMetricsReport:
    """Discover test modules and emit a static oracle/smell report."""
    root = root.resolve()
    paths = discover_tests(root)
    parsed, skipped = parse_files(paths)
    modules: list[TestModuleReport] = []
    for pf in parsed:
        try:
            rel = str(pf.path.resolve().relative_to(root))
        except ValueError:
            rel = str(pf.path)
        mod_name = _module_name(root, pf.path)
        tests = [_to_metrics(rel, info) for info in extract_test_functions(pf.tree)]
        modules.append(
            TestModuleReport(
                path=rel,
                name=mod_name,
                metrics=_module_rollup(tests),
                tests=tests,
            )
        )
    modules.sort(key=lambda m: m.path)
    return TestMetricsReport(
        input={
            "root": str(root),
            "files_analyzed": len(parsed),
            "files_skipped": [{"path": str(s.path), "reason": s.reason} for s in skipped],
        },
        overall=_overall(modules),
        modules=modules,
    )


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
    # Default for free functions named test_*
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
