"""GitHub helpers for QEOS product repo (issues + file uploads)."""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlparse

import httpx

GITHUB_API = "https://api.github.com"
GITHUB_HEADERS_BASE = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from HTTPS or SSH GitHub remotes."""
    url = (remote_url or "").strip()
    if not url:
        return None

    # git@github.com:owner/repo.git
    ssh = re.match(r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
    if ssh:
        return ssh.group(1), ssh.group(2).removesuffix(".git")

    # https://github.com/owner/repo(.git)
    cleaned = url
    if cleaned.startswith("ssh://git@github.com/"):
        cleaned = "https://github.com/" + cleaned[len("ssh://git@github.com/") :]
    if "github.com" not in cleaned.lower():
        return None

    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    parts = [p for p in (parsed.path or "").strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def _headers(token: str) -> dict[str, str]:
    return {
        **GITHUB_HEADERS_BASE,
        "Authorization": f"Bearer {token}",
    }


async def create_github_issue(
    token: str,
    owner: str,
    repo: str,
    *,
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=_headers(token),
            json=payload,
        )

    if response.status_code not in (200, 201):
        raise ValueError(f"GitHub create issue failed ({response.status_code}): {response.text[:300]}")

    data = response.json()
    return {
        "number": data.get("number"),
        "html_url": data.get("html_url"),
        "title": data.get("title"),
        "id": data.get("id"),
    }


async def push_repo_files(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    files: list[dict[str, Any]],
    commit_message: str,
) -> dict[str, Any]:
    """
    Push text or binary files via Contents API.
    Each file: {path, content: str|bytes, encoding?: 'utf-8'|'base64'}
    """
    headers = _headers(token)
    pushed: list[str] = []
    errors: list[str] = []
    urls: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=60.0) as client:
        for item in files:
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            raw = item.get("content", b"")
            if isinstance(raw, str):
                content_b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
            elif isinstance(raw, (bytes, bytearray)):
                content_b64 = base64.b64encode(bytes(raw)).decode("ascii")
            else:
                errors.append(f"{path}: unsupported content type")
                continue

            sha = None
            check = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                params={"ref": branch},
            )
            if check.status_code == 200:
                sha = check.json().get("sha")

            payload: dict[str, Any] = {
                "message": commit_message,
                "content": content_b64,
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            resp = await client.put(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                json=payload,
            )
            if resp.status_code in (200, 201):
                pushed.append(path)
                content_meta = resp.json().get("content") or {}
                if content_meta.get("html_url"):
                    urls[path] = content_meta["html_url"]
            else:
                errors.append(f"{path}: {resp.status_code} {resp.text[:160]}")

    return {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "pushed": pushed,
        "urls": urls,
        "errors": errors,
        "success": len(errors) == 0 and len(pushed) > 0,
    }
