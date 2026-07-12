"""Ingest coverage.py JSON and merge with oracle / SUT signals."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_code_metrics.discover import is_test_file
from py_code_metrics.model import TestCaseMetrics, TestMetricsReport
from py_code_metrics.resolve import CallableInfo, SymbolIndex


@dataclass
class CoverageIngest:
    coverage_line: float | None = None
    coverage_branch: float | None = None
    # Absolute or report-relative file path → executed line numbers
    executed_lines: dict[str, set[int]] = field(default_factory=dict)
    # file → line → context strings (pytest-cov style)
    contexts: dict[str, dict[int, list[str]]] = field(default_factory=dict)
    has_contexts: bool = False
    file_summaries: dict[str, dict[str, float | None]] = field(default_factory=dict)


def load_coverage_json(path: Path) -> CoverageIngest:
    """Parse a coverage.py JSON report (optionally with show_contexts)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    totals = raw.get("totals") or {}
    ingest = CoverageIngest(
        coverage_line=_pct(totals.get("percent_covered")),
        coverage_branch=_branch_pct(totals),
    )
    for file_key, meta in (raw.get("files") or {}).items():
        _ingest_file(ingest, file_key, meta)
    return ingest


def apply_coverage(
    report: TestMetricsReport,
    index: SymbolIndex,
    ingest: CoverageIngest,
    root: Path,
) -> None:
    """Attach floors, weak-oracle-covered lines, and unchecked callables."""
    report.overall.coverage_line = ingest.coverage_line
    report.overall.coverage_branch = ingest.coverage_branch
    _attach_module_floors(report, ingest, root)

    test_by_key = _index_tests(report)
    if ingest.has_contexts:
        weak_lines = _weak_oracle_covered_lines(ingest, test_by_key, root)
        report.overall.weak_oracle_covered_lines = weak_lines
        report.overall.weak_oracle_covered_line_count = len(weak_lines)

    unchecked = _unchecked_covered_callables(report, index, ingest, root)
    report.overall.unchecked_covered_callables = unchecked
    report.overall.unchecked_covered_callable_count = len(unchecked)
    _count_module_findings(report)


def parse_run_context(ctx: str) -> tuple[str, str] | None:
    """Map pytest-cov context to (file_hint, qualified_name); None if not run-phase."""
    if "|" not in ctx:
        return None
    test_id, phase = ctx.rsplit("|", 1)
    if phase != "run":
        return None
    parts = test_id.split("::")
    if len(parts) < 2:
        return None
    file_hint = parts[0]
    qname = ".".join(parts[1:])
    if "[" in qname:
        qname = qname.split("[", 1)[0]
    return file_hint, qname


def _ingest_file(ingest: CoverageIngest, file_key: str, meta: dict[str, Any]) -> None:
    summary = meta.get("summary") or {}
    ingest.file_summaries[file_key] = {
        "coverage_line": _pct(summary.get("percent_covered")),
        "coverage_branch": _branch_pct(summary),
    }
    ingest.executed_lines[file_key] = set(meta.get("executed_lines") or [])
    ctx_map = meta.get("contexts") or {}
    if not ctx_map:
        return
    ingest.has_contexts = True
    by_line: dict[int, list[str]] = {}
    for line_key, ctxs in ctx_map.items():
        line_no = _int_or_none(line_key)
        if line_no is not None:
            by_line[line_no] = list(ctxs)
    ingest.contexts[file_key] = by_line


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _branch_pct(summary: dict[str, Any]) -> float | None:
    covered = summary.get("covered_branches")
    total = summary.get("num_branches")
    if covered is None or total is None:
        return _pct(summary.get("percent_covered_display"))
    try:
        total_f = float(total)
    except (TypeError, ValueError):
        return None
    if total_f <= 0:
        return None
    return 100.0 * float(covered) / total_f


def _index_tests(report: TestMetricsReport) -> dict[tuple[str, str], TestCaseMetrics]:
    out: dict[tuple[str, str], TestCaseMetrics] = {}
    for mod in report.modules:
        for t in mod.tests:
            out[(t.file, t.qualified_name)] = t
            out[(Path(t.file).name, t.qualified_name)] = t
            out[(str(Path(t.file).as_posix()), t.qualified_name)] = t
    return out


def _lookup_test(
    test_by_key: dict[tuple[str, str], TestCaseMetrics],
    file_hint: str,
    qname: str,
) -> TestCaseMetrics | None:
    hint = file_hint.replace("\\", "/")
    for key in ((hint, qname), (Path(hint).name, qname), (str(Path(hint).as_posix()), qname)):
        hit = test_by_key.get(key)
        if hit is not None:
            return hit
    return _unique_qname_match(test_by_key, qname)


def _unique_qname_match(
    test_by_key: dict[tuple[str, str], TestCaseMetrics], qname: str
) -> TestCaseMetrics | None:
    uniq = list({id(t): t for (f, q), t in test_by_key.items() if q == qname}.values())
    return uniq[0] if len(uniq) == 1 else None


