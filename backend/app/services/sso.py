"""OIDC SSO helpers."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from jose import jwt

from app.config import settings

# Short-lived SSO state tokens (in-memory; use Redis in production)
_SSO_STATES: dict[str, datetime] = {}


def sso_configured() -> bool:
    return bool(
        settings.qeos_sso_enabled
        and settings.qeos_sso_issuer_url
        and settings.qeos_sso_client_id
        and settings.qeos_sso_client_secret
    )


def build_sso_authorize_url() -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    _SSO_STATES[state] = datetime.now(timezone.utc) + timedelta(minutes=10)

    issuer = settings.qeos_sso_issuer_url.rstrip("/")
    params = {
        "client_id": settings.qeos_sso_client_id,
        "response_type": "code",
        "scope": settings.qeos_sso_scopes,
        "redirect_uri": settings.qeos_sso_redirect_uri,
        "state": state,
    }
    url = f"{issuer}/authorize?{urlencode(params)}"
    return url, state


def validate_sso_state(state: str) -> bool:
    expires = _SSO_STATES.pop(state, None)
    if not expires:
        return False
    return datetime.now(timezone.utc) <= expires


async def exchange_oidc_code(code: str) -> dict:
    issuer = settings.qeos_sso_issuer_url.rstrip("/")
    token_url = f"{issuer}/token"

    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.qeos_sso_redirect_uri,
                "client_id": settings.qeos_sso_client_id,
                "client_secret": settings.qeos_sso_client_secret,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        access_token = tokens.get("access_token")
        if not access_token:
            raise ValueError("No access_token in OIDC response")

        userinfo = _decode_id_token_user(tokens.get("id_token"))
        if not userinfo:
            userinfo_resp = await client.get(
                f"{issuer}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

        email = userinfo.get("email") or userinfo.get("preferred_username") or userinfo.get("upn")
        if not email:
            raise ValueError("OIDC userinfo missing email")

        return {
            "email": email,
            "name": userinfo.get("name") or userinfo.get("given_name") or email.split("@")[0],
            "external_id": userinfo.get("sub") or str(uuid.uuid4()),
        }


def _decode_id_token_user(id_token: str | None) -> dict | None:
    if not id_token:
        return None
    try:
        return jwt.get_unverified_claims(id_token)
    except Exception:
        return None
