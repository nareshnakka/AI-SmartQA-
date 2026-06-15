"""Push automation assets to Git providers."""

import base64
from typing import Any

import httpx

from app.models.schemas import IntegrationProvider


async def push_files_to_github(
    credentials: dict[str, Any],
    owner: str,
    repo: str,
    branch: str,
    files: list[dict],
    commit_message: str = "QEOS: update automation assets",
) -> dict:
    token = credentials.get("token") or credentials.get("access_token")
    if not token:
        raise ValueError("GitHub token required")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    pushed: list[str] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")
            if not path:
                continue

            sha = None
            check = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                params={"ref": branch},
            )
            if check.status_code == 200:
                sha = check.json().get("sha")

            payload = {
                "message": commit_message,
                "content": base64.b64encode(content.encode()).decode(),
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            resp = await client.put(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                json=payload,
            )
            if resp.status_code in (200, 201):
                pushed.append(path)
            else:
                errors.append(f"{path}: {resp.status_code} {resp.text[:120]}")

    return {
        "provider": IntegrationProvider.GITHUB.value,
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "pushed": pushed,
        "errors": errors,
        "success": len(errors) == 0,
    }
