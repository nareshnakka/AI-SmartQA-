from unittest.mock import patch

import pytest

from app.services.app_updates import (
    _changelog_sync,
    _git_check_sync,
    _version_label,
    backup_user_data,
    find_repo_root,
)


def test_find_repo_root():
    root = find_repo_root()
    assert root is not None
    assert (root / ".git").is_dir()


def test_version_label():
    assert _version_label({"major": 2, "minor": 0, "build": 14}) == "V2.0-Build 14"
    assert _version_label(None) is None


def test_git_check_sync_no_fetch():
    root = find_repo_root()
    assert root is not None
    result = _git_check_sync(root, fetch=False)
    assert "current_commit" in result
    assert "branch" in result
    assert isinstance(result.get("available"), bool)
    assert "changelog" in result
    assert "auto_update_enabled" in result


def test_git_check_sync_behind_with_changelog():
    root = find_repo_root()
    assert root is not None
    with patch("app.services.app_updates._run_git") as mock_git, patch(
        "app.services.app_updates._read_version_file",
        return_value={"major": 2, "minor": 0, "build": 13},
    ), patch(
        "app.services.app_updates._remote_version_sync",
        return_value={"major": 2, "minor": 0, "build": 14},
    ), patch(
        "app.services.app_updates._changelog_sync",
        return_value=[{"sha": "abc1234", "message": "Add auto-update", "author": "dev", "date": ""}],
    ):
        mock_git.side_effect = [
            type("R", (), {"returncode": 0, "stdout": "main\n", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "abc1234567890\n", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "def1234567890\n", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "2\n", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "https://github.com/example/repo.git\n", "stderr": ""})(),
        ]
        result = _git_check_sync(root, fetch=False)
    assert result["available"] is True
    assert result["commits_behind"] == 2
    assert result["current_version"] == "V2.0-Build 13"
    assert result["remote_version"] == "V2.0-Build 14"
    assert result["changelog"][0]["message"] == "Add auto-update"
    assert "2.0-Build 13" in result["summary"] or "V2.0-Build 13" in result["summary"]


def test_changelog_sync_parses_lines():
    root = find_repo_root()
    assert root is not None
    with patch("app.services.app_updates._run_git") as mock_git:
        mock_git.return_value = type(
            "R",
            (),
            {
                "returncode": 0,
                "stdout": "a1b2c3d|Fix discovery|Dev|2026-07-18T10:00:00Z\neeeffff|Bump version|Bot|2026-07-18T11:00:00Z\n",
                "stderr": "",
            },
        )()
        entries = _changelog_sync(root, "main")
    assert len(entries) == 2
    assert entries[0]["sha"] == "a1b2c3d"
    assert entries[0]["message"] == "Fix discovery"
    assert entries[1]["message"] == "Bump version"


def test_backup_user_data(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "qeos.db").write_bytes(b"sqlite")
    (tmp_path / "data").mkdir()
    result = backup_user_data(tmp_path)
    assert result["copied"]
    assert (tmp_path / result["backup_dir"]).is_dir()


def test_windows_update_scripts_exist():
    root = find_repo_root()
    assert root is not None
    for rel in (
        "update-and-install.bat",
        "restart.bat",
        "stop.bat",
    ):
        assert (root / rel).is_file(), f"missing {rel}"
