"""Cursor Cloud Agents API client (https://cursor.com/docs/cloud-agent/api/endpoints)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

CURSOR_API_BASE = "https://api.cursor.com"
TERMINAL_RUN_STATUSES = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED", "FAILED"})


class CursorAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class CursorCloudClient:
    """Thin async client for Cursor Cloud Agents API v1."""

    def __init__(self, api_key: str, *, timeout_sec: float = 60.0):
        self.api_key = (api_key or "").strip()
        self.timeout_sec = timeout_sec

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def me(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/me")

    async def list_models(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/v1/models")
        items = data.get("items") or data.get("models") or []
        return list(items)

    async def run_prompt_no_repo(
        self,
        prompt_text: str,
        *,
        model: str | None = None,
        poll_interval_sec: float = 2.0,
        max_wait_sec: float = 120.0,
    ) -> str:
        """
        Create a no-repository cloud agent, wait for the run to finish, return assistant text.
        See API: omit repos and env to start a no-repo agent.
        """
        body: dict[str, Any] = {
            "prompt": {"text": prompt_text},
            "name": "QEOS Discovery Advisor",
        }
        if model:
            body["model"] = {"id": model}

        created = await self._request("POST", "/v1/agents", json_body=body)
        agent = created.get("agent") or {}
        run = created.get("run") or {}
        agent_id = agent.get("id") or created.get("agentId")
        run_id = run.get("id") or created.get("runId") or agent.get("latestRunId")
        if not agent_id or not run_id:
            raise CursorAPIError("Cursor API did not return agent/run ids", retryable=False)

        deadline = time.monotonic() + max_wait_sec
        last_status = "UNKNOWN"
        while time.monotonic() < deadline:
            run_data = await self._request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")
            last_status = str(run_data.get("status") or "").upper()
            if last_status in TERMINAL_RUN_STATUSES:
                result = (run_data.get("result") or "").strip()
                if last_status == "FINISHED" and result:
                    return result
                raise CursorAPIError(
                    f"Cursor run ended with status {last_status}: {result or 'no result text'}",
                    retryable=last_status in {"ERROR", "EXPIRED"},
                )
            await asyncio.sleep(poll_interval_sec)

        try:
            await self._request("POST", f"/v1/agents/{agent_id}/runs/{run_id}/cancel")
        except Exception:
            pass
        raise CursorAPIError(
            f"Cursor run timed out after {max_wait_sec}s (last status: {last_status})",
            retryable=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise CursorAPIError("CURSOR_API_KEY is not configured", status_code=401)

        url = f"{CURSOR_API_BASE}{path}"
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.request(method, url, headers=self._headers(), json=json_body)

        if response.status_code == 429:
            raise CursorAPIError("Cursor API rate limit exceeded", status_code=429, retryable=True)
        if response.status_code == 401:
            raise CursorAPIError("Invalid Cursor API key — create one at cursor.com/dashboard/api-keys", status_code=401, retryable=False)
        if response.status_code >= 400:
            detail = response.text[:300]
            raise CursorAPIError(
                f"Cursor API error {response.status_code}: {detail}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )

        if not response.content:
            return {}
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise CursorAPIError(f"Invalid JSON from Cursor API: {exc}") from exc


def get_cursor_client() -> CursorCloudClient | None:
    from app.config import settings
    from app.services.cursor_credential_store import get_cloud_api_key

    key = (get_cloud_api_key() or "").strip()
    if not key:
        return None
    return CursorCloudClient(key, timeout_sec=float(settings.cursor_api_timeout_sec))


async def get_cursor_client_async() -> CursorCloudClient | None:
    from app.config import settings
    from app.services.cursor_credential_store import get_cloud_api_key

    key = (get_cloud_api_key() or "").strip()
    if not key:
        return None
    return CursorCloudClient(key, timeout_sec=float(settings.cursor_api_timeout_sec))
