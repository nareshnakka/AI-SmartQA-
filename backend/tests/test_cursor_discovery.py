"""Tests for Cursor Cloud API Discovery advisor integration."""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_cursor_qeos.db")
os.environ.setdefault("QEOS_AUTH_ENABLED", "false")

from app.main import app  # noqa: E402
from app.db.session import init_db  # noqa: E402
from app.services.cursor_discovery_advisor import (
    _extract_json_object,
    apply_cursor_discovery_plan,
    get_cursor_discovery_status,
    suggest_menu_click_aliases,
)
from app.runners.discovery_prompt import DiscoveryIntent, parse_discovery_prompt


@pytest.fixture(scope="session")
async def setup_db():
    if os.path.exists("test_cursor_qeos.db"):
        os.remove("test_cursor_qeos.db")
    await init_db()


@pytest.fixture
async def client(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_extract_json_object_from_markdown_fence():
    raw = '```json\n{"menu_targets": ["Fashion", "Mobiles"]}\n```'
    data = _extract_json_object(raw)
    assert data == {"menu_targets": ["Fashion", "Mobiles"]}


@pytest.mark.asyncio
async def test_cursor_status_not_configured():
    with patch("app.services.cursor_credential_store.get_cloud_api_key", return_value=""), patch(
        "app.services.cursor_credential_store.has_cursor_session", return_value=False
    ):
        status = await get_cursor_discovery_status()
    assert status["configured"] is False
    assert status["available"] is False
    assert "Connect Cursor" in status["message"]


@pytest.mark.asyncio
async def test_cursor_status_needs_api_key_after_signin():
    with patch("app.services.cursor_credential_store.get_cloud_api_key", return_value=""), patch(
        "app.services.cursor_credential_store.has_cursor_session", return_value=True
    ), patch("app.services.cursor_auth.connection_summary", return_value={
        "email": "user@example.com",
        "api_keys_url": "https://cursor.com/dashboard/api-keys",
    }):
        status = await get_cursor_discovery_status()
    assert status["signed_in"] is True
    assert status["needs_api_key"] is True
    assert status["available"] is False
    assert "crsr_" in status["message"]


@pytest.mark.asyncio
async def test_apply_cursor_skips_when_user_menu_list_parsed():
    text = """no login

Navigate each of the below menus:
Fashion
Mobiles
"""
    intent = parse_discovery_prompt(text)
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    with patch("app.services.cursor_discovery_advisor.get_cursor_client_async") as mock_get:
        mock_get.return_value.run_prompt_no_repo = AsyncMock()
        result = await apply_cursor_discovery_plan(intent, "https://www.flipkart.com", emit)

    assert len(result.explicit_targets) >= 2
    mock_get.return_value.run_prompt_no_repo.assert_not_called()
    assert any("using your menu list" in e.get("message", "") for e in events)


@pytest.mark.asyncio
async def test_apply_cursor_enriches_unparsed_prompt():
    intent = DiscoveryIntent(
        raw="Explore top navigation on example.com",
        goals="Explore top navigation on example.com",
        summary="explore",
        strict_follow=True,
    )
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    mock_client = AsyncMock()
    mock_client.run_prompt_no_repo.return_value = json.dumps({
        "menu_targets": ["Home", "Products", "Contact"],
        "navigation_strategy": "return_home_between_menus",
        "notes": "simple header nav",
    })

    with patch("app.services.cursor_discovery_advisor.get_cursor_client_async", return_value=mock_client):
        result = await apply_cursor_discovery_plan(intent, "https://example.com", emit)

    assert result.explicit_targets == ["Home", "Products", "Contact"]
    assert result.menu_list_navigation is True
    mock_client.run_prompt_no_repo.assert_awaited_once()


@pytest.mark.asyncio
async def test_suggest_menu_click_aliases():
    mock_client = AsyncMock()
    mock_client.run_prompt_no_repo.return_value = json.dumps({
        "aliases": ["Baby & Kids"],
        "hint": "hover mega-menu",
    })

    with patch("app.services.cursor_discovery_advisor.get_cursor_client_async", return_value=mock_client):
        aliases = await suggest_menu_click_aliases(
            "Toys, Baby & Kids",
            ["Fashion", "Baby & Kids", "Electronics"],
            "https://www.flipkart.com",
        )

    assert aliases == ["Baby & Kids"]


@pytest.mark.asyncio
async def test_cursor_discovery_status_endpoint(client):
    r = await client.get("/api/v1/cursor/discovery-status")
    assert r.status_code == 200
    data = r.json()
    assert "configured" in data
    assert "enabled" in data
    assert "available" in data


@pytest.mark.asyncio
async def test_cursor_connect_start_returns_auth_url(client):
    r = await client.post("/api/v1/cursor/connect/start")
    assert r.status_code == 200
    data = r.json()
    assert "session_id" in data
    assert "auth_url" in data
    assert "loginDeepControl" in data["auth_url"]
