"""Ingest mutmut / Cosmic Ray / PCM-normalized mutation reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_code_metrics.model import MutationSurvivor, TestMetricsReport
from py_code_metrics.resolve import CallableInfo, SymbolIndex

PCM_MUTATION_FORMAT = "py-code-metrics.mutation.v1"
SURVIVED_OUTCOMES = frozenset({"survived", "SURVIVED"})


class MutationLoadError(ValueError):
    """Raised when a mutation report cannot be parsed."""


@dataclass
class MutationIngest:
    format_name: str
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    skipped: int = 0
    survivors: list[MutationSurvivor] = field(default_factory=list)

    @property
    def mutation_score(self) -> float | None:
        denom = self.killed + self.survived
        if denom <= 0:
            return None
        return self.killed / denom


def load_mutation_json(path: Path) -> MutationIngest:
    """Parse a mutation report; auto-detect PCM v1, mutmut CICID, or Cosmic Ray dump."""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        raise MutationLoadError("mutation report is empty")

    if _looks_like_ndjson(stripped):
        return _from_cosmic_ray_ndjson(stripped)

    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise MutationLoadError(f"invalid mutation JSON: {exc}") from exc

    if isinstance(raw, list):
        return _from_cosmic_ray_array(raw)
    if not isinstance(raw, dict):
        raise MutationLoadError("mutation report must be a JSON object or Cosmic Ray dump")

    if raw.get("format") == PCM_MUTATION_FORMAT:
        return _from_pcm_v1(raw)
    if _is_mutmut_cicd(raw):
        return _from_mutmut_cicd(raw)
    raise MutationLoadError(
        "unrecognized mutation report shape "
        "(expected py-code-metrics.mutation.v1, mutmut CICID, or Cosmic Ray dump)"
    )


def apply_mutation(
    report: TestMetricsReport,
    ingest: MutationIngest,
    root: Path,
    index: SymbolIndex | None = None,
) -> None:
    """Attach mutation score and survivors; tag overlaps with coverage signals when present."""
    survivors = [_rel_survivor(item, root) for item in ingest.survivors]
    if index is not None:
        survivors = [_tag_overlap(s, report, index, root) for s in survivors]
    else:
        survivors = [_tag_overlap_lines_only(s, report) for s in survivors]

    report.overall.mutation_score = ingest.mutation_score
    report.overall.survivors = survivors
    if survivors:
        report.overall.survivor_count = len(survivors)
    else:
        report.overall.survivor_count = ingest.survived

    _attach_module_survivors(report)


def _looks_like_ndjson(text: str) -> bool:
    """True when each non-empty line is its own JSON value (Cosmic Ray dump)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    if not all(ln.startswith(("[", "{")) for ln in lines):
        return False
    # Pretty-printed single JSON objects have indented continuation lines.
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return True
    return False


def _is_mutmut_cicd(raw: dict[str, Any]) -> bool:
    return "killed" in raw and "survived" in raw and "format" not in raw


def _from_pcm_v1(raw: dict[str, Any]) -> MutationIngest:
    survivors = [_normalize_survivor(s) for s in (raw.get("survivors") or [])]
    return MutationIngest(
        format_name="pcm_v1",
        killed=_int(raw.get("killed")),
        survived=_int(raw.get("survived"), default=len(survivors)),
        timeout=_int(raw.get("timeout")),
        skipped=_int(raw.get("skipped")),
        survivors=survivors,
    )


def _from_mutmut_cicd(raw: dict[str, Any]) -> MutationIngest:
    return MutationIngest(
        format_name="mutmut_cicd",
        killed=_int(raw.get("killed")),
        survived=_int(raw.get("survived")),
        timeout=_int(raw.get("timeout")),
        skipped=_int(raw.get("skipped")),
        survivors=[],
    )


def _from_cosmic_ray_ndjson(text: str) -> MutationIngest:
    rows: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise MutationLoadError(f"invalid Cosmic Ray NDJSON line: {exc}") from exc
    return _from_cosmic_ray_array(rows)


def _from_cosmic_ray_array(rows: list[Any]) -> MutationIngest:
    if not rows:
        raise MutationLoadError("Cosmic Ray dump is empty")
    killed = 0
    survived = 0
    timeout = 0
    skipped = 0
    survivors: list[MutationSurvivor] = []
    for row in rows:
        item, result = _split_cosmic_row(row)
        outcome = _cosmic_outcome(result)
        if outcome in SURVIVED_OUTCOMES:
            survived += 1
            survivors.append(_survivor_from_cosmic(item, result))
        elif outcome in {"killed", "KILLED"}:
            killed += 1
        elif outcome in {"timeout", "TIMEOUT"}:
            timeout += 1
        elif outcome in {"skipped", "SKIPPED", None}:
            skipped += 1
        else:
            # treat unknown completed outcomes as killed-ish for score stability
            if outcome:
                killed += 1
    return MutationIngest(
        format_name="cosmic_ray",
        killed=killed,
        survived=survived,
        timeout=timeout,
        skipped=skipped,
        survivors=survivors,
    )


