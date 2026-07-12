"""Parse Python source files into ASTs."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedFile:
    path: Path
    source: str
    tree: ast.Module


@dataclass(frozen=True)
class SkippedFile:
    path: Path
    reason: str


def parse_files(paths: list[Path]) -> tuple[list[ParsedFile], list[SkippedFile]]:
    parsed: list[ParsedFile] = []
    skipped: list[SkippedFile] = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            skipped.append(SkippedFile(path=path, reason=f"read error: {exc}"))
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            skipped.append(
                SkippedFile(
                    path=path,
                    reason=f"syntax error: {exc.msg} (line {exc.lineno})",
                )
            )
            continue
        parsed.append(ParsedFile(path=path, source=source, tree=tree))
    return parsed, skipped
