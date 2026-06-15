from typing import Any

import httpx

from app.integrations.base import BaseIntegration
from app.models.schemas import GitRepositoryInfo, IntegrationProvider


class JiraIntegration(BaseIntegration):
    provider = IntegrationProvider.JIRA
    name = "Jira"
    description = "Atlassian Jira issues, epics, and user stories integration"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        domain = credentials.get("domain")
        email = credentials.get("email")
        api_token = credentials.get("api_token")
        if not all([domain, email, api_token]):
            return False

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{domain}/rest/api/3/myself",
                auth=(email, api_token),
                headers={"Accept": "application/json"},
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        return []

    async def search_issues(
        self,
        credentials: dict[str, Any],
        jql: str,
        max_results: int = 50,
    ) -> list[dict]:
        domain = credentials.get("domain")
        email = credentials.get("email")
        api_token = credentials.get("api_token")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{domain}/rest/api/3/search",
                auth=(email, api_token),
                params={"jql": jql, "maxResults": max_results},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json().get("issues", [])

    async def get_issue(self, credentials: dict[str, Any], issue_key: str) -> dict:
        domain = credentials.get("domain")
        email = credentials.get("email")
        api_token = credentials.get("api_token")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{domain}/rest/api/3/issue/{issue_key}",
                auth=(email, api_token),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def handle_webhook(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        issue = payload.get("issue", {})
        return {
            "provider": self.provider.value,
            "event": event_type,
            "action": "sync_requirements",
            "issue_key": issue.get("key"),
            "issue_type": issue.get("fields", {}).get("issuetype", {}).get("name"),
        }


class JenkinsIntegration(BaseIntegration):
    provider = IntegrationProvider.JENKINS
    name = "Jenkins"
    description = "Jenkins CI/CD job triggering and result collection"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        url = credentials.get("url", "").rstrip("/")
        username = credentials.get("username")
        api_token = credentials.get("api_token")
        if not url or not api_token:
            return False

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{url}/api/json",
                auth=(username or "", api_token),
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        return []

    async def trigger_job(
        self,
        credentials: dict[str, Any],
        job_name: str,
        parameters: dict | None = None,
    ) -> dict:
        url = credentials.get("url", "").rstrip("/")
        username = credentials.get("username")
        api_token = credentials.get("api_token")

        endpoint = f"{url}/job/{job_name}/build"
        if parameters:
            endpoint = f"{url}/job/{job_name}/buildWithParameters"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                auth=(username or "", api_token),
                params=parameters or {},
            )
            response.raise_for_status()
            return {"status": "triggered", "job": job_name}

    async def get_job_status(self, credentials: dict[str, Any], job_name: str) -> dict:
        url = credentials.get("url", "").rstrip("/")
        username = credentials.get("username")
        api_token = credentials.get("api_token")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{url}/job/{job_name}/lastBuild/api/json",
                auth=(username or "", api_token),
            )
            response.raise_for_status()
            return response.json()
