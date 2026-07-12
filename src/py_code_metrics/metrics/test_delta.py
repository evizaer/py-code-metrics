"""Git delta path helpers for test-quality reports."""

from __future__ import annotations

import subprocess
from pathlib import Path


def changed_python_paths(root: Path) -> tuple[list[str], str | None]:
    """Return changed *.py paths relative to *root*, plus an optional note.

    Soft-fails (empty list + note) when git is unavailable or *root* is not a repo.
    Diff base: merge-base with main/master when available, else HEAD~1.
    """
    root = root.resolve()
    try:
        base = _diff_base(root)
        proc = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", base],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return [], f"git unavailable: {exc}"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "git diff failed").strip()
        return [], msg
    paths = [line.strip() for line in proc.stdout.splitlines() if line.strip().endswith(".py")]
    return paths, None


def _diff_base(root: Path) -> str:
    for branch in ("main", "master"):
        mb = subprocess.run(
            ["git", "-C", str(root), "merge-base", "HEAD", branch],
            check=False,
            capture_output=True,
            text=True,
        )
        if mb.returncode == 0 and mb.stdout.strip():
            return mb.stdout.strip()
    return "HEAD~1"
