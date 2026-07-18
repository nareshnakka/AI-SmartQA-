"""Tests for Report Bug / GitHub helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.github_repo import parse_github_owner_repo
from app.services.log_buffer import append_log_line, clear_logs, recent_logs_text
from app.services.bug_report import _redact, build_diagnostics, submit_bug_report


def test_parse_github_https():
    assert parse_github_owner_repo("https://github.com/nareshnakka/AI-SmartQA-.git") == (
        "nareshnakka",
        "AI-SmartQA-",
    )


def test_parse_github_ssh():
    assert parse_github_owner_repo("git@github.com:nareshnakka/AI-SmartQA-.git") == (
        "nareshnakka",
        "AI-SmartQA-",
    )


def test_redact_secrets():
    text = "Authorization: Bearer secret-token-value\nCURSOR_API_KEY=crsr_abc123xyz\n"
    out = _redact(text)
    assert "secret-token-value" not in out
    assert "crsr_abc123xyz" not in out
    assert "***" in out


def test_log_buffer_captures_lines():
    clear_logs()
    append_log_line("hello bug report")
    text = recent_logs_text(limit=10)
    assert "hello bug report" in text
    clear_logs()


@pytest.mark.asyncio
async def test_build_diagnostics_includes_version():
    docs = await build_diagnostics(None, page_url="http://localhost:3000/discovery")
    assert "diagnostics.md" in docs
    assert "logs.txt" in docs
    assert "QEOS version" in docs["diagnostics.md"]
    assert "localhost:3000/discovery" in docs["diagnostics.md"]


@pytest.mark.asyncio
async def test_submit_bug_report_happy_path():
    with patch("app.services.bug_report.resolve_bug_target", new=AsyncMock(return_value={
        "configured": True,
        "owner": "nareshnakka",
        "repo": "AI-SmartQA-",
        "branch": "main",
        "remote_url": "https://github.com/nareshnakka/AI-SmartQA-",
        "has_token": True,
        "token": "ghp_test",
        "message": "ok",
    })), patch(
        "app.services.bug_report.push_repo_files",
        new=AsyncMock(return_value={
            "success": True,
            "pushed": ["bug-reports/x/report.md"],
            "urls": {"bug-reports/x/report.md": "https://github.com/example"},
            "errors": [],
        }),
    ), patch(
        "app.services.bug_report.create_github_issue",
        new=AsyncMock(return_value={
            "number": 42,
            "html_url": "https://github.com/nareshnakka/AI-SmartQA-/issues/42",
        }),
    ), patch(
        "app.services.bug_report.build_diagnostics",
        new=AsyncMock(return_value={"diagnostics.md": "# diag\n", "logs.txt": "logs\n"}),
    ):
        result = await submit_bug_report(
            None,
            title="Discovery fails",
            description="Menus skipped after Fashion",
            steps_to_reproduce="1. Run Flipkart prompt",
            include_diagnostics=True,
            screenshot_bytes=b"\x89PNG",
            screenshot_filename="shot.png",
        )

    assert result["ok"] is True
    assert result["issue_number"] == 42
    assert "issues/42" in result["html_url"]


@pytest.mark.asyncio
async def test_submit_requires_token():
    with patch("app.services.bug_report.resolve_bug_target", new=AsyncMock(return_value={
        "configured": False,
        "owner": "nareshnakka",
        "repo": "AI-SmartQA-",
        "branch": "main",
        "remote_url": "",
        "has_token": False,
        "token": "",
        "message": "Set QEOS_GITHUB_BUG_TOKEN",
    })):
        with pytest.raises(ValueError, match="QEOS_GITHUB_BUG_TOKEN"):
            await submit_bug_report(None, title="t", description="long enough")