def _test_from_context(
    ctx: str, test_by_key: dict[tuple[str, str], TestCaseMetrics]
) -> TestCaseMetrics | None:
    parsed = parse_run_context(ctx)
    if parsed is None:
        return None
    test = _lookup_test(test_by_key, parsed[0], parsed[1])
    if test is None or test.exempt:
        return None
    return test


def _tiers_from_contexts(
    ctxs: list[str], test_by_key: dict[tuple[str, str], TestCaseMetrics]
) -> tuple[list[str], list[str]]:
    tiers: list[str] = []
    names: list[str] = []
    for ctx in ctxs:
        test = _test_from_context(ctx, test_by_key)
        if test is None:
            continue
        tiers.append(test.oracle_tier)
        names.append(test.qualified_name)
    return tiers, names


def _weak_line_finding(
    rel: str, line_no: int, tiers: list[str], test_names: list[str]
) -> dict[str, Any] | None:
    if not tiers:
        return None
    if any(t == "strong" for t in tiers):
        return None
    if not all(t in ("none", "weak") for t in tiers):
        return None
    best = "weak" if "weak" in tiers else "none"
    return {
        "file": rel,
        "line": line_no,
        "tests": sorted(set(test_names)),
        "best_oracle_tier": best,
    }


def _weak_oracle_covered_lines(
    ingest: CoverageIngest,
    test_by_key: dict[tuple[str, str], TestCaseMetrics],
    root: Path,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for file_key, by_line in ingest.contexts.items():
        rel = _rel_to_root(root, file_key)
        for line_no, ctxs in sorted(by_line.items()):
            tiers, names = _tiers_from_contexts(ctxs, test_by_key)
            hit = _weak_line_finding(rel, line_no, tiers, names)
            if hit is not None:
                findings.append(hit)
    return findings


def _strong_production_targets(report: TestMetricsReport) -> set[str]:
    strong: set[str] = set()
    for mod in report.modules:
        for t in mod.tests:
            if t.oracle_tier == "strong" and not t.exempt:
                strong.update(t.calls_production)
    return strong


def _body_covered(info: CallableInfo, executed: set[int]) -> bool:
    start = info.node.lineno
    end = getattr(info.node, "end_lineno", None) or start
    return any(start <= line <= end for line in executed)


def _is_unchecked_candidate(
    index: SymbolIndex,
    qname: str,
    info: CallableInfo,
    strong: set[str],
    path_index: dict[str, set[int]],
    root: Path,
) -> bool:
    mi = index.modules.get(info.module)
    if mi is None or is_test_file(Path(mi.path)):
        return False
    if qname in strong:
        return False
    executed = _executed_for_module(path_index, mi.path, root)
    if not executed:
        return False
    return _body_covered(info, executed)


def _unchecked_covered_callables(
    report: TestMetricsReport,
    index: SymbolIndex,
    ingest: CoverageIngest,
    root: Path,
) -> list[str]:
    strong = _strong_production_targets(report)
    path_index = _coverage_path_index(ingest, root)
    return [
        qname
        for qname, info in sorted(index.callables.items())
        if _is_unchecked_candidate(index, qname, info, strong, path_index, root)
    ]


def _coverage_path_index(ingest: CoverageIngest, root: Path) -> dict[str, set[int]]:
    """Normalize coverage file keys to resolved absolute paths and basenames."""
    out: dict[str, set[int]] = {}
    for key, lines in ingest.executed_lines.items():
        path = Path(key)
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        out[str(path)] = lines
        out[path.name] = lines
        with contextlib.suppress(ValueError):
            out[str(path.relative_to(root.resolve()))] = lines
    return out


def _executed_for_module(
    path_index: dict[str, set[int]], module_path: Path, root: Path
) -> set[int]:
    resolved = module_path.resolve()
    rel = (
        str(resolved.relative_to(root.resolve()))
        if resolved.is_relative_to(root.resolve())
        else None
    )
    for key in (str(resolved), resolved.name, rel):
        if key and key in path_index:
            return path_index[key]
    return set()


def _attach_module_floors(report: TestMetricsReport, ingest: CoverageIngest, root: Path) -> None:
    summaries = {_rel_to_root(root, k): v for k, v in ingest.file_summaries.items()}
    for mod in report.modules:
        hit = summaries.get(mod.path)
        if not hit:
            continue
        mod.metrics.coverage_line = hit.get("coverage_line")  # type: ignore[assignment]
        mod.metrics.coverage_branch = hit.get("coverage_branch")  # type: ignore[assignment]


def _count_module_findings(report: TestMetricsReport) -> None:
    by_file: dict[str, int] = {}
    for item in report.overall.weak_oracle_covered_lines:
        by_file[item["file"]] = by_file.get(item["file"], 0) + 1
    for mod in report.modules:
        mod.metrics.weak_oracle_covered_line_count = by_file.get(mod.path, 0)
        mod.metrics.unchecked_covered_callable_count = 0


def _rel_to_root(root: Path, file_key: str) -> str:
    path = Path(file_key)
    try:
        if path.is_absolute():
            return str(path.resolve().relative_to(root.resolve()))
        return str(path.as_posix())
    except ValueError:
        return str(path)
