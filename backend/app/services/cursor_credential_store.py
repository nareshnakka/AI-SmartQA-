"""Persist Cursor OAuth session + Cloud Agents API key for Discovery."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_CACHE: dict[str, Any] | None = None


def _repo_root() -> Path:
    env_root = os.environ.get("QEOS_REPO_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[3]


def credentials_path() -> Path:
    return _repo_root() / "data" / "cursor_credentials.json"


def load_credentials() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return dict(_CACHE)

    path = credentials_path()
    if not path.is_file():
        _CACHE = {}
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _CACHE = data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("cursor_credentials_read_failed", error=str(exc))
        _CACHE = {}
    return dict(_CACHE)


def save_credentials(data: dict[str, Any]) -> None:
    global _CACHE
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _CACHE = payload


def clear_credentials() -> None:
    global _CACHE
    path = credentials_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("cursor_credentials_delete_failed", error=str(exc))
    _CACHE = {}


def _looks_like_cloud_api_key(value: str) -> bool:
    key = (value or "").strip()
    return key.startswith("crsr_")


def get_cloud_api_key() -> str:
    """User API key for api.cursor.com (Cloud Agents API)."""
    env_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if _looks_like_cloud_api_key(env_key):
        return env_key

    from app.config import settings

    settings_key = (settings.cursor_api_key or "").strip()
    if _looks_like_cloud_api_key(settings_key):
        return settings_key

    creds = load_credentials()
    stored = str(creds.get("api_key") or "").strip()
    if _looks_like_cloud_api_key(stored):
        return stored
    return ""


def has_cursor_session() -> bool:
    creds = load_credentials()
    return bool(creds.get("access_token") and creds.get("auth_id"))


def get_session_cookie_value() -> str | None:
    creds = load_credentials()
    access = str(creds.get("access_token") or "").strip()
    auth_id = str(creds.get("auth_id") or "").strip()
    if not access or not auth_id:
        return None
    return f"{auth_id}::{access}"


def get_refresh_token() -> str:
    return str(load_credentials().get("refresh_token") or "").strip()

# Backward compatibility for older imports
def get_stored_api_key() -> str:
    return get_cloud_api_key()
