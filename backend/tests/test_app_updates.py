from unittest.mock import patch

import pytest

from app.services.app_updates import _git_check_sync, find_repo_root


def test_find_repo_root():
    root = find_repo_root()
    assert root is not None
    assert (root / ".git").is_dir()


def test_git_check_sync_no_fetch():
    root = find_repo_root()
    assert root is not None
    result = _git_check_sync(root, fetch=False)
    assert "current_commit" in result
    assert "branch" in result
    assert isinstance(result.get("available"), bool)


def test_git_check_sync_behind_count():
    root = find_repo_root()
    assert root is not None
    with patch("app.services.app_updates._run_git") as mock_git:
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
    assert result["current_commit"] == "abc1234"
    assert result["remote_commit"] == "def1234"