def _split_cosmic_row(row: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if isinstance(row, list) and len(row) == 2:
        item, result = row[0], row[1]
        if not isinstance(item, dict):
            raise MutationLoadError("Cosmic Ray work item must be an object")
        if result is not None and not isinstance(result, dict):
            raise MutationLoadError("Cosmic Ray work result must be an object or null")
        return item, result
    if isinstance(row, dict):
        # Flat dump variant used in some exports / fixtures
        return row, row
    raise MutationLoadError("Cosmic Ray row must be [work_item, work_result] or an object")


def _cosmic_outcome(result: dict[str, Any] | None) -> str | None:
    if result is None:
        return None
    return result.get("test_outcome") or result.get("outcome")


def _survivor_from_cosmic(item: dict[str, Any], result: dict[str, Any] | None) -> MutationSurvivor:
    merged = {**item, **(result or {})}
    line = merged.get("line_number")
    if line is None:
        start = merged.get("start_pos") or merged.get("start_pos_row")
        line = start[0] if isinstance(start, (list, tuple)) and start else start
    path = merged.get("module_path") or merged.get("module") or merged.get("filename") or ""
    return _normalize_survivor(
        {
            "file": path,
            "line": line,
            "id": merged.get("job_id") or merged.get("id"),
            "operator": merged.get("operator") or merged.get("operator_name"),
            "status": "survived",
        }
    )


def _normalize_survivor(raw: dict[str, Any] | Any) -> MutationSurvivor:
    if not isinstance(raw, dict):
        raise MutationLoadError("survivor entries must be objects")
    return MutationSurvivor.from_dict(raw)


def _int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rel_survivor(item: MutationSurvivor, root: Path) -> MutationSurvivor:
    return MutationSurvivor(
        file=_rel_to_root(root, item.file or ""),
        line=item.line,
        id=item.id,
        operator=item.operator,
        status=item.status,
        overlap_flags=list(item.overlap_flags),
    )


def _rel_to_root(root: Path, file_key: str) -> str:
    if not file_key:
        return ""
    path = Path(file_key)
    try:
        if path.is_absolute():
            return str(path.resolve().relative_to(root.resolve()))
        return str(path.as_posix())
    except ValueError:
        return str(path)


def _tag_overlap_lines_only(
    survivor: MutationSurvivor, report: TestMetricsReport
) -> MutationSurvivor:
    flags: list[str] = []
    for item in report.overall.weak_oracle_covered_lines:
        if item.file == survivor.file and item.line == survivor.line:
            flags.append("weak_oracle_covered_line")
            break
    return MutationSurvivor(
        file=survivor.file,
        line=survivor.line,
        id=survivor.id,
        operator=survivor.operator,
        status=survivor.status,
        overlap_flags=flags,
    )


def _tag_overlap(
    survivor: MutationSurvivor,
    report: TestMetricsReport,
    index: SymbolIndex,
    root: Path,
) -> MutationSurvivor:
    out = _tag_overlap_lines_only(survivor, report)
    flags = list(out.overlap_flags)
    line = survivor.line
    file = survivor.file or ""
    if line is None or not file:
        out.overlap_flags = flags
        return out
    unchecked = set(report.overall.unchecked_covered_callables)
    for qname in unchecked:
        info = index.callables.get(qname)
        if info is None:
            continue
        if not _callable_in_file(info, index, file, root):
            continue
        if _line_in_callable(info, int(line)):
            flags.append("unchecked_covered_callable")
            break
    out.overlap_flags = flags
    return out


def _callable_in_file(info: CallableInfo, index: SymbolIndex, file_rel: str, root: Path) -> bool:
    mi = index.modules.get(info.module)
    if mi is None:
        return False
    try:
        rel = str(mi.path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(mi.path)
    return (
        rel.replace("\\", "/") == file_rel.replace("\\", "/") or mi.path.name == Path(file_rel).name
    )


def _line_in_callable(info: CallableInfo, line: int) -> bool:
    start = info.node.lineno
    end = getattr(info.node, "end_lineno", None) or start
    return start <= line <= end


def _attach_module_survivors(report: TestMetricsReport) -> None:
    by_file: dict[str, int] = {}
    for item in report.overall.survivors:
        f = item.file or ""
        by_file[f] = by_file.get(f, 0) + 1
    for mod in report.modules:
        mod.metrics.survivor_count = by_file.get(mod.path, 0)
        # Production survivors often live outside test modules; count by basename too
        if mod.metrics.survivor_count == 0:
            base = Path(mod.path).name
            mod.metrics.survivor_count = sum(c for f, c in by_file.items() if Path(f).name == base)
