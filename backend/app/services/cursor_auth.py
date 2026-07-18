"""Browser PKCE login for Cursor — sign-in + Cloud Agents API key setup."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
import structlog

from app.integrations.cursor_api import CursorAPIError, CursorCloudClient
from app.services.cursor_credential_store import (
    clear_credentials,
    get_cloud_api_key,
    get_session_cookie_value,
    has_cursor_session,
    load_credentials,
    save_credentials,
)

logger = structlog.get_logger()

CURSOR_AUTH_BASE = "https://api2.cursor.sh"
CURSOR_LOGIN_BASE = "https://cursor.com/loginDeepControl"
CURSOR_API_KEYS_URL = "https://cursor.com/dashboard/api-keys"
CURSOR_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Cursor/2.0.0 Chrome/132.0.0.0 Electron/34.0.0 Safari/537.36"
)

ConnectStatus = Literal["pending", "completed", "failed", "expired", "cancelled"]


@dataclass
class CursorConnectSession:
    session_id: str
    verifier: str
    challenge: str
    poll_uuid: str
    created_at: float = field(default_factory=time.monotonic)
    status: ConnectStatus = "pending"
    message: str = "Waiting for you to sign in to Cursor in the browser…"
    email: str | None = None
    error: str | None = None

    @property
    def auth_url(self) -> str:
        return (
            f"{CURSOR_LOGIN_BASE}?challenge={self.challenge}"
            f"&uuid={self.poll_uuid}&mode=login&redirectTarget=cli"
        )

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "message": self.message,
            "auth_url": self.auth_url if self.status == "pending" else None,
            "email": self.email,
            "error": self.error,
            "needs_api_key": self.status == "completed" and not get_cloud_api_key(),
            "api_keys_url": CURSOR_API_KEYS_URL,
        }


_sessions: dict[str, CursorConnectSession] = {}
SESSION_TTL_SEC = 600.0


def _generate_pkce() -> tuple[str, str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge, str(uuid.uuid4())


def _purge_stale_sessions() -> None:
    now = time.monotonic()
    stale = [sid for sid, s in _sessions.items() if now - s.created_at > SESSION_TTL_SEC]
    for sid in stale:
        session = _sessions.pop(sid, None)
        if session and session.status == "pending":
            session.status = "expired"
            session.message = "Connection timed out — click Connect Cursor to try again."


def start_connect_session() -> CursorConnectSession:
    _purge_stale_sessions()
    verifier, challenge, poll_uuid = _generate_pkce()
    session_id = secrets.token_urlsafe(16)
    session = CursorConnectSession(
        session_id=session_id,
        verifier=verifier,
        challenge=challenge,
        poll_uuid=poll_uuid,
        message=(
            "Cursor sign-in opened — if you are already logged in, click **Yes, Log In**. "
            "QEOS will continue automatically when you accept."
        ),
    )
    _sessions[session_id] = session
    return session


def cancel_connect_session(session_id: str) -> bool:
    session = _sessions.get(session_id)
    if not session or session.status != "pending":
        return False
    session.status = "cancelled"
    session.message = "Connection cancelled."
    return True


async def _poll_auth_once(session: CursorConnectSession) -> dict[str, Any] | None:
    params = {"uuid": session.poll_uuid, "verifier": session.verifier}
    headers = {"User-Agent": CURSOR_USER_AGENT, "Accept": "*/*"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{CURSOR_AUTH_BASE}/auth/poll", params=params, headers=headers)

    if response.status_code in (204, 404, 202):
        return None
    if response.status_code != 200:
        text = response.text[:200]
        if response.status_code >= 500:
            logger.debug("cursor_auth_poll_retry", status=response.status_code, detail=text)
            return None
        raise CursorAPIError(f"Cursor auth poll failed ({response.status_code}): {text}")

    try:
        data = response.json()
    except Exception as exc:
        raise CursorAPIError(f"Invalid Cursor auth poll response: {exc}") from exc

    if isinstance(data, dict) and data.get("accessToken"):
        return data
    return None


async def _fetch_profile_email(auth_id: str, access_token: str) -> str | None:
    cookie = f"WorkosCursorSessionToken={auth_id}::{access_token}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://cursor.com/api/auth/me",
                headers={"Cookie": cookie, "Accept": "application/json", "User-Agent": CURSOR_USER_AGENT},
            )
        if response.status_code == 200:
            data = response.json()
            return data.get("email") or data.get("name")
    except Exception:
        pass
    return None


async def validate_cloud_api_key(api_key: str) -> dict[str, Any]:
    key = (api_key or "").strip()
    if not key.startswith("crsr_"):
        raise CursorAPIError(
            "Paste a Cursor User API key from cursor.com/dashboard/api-keys (starts with crsr_)."
        )
    client = CursorCloudClient(key)
    return await client.me()


async def save_cloud_api_key(api_key: str) -> dict[str, Any]:
    key = (api_key or "").strip()
    me = await validate_cloud_api_key(key)
    creds = load_credentials()
    save_credentials({
        **creds,
        "api_key": key,
        "api_key_name": me.get("apiKeyName"),
        "email": me.get("userEmail") or creds.get("email"),
        "source": "browser_pkce" if has_cursor_session() else "api_key",
    })
    return {
        "saved": True,
        "email": me.get("userEmail") or creds.get("email"),
        "api_key_name": me.get("apiKeyName"),
        "message": "Cursor Agent API key saved — Discovery advisor is ready.",
    }


async def _complete_session(session: CursorConnectSession, poll_data: dict[str, Any]) -> None:
    access = str(poll_data.get("accessToken") or "").strip()
    refresh = str(poll_data.get("refreshToken") or "").strip()
    auth_id = str(poll_data.get("authId") or "").strip()
    if not access or not auth_id:
        session.status = "failed"
        session.error = "Cursor returned an incomplete sign-in response."
        session.message = session.error
        return

    email = await _fetch_profile_email(auth_id, access)
    creds = load_credentials()
    save_credentials({
        **creds,
        "access_token": access,
        "refresh_token": refresh,
        "auth_id": auth_id,
        "email": email,
        "source": "browser_pkce",
    })

    session.status = "completed"
    session.email = email
    if get_cloud_api_key():
        session.message = (
            f"Signed in to Cursor{f' as {email}' if email else ''} — Discovery advisor is ready."
        )
    else:
        session.message = (
            f"Signed in to Cursor{f' as {email}' if email else ''}. "
            "Paste your Agent API key below (one-time) to enable Discovery planning."
        )


async def poll_connect_session(session_id: str) -> dict[str, Any]:
    _purge_stale_sessions()
    session = _sessions.get(session_id)
    if not session:
        return {
            "session_id": session_id,
            "status": "failed",
            "message": "Unknown or expired connection session.",
            "error": "session_not_found",
        }

    if session.status != "pending":
        return session.to_status_dict()

    if time.monotonic() - session.created_at > SESSION_TTL_SEC:
        session.status = "expired"
        session.message = "Connection timed out — click Connect Cursor to try again."
        return session.to_status_dict()

    try:
        poll_data = await _poll_auth_once(session)
        if poll_data:
            await _complete_session(session, poll_data)
    except CursorAPIError as exc:
        session.status = "failed"
        session.error = str(exc)
        session.message = f"Cursor connection failed: {exc}"

    return session.to_status_dict()


async def disconnect_cursor() -> dict[str, Any]:
    clear_credentials()
    for session in _sessions.values():
        if session.status == "pending":
            session.status = "cancelled"
    return {"disconnected": True, "message": "Cursor disconnected from QEOS."}


def connection_summary() -> dict[str, Any]:
    creds = load_credentials()
    return {
        "signed_in": has_cursor_session(),
        "has_api_key": bool(get_cloud_api_key()),
        "connected": bool(get_cloud_api_key()),
        "email": creds.get("email"),
        "api_key_name": creds.get("api_key_name"),
        "source": creds.get("source"),
        "updated_at": creds.get("updated_at"),
        "api_keys_url": CURSOR_API_KEYS_URL,
    }
