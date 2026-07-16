"""Post-package project setup and optional package-acquire helpers."""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SKILL_NAME = "metrics-guided-implement"
PACKAGE_NAME = "py-code-metrics"


@dataclass(frozen=True)
class StepResult:
    step_id: str
    status: str  # "copied" | "unchanged" | "planned" | "skipped"
    detail: str


class InstallError(Exception):
    """User-facing install failure (missing path, refuse overwrite, etc.)."""


def skill_source_dir() -> Path:
    """Locate shipped skill data (wheel) or authoring tree (editable/dev)."""
    packaged = Path(__file__).resolve().parent / "skill_data" / SKILL_NAME
    if _is_skill_dir(packaged):
        return packaged
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".cursor" / "skills" / SKILL_NAME
        if _is_skill_dir(candidate):
            return candidate
    raise InstallError(
        f"skill data not found: expected package skill_data/{SKILL_NAME} "
        f"or .cursor/skills/{SKILL_NAME}"
    )


def _is_skill_dir(path: Path) -> bool:
    return path.is_dir() and (path / "SKILL.md").is_file()


def project_skills_dest(root: Path) -> Path:
    return root.resolve() / ".cursor" / "skills" / SKILL_NAME


def user_skills_dest() -> Path:
    return Path.home() / ".cursor" / "skills" / SKILL_NAME


def assert_safe_skills_dest(dest: Path) -> None:
    """Refuse writes under Cursor's reserved builtins skills directory."""
    resolved = dest.resolve()
    reserved = (Path.home() / ".cursor" / "skills-cursor").resolve()
    try:
        resolved.relative_to(reserved)
    except ValueError:
        return
    raise InstallError(f"refusing to write under reserved Cursor builtins path: {reserved}")


def copy_skill_tree(src: Path, dest: Path, *, force: bool, dry_run: bool) -> StepResult:
    """Copy skill directory idempotently. Divergent content requires force."""
    assert_safe_skills_dest(dest)
    if not _is_skill_dir(src):
        raise InstallError(f"invalid skill source (missing SKILL.md): {src}")
    src_r, dest_r = src.resolve(), dest.resolve()
    if src_r == dest_r:
        return StepResult("copy-skill", "unchanged", str(dest_r))

    if dest.exists():
        if _trees_equal(src, dest):
            return StepResult("copy-skill", "unchanged", str(dest))
        if not force:
            raise InstallError(
                f"destination exists and differs from packaged skill: {dest}\n"
                f"re-run with --force to overwrite"
            )
        if dry_run:
            return StepResult("copy-skill", "planned", f"overwrite {dest}")
        shutil.rmtree(dest)
    elif dry_run:
        return StepResult("copy-skill", "planned", f"create {dest}")

    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
    return StepResult("copy-skill", "copied" if not dry_run else "planned", str(dest))


def _trees_equal(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(_trees_equal(a / sub, b / sub) for sub in cmp.common_dirs)


def run_project_post_install(
    root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[StepResult]:
    """Run all post-package project setup steps for ROOT."""
    root = root.resolve()
    if not root.is_dir():
        raise InstallError(f"project root is not a directory: {root}")
    src = skill_source_dir()
    dest = project_skills_dest(root)
    return [copy_skill_tree(src, dest, force=force, dry_run=dry_run)]


def run_user_post_install(*, force: bool = False, dry_run: bool = False) -> list[StepResult]:
    """Install the adoption skill into ~/.cursor/skills/."""
    src = skill_source_dir()
    dest = user_skills_dest()
    return [copy_skill_tree(src, dest, force=force, dry_run=dry_run)]


def format_install_summary(results: list[StepResult], *, dry_run: bool) -> str:
    lines = ["post-install:" if not dry_run else "post-install (dry-run):"]
    for r in results:
        lines.append(f"  [{r.status}] {r.step_id}: {r.detail}")
    lines.extend(
        [
            "",
            "next:",
            "  uv run py-code-metrics snapshot src/<pkg> -o /tmp/pcm-before.json",
            "  uv run py-code-metrics board -f /tmp/pcm-before.json",
            "  uv run py-code-metrics hotspots -f /tmp/pcm-before.json",
            "See docs/adoption.md (in the py-code-metrics repo) for the full loop.",
        ]
    )
    return "\n".join(lines)


def acquire_uv_dev(*, cwd: Path | None = None) -> int:
    return _run_acquire(["uv", "add", "--dev", PACKAGE_NAME], cwd=cwd)


def acquire_pip_user() -> int:
    return _run_acquire([sys.executable, "-m", "pip", "install", "--user", PACKAGE_NAME])


def acquire_editable(path: Path, *, cwd: Path | None = None) -> int:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise InstallError(f"editable path is not a directory: {resolved}")
    return _run_acquire(
        ["uv", "add", "--dev", "--editable", str(resolved)],
        cwd=cwd,
    )


def _run_acquire(cmd: list[str], *, cwd: Path | None = None) -> int:
    try:
        completed = subprocess.run(cmd, cwd=cwd, check=False)
    except FileNotFoundError as exc:
        raise InstallError(f"command not found: {cmd[0]}") from exc
    return int(completed.returncode)


# Named steps for future extension (copy-skill is the only MVP step).
POST_INSTALL_STEPS: dict[str, Callable[..., list[StepResult]]] = {
    "project": run_project_post_install,
    "user": run_user_post_install,
}
