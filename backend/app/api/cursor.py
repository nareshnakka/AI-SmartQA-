"""Cursor Cloud API — connect, status, and Discovery advisor."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query

from app.services.cursor_auth import (
    CURSOR_API_KEYS_URL,
    cancel_connect_session,
    connection_summary,
    disconnect_cursor,
    poll_connect_session,
    save_cloud_api_key,
    start_connect_session,
)
from app.services.cursor_discovery_advisor import get_cursor_discovery_status

router = APIRouter(prefix="/cursor", tags=["Cursor Integration"])


class CursorApiKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=20)


@router.get("/discovery-status")
async def cursor_discovery_status():
    """Whether Cursor is connected and available for Discovery planning."""
    return await get_cursor_discovery_status()


@router.post("/connect/start")
async def cursor_connect_start():
    """
    Start browser PKCE sign-in. Open the returned auth_url in the browser;
    poll /connect/status until status is completed.
    """
    session = start_connect_session()
    return {
        **session.to_status_dict(),
        "auth_url": session.auth_url,
        "api_keys_url": CURSOR_API_KEYS_URL,
        "instructions": (
            "A browser tab opens for Cursor sign-in. Click **Yes, Log In** when prompted. "
            "After sign-in, paste your Agent API key from the dashboard (one-time)."
        ),
        "expires_in_sec": 600,
    }


@router.get("/connect/status")
async def cursor_connect_status(session_id: str = Query(..., min_length=8)):
    """Poll Cursor sign-in progress (call every 2–3s after /connect/start)."""
    return await poll_connect_session(session_id)


@router.post("/connect/api-key")
async def cursor_save_api_key(body: CursorApiKeyRequest):
    """Save and validate a Cursor Cloud Agents API key (crsr_…)."""
    try:
        return await save_cloud_api_key(body.api_key)
    except Exception as exc:
        from app.integrations.cursor_api import CursorAPIError

        if isinstance(exc, CursorAPIError):
            raise HTTPException(400, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc


@router.post("/connect/cancel")
async def cursor_connect_cancel(session_id: str = Query(..., min_length=8)):
    if not cancel_connect_session(session_id):
        raise HTTPException(404, "Session not found or already finished")
    return {"cancelled": True, "session_id": session_id}


@router.delete("/connect")
async def cursor_disconnect():
    """Remove stored Cursor credentials from this QEOS install."""
    return await disconnect_cursor()


@router.get("/connection")
async def cursor_connection():
    """Lightweight connection summary (no live API call)."""
    return connection_summary()
