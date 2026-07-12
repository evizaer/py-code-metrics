"""Recursive discovery of Python source files."""

from __future__ import annotations

from pathlib import Path

SKIP_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        ".eggs",
        "egg-info",
    }
)


def discover_python_files(root: Path) -> list[Path]:
    """Return sorted *.py paths under *root*, skipping junk directories."""
    root = root.resolve()
    if root.is_file():
        if root.suffix == ".py":
            return [root]
        return []

    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES or part.endswith(".egg-info") for part in path.parts):
            continue
        files.append(path)
    return sorted(files)
