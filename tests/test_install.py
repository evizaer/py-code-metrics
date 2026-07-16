"""Tests for post-package install and skill copy."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from py_code_metrics.cli import main
from py_code_metrics.install_cmd import (
    SKILL_NAME,
    InstallError,
    acquire_editable,
    acquire_pip_user,
    acquire_uv_dev,
    assert_safe_skills_dest,
    copy_skill_tree,
    project_skills_dest,
    run_project_post_install,
    skill_source_dir,
    user_skills_dest,
)


@pytest.fixture
def skill_src() -> Path:
    src = skill_source_dir()
    assert (src / "SKILL.md").is_file()
    return src


def test_skill_source_dir_finds_authoring_tree(skill_src: Path) -> None:
    assert skill_src.name == SKILL_NAME
    assert (skill_src / "reference.md").is_file()


def test_install_for_project_copies_skill(tmp_path: Path, skill_src: Path) -> None:
    results = run_project_post_install(tmp_path)
    dest = project_skills_dest(tmp_path)
    assert results[0].status == "copied"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == (skill_src / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert (dest / "reference.md").is_file()


def test_install_for_project_idempotent(tmp_path: Path) -> None:
    run_project_post_install(tmp_path)
    results = run_project_post_install(tmp_path)
    assert results[0].status == "unchanged"


def test_install_for_project_requires_force_when_divergent(tmp_path: Path) -> None:
    run_project_post_install(tmp_path)
    dest = project_skills_dest(tmp_path)
    (dest / "SKILL.md").write_text("diverged\n", encoding="utf-8")
    with pytest.raises(InstallError, match="--force"):
        run_project_post_install(tmp_path)
    results = run_project_post_install(tmp_path, force=True)
    assert results[0].status == "copied"
    assert "diverged" not in (dest / "SKILL.md").read_text(encoding="utf-8")


def test_install_for_project_dry_run_does_not_write(tmp_path: Path) -> None:
    results = run_project_post_install(tmp_path, dry_run=True)
    assert results[0].status == "planned"
    assert not project_skills_dest(tmp_path).exists()


def test_install_for_project_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(InstallError, match="not a directory"):
        run_project_post_install(missing)


def test_refuse_skills_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    reserved = fake_home / ".cursor" / "skills-cursor" / SKILL_NAME
    with pytest.raises(InstallError, match="skills-cursor"):
        assert_safe_skills_dest(reserved)


def test_copy_skill_refuses_skills_cursor_dest(
    tmp_path: Path,
    skill_src: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    dest = fake_home / ".cursor" / "skills-cursor" / SKILL_NAME
    with pytest.raises(InstallError, match="skills-cursor"):
        copy_skill_tree(skill_src, dest, force=False, dry_run=False)


def test_copy_skill_same_path_is_noop(skill_src: Path) -> None:
    result = copy_skill_tree(skill_src, skill_src, force=True, dry_run=False)
    assert result.status == "unchanged"
    assert (skill_src / "SKILL.md").is_file()


def test_cli_install_for_project_copies_skill(tmp_path: Path) -> None:
    code = main(["--install-for-project", str(tmp_path)])
    assert code == 0
    assert (project_skills_dest(tmp_path) / "SKILL.md").is_file()


def test_cli_install_for_project_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--install-for-project", str(tmp_path), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "copy-skill" in out
    assert not project_skills_dest(tmp_path).exists()


def test_cli_install_for_project_does_not_analyze_dot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: setup flags must not fall through to legacy analyze of ROOT."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dummy.py").write_text("x = 1\n", encoding="utf-8")
    code = main(["--install-for-project", "."])
    assert code == 0
    assert (tmp_path / ".cursor" / "skills" / SKILL_NAME / "SKILL.md").is_file()


def test_cli_install_for_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    code = main(["--install-for-user"])
    assert code == 0
    assert (user_skills_dest() / "SKILL.md").is_file()


def test_cli_force_without_install_mode_errors(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--uv-dev", "--force"])
    assert code == 2
    assert "--force" in capsys.readouterr().err


def test_acquire_uv_dev_invokes_subprocess(tmp_path: Path) -> None:
    with patch("py_code_metrics.install_cmd.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        assert acquire_uv_dev(cwd=tmp_path) == 0
        run.assert_called_once()
        cmd = run.call_args.args[0]
        assert cmd[:3] == ["uv", "add", "--dev"]


def test_acquire_pip_user_invokes_subprocess() -> None:
    with patch("py_code_metrics.install_cmd.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        assert acquire_pip_user() == 0
        cmd = run.call_args.args[0]
        assert cmd[-3:] == ["pip", "install", "--user"] or "pip" in cmd


def test_acquire_editable_missing_path(tmp_path: Path) -> None:
    with pytest.raises(InstallError, match="not a directory"):
        acquire_editable(tmp_path / "missing")


def test_cli_editable_missing_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--editable", str(tmp_path / "missing")])
    assert code == 2
    assert "not a directory" in capsys.readouterr().err
