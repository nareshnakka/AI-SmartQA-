import base64
from typing import Any

import httpx

from app.integrations.base import BaseIntegration
from app.models.schemas import GitRepositoryInfo, IntegrationProvider


class GitHubIntegration(BaseIntegration):
    provider = IntegrationProvider.GITHUB
    name = "GitHub"
    description = "GitHub repositories, Actions, webhooks, and PR integration"

    API_BASE = "https://api.github.com"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        token = credentials.get("token") or credentials.get("access_token")
        if not token:
            return False
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.API_BASE}/user",
                headers=self._headers(token),
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        token = credentials.get("token") or credentials.get("access_token")
        repos: list[GitRepositoryInfo] = []

        async with httpx.AsyncClient() as client:
            page = 1
            while True:
                response = await client.get(
                    f"{self.API_BASE}/user/repos",
                    headers=self._headers(token),
                    params={"per_page": 100, "page": page, "sort": "updated"},
                )
                response.raise_for_status()
                data = response.json()
                if not data:
                    break

                for repo in data:
                    repos.append(GitRepositoryInfo(
                        provider=self.provider,
                        owner=repo["owner"]["login"],
                        name=repo["name"],
                        default_branch=repo.get("default_branch", "main"),
                        url=repo["html_url"],
                        clone_url=repo["clone_url"],
                    ))
                page += 1
                if len(data) < 100:
                    break

        return repos

    async def get_repository_contents(
        self,
        credentials: dict[str, Any],
        owner: str,
        repo: str,
        path: str = "",
    ) -> list[dict]:
        token = credentials.get("token") or credentials.get("access_token")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.API_BASE}/repos/{owner}/{repo}/contents/{path}",
                headers=self._headers(token),
            )
            response.raise_for_status()
            return response.json()

    async def create_workflow_dispatch(
        self,
        credentials: dict[str, Any],
        owner: str,
        repo: str,
        workflow_id: str,
        ref: str = "main",
        inputs: dict | None = None,
    ) -> dict:
        token = credentials.get("token") or credentials.get("access_token")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.API_BASE}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
                headers=self._headers(token),
                json={"ref": ref, "inputs": inputs or {}},
            )
            response.raise_for_status()
            return {"status": "triggered", "workflow_id": workflow_id}

    async def handle_webhook(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = {"provider": self.provider.value, "event": event_type}

        if event_type == "push":
            result["action"] = "sync_tests"
            result["ref"] = payload.get("ref")
            result["repository"] = payload.get("repository", {}).get("full_name")
        elif event_type == "pull_request":
            result["action"] = "run_regression"
            result["pr_number"] = payload.get("number")
        elif event_type == "workflow_run":
            result["action"] = "collect_results"
            result["conclusion"] = payload.get("workflow_run", {}).get("conclusion")

        return result

    def get_oauth_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        scopes = "repo,workflow,read:org"
        return (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect_uri}&scope={scopes}&state={state}"
        )

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


class BitbucketIntegration(BaseIntegration):
    provider = IntegrationProvider.BITBUCKET
    name = "Bitbucket"
    description = "Atlassian Bitbucket Cloud repositories and Pipelines integration"

    API_BASE = "https://api.bitbucket.org/2.0"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        token = credentials.get("access_token") or credentials.get("app_password")
        username = credentials.get("username", "")
        if not token:
            return False

        auth = (username, token) if username and not credentials.get("access_token") else None
        headers = {}
        if credentials.get("access_token"):
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.API_BASE}/user",
                auth=auth,
                headers=headers,
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        token = credentials.get("access_token") or credentials.get("app_password")
        username = credentials.get("username", "")
        repos: list[GitRepositoryInfo] = []

        auth = (username, token) if username and not credentials.get("access_token") else None
        headers = {"Authorization": f"Bearer {token}"} if credentials.get("access_token") else {}

        async with httpx.AsyncClient() as client:
            url = f"{self.API_BASE}/repositories?role=member&pagelen=100"
            while url:
                response = await client.get(url, auth=auth, headers=headers)
                response.raise_for_status()
                data = response.json()

                for repo in data.get("values", []):
                    owner = repo["owner"]["username"]
                    repos.append(GitRepositoryInfo(
                        provider=self.provider,
                        owner=owner,
                        name=repo["name"],
                        default_branch=repo.get("mainbranch", {}).get("name", "main"),
                        url=repo["links"]["html"]["href"],
                        clone_url=next(
                            (l["href"] for l in repo["links"]["clone"] if l["name"] == "https"),
                            "",
                        ),
                    ))
                url = data.get("next")

        return repos

    async def trigger_pipeline(
        self,
        credentials: dict[str, Any],
        workspace: str,
        repo_slug: str,
        branch: str = "main",
    ) -> dict:
        token = credentials.get("access_token") or credentials.get("app_password")
        username = credentials.get("username", "")
        auth = (username, token) if username and not credentials.get("access_token") else None
        headers = {"Authorization": f"Bearer {token}"} if credentials.get("access_token") else {}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.API_BASE}/repositories/{workspace}/{repo_slug}/pipelines/",
                auth=auth,
                headers=headers,
                json={"target": {"ref_type": "branch", "type": "pipeline_ref_target", "ref_name": branch}},
            )
            response.raise_for_status()
            return response.json()

    async def handle_webhook(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = {"provider": self.provider.value, "event": event_type}

        if "repo:push" in event_type or event_type == "push":
            result["action"] = "sync_tests"
            result["repository"] = payload.get("repository", {}).get("full_name")
        elif "pullrequest" in event_type:
            result["action"] = "run_regression"
        elif "pipeline" in event_type:
            result["action"] = "collect_results"

        return result

    def get_oauth_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        return (
            f"https://bitbucket.org/site/oauth2/authorize"
            f"?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&state={state}"
        )


class GitLabIntegration(BaseIntegration):
    provider = IntegrationProvider.GITLAB
    name = "GitLab"
    description = "GitLab repositories and CI/CD pipeline integration"

    def __init__(self, base_url: str = "https://gitlab.com") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        token = credentials.get("access_token") or credentials.get("private_token")
        if not token:
            return False
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/user",
                headers={"PRIVATE-TOKEN": token},
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        token = credentials.get("access_token") or credentials.get("private_token")
        repos: list[GitRepositoryInfo] = []

        async with httpx.AsyncClient() as client:
            page = 1
            while True:
                response = await client.get(
                    f"{self.api_base}/projects",
                    headers={"PRIVATE-TOKEN": token},
                    params={"membership": True, "per_page": 100, "page": page},
                )
                response.raise_for_status()
                data = response.json()
                if not data:
                    break

                for project in data:
                    namespace = project["namespace"]["path"]
                    repos.append(GitRepositoryInfo(
                        provider=self.provider,
                        owner=namespace,
                        name=project["path"],
                        default_branch=project.get("default_branch", "main"),
                        url=project["web_url"],
                        clone_url=project["http_url_to_repo"],
                    ))
                page += 1
                if len(data) < 100:
                    break

        return repos

    async def trigger_pipeline(
        self,
        credentials: dict[str, Any],
        project_id: str,
        ref: str = "main",
    ) -> dict:
        token = credentials.get("access_token") or credentials.get("private_token")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/projects/{project_id}/pipeline",
                headers={"PRIVATE-TOKEN": token},
                json={"ref": ref},
            )
            response.raise_for_status()
            return response.json()

    async def handle_webhook(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = {"provider": self.provider.value, "event": event_type}

        if event_type == "Push Hook":
            result["action"] = "sync_tests"
        elif event_type == "Merge Request Hook":
            result["action"] = "run_regression"
        elif event_type == "Pipeline Hook":
            result["action"] = "collect_results"
            result["status"] = payload.get("object_attributes", {}).get("status")

        return result

    def get_oauth_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        return (
            f"{self.base_url}/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&state={state}"
        )


class GiteaIntegration(BaseIntegration):
    """Gitea and Forgejo (open-source Git hosting) integration."""

    provider = IntegrationProvider.GITEA
    name = "Gitea / Forgejo"
    description = "Self-hosted Gitea and Forgejo Git repositories"

    def __init__(self, base_url: str = "http://localhost:3000") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v1"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        token = credentials.get("access_token")
        if not token:
            return False
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/user",
                headers={"Authorization": f"token {token}"},
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        token = credentials.get("access_token")
        repos: list[GitRepositoryInfo] = []

        async with httpx.AsyncClient() as client:
            page = 1
            while True:
                response = await client.get(
                    f"{self.api_base}/user/repos",
                    headers={"Authorization": f"token {token}"},
                    params={"page": page, "limit": 50},
                )
                response.raise_for_status()
                data = response.json()
                if not data:
                    break

                for repo in data:
                    repos.append(GitRepositoryInfo(
                        provider=IntegrationProvider.GITEA,
                        owner=repo["owner"]["login"],
                        name=repo["name"],
                        default_branch=repo.get("default_branch", "main"),
                        url=repo["html_url"],
                        clone_url=repo["clone_url"],
                    ))
                page += 1
                if len(data) < 50:
                    break

        return repos

    def get_oauth_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        return (
            f"{self.base_url}/login/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&state={state}"
        )


class AzureDevOpsIntegration(BaseIntegration):
    provider = IntegrationProvider.AZURE_DEVOPS
    name = "Azure DevOps"
    description = "Azure Repos and Pipelines integration"

    async def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        pat = credentials.get("personal_access_token")
        org = credentials.get("organization")
        if not pat or not org:
            return False
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://dev.azure.com/{org}/_apis/projects?api-version=7.0",
                auth=("", pat),
            )
            return response.status_code == 200

    async def list_repositories(self, credentials: dict[str, Any]) -> list[GitRepositoryInfo]:
        pat = credentials.get("personal_access_token")
        org = credentials.get("organization")
        project = credentials.get("project", "")
        repos: list[GitRepositoryInfo] = []

        async with httpx.AsyncClient() as client:
            url = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories?api-version=7.0"
            response = await client.get(url, auth=("", pat))
            response.raise_for_status()

            for repo in response.json().get("value", []):
                repos.append(GitRepositoryInfo(
                    provider=self.provider,
                    owner=org,
                    name=repo["name"],
                    default_branch=repo.get("defaultBranch", "refs/heads/main").replace("refs/heads/", ""),
                    url=repo.get("webUrl", ""),
                    clone_url=repo.get("remoteUrl", ""),
                ))

        return repos

    async def trigger_pipeline(
        self,
        credentials: dict[str, Any],
        pipeline_id: int,
        branch: str = "main",
    ) -> dict:
        pat = credentials.get("personal_access_token")
        org = credentials.get("organization")
        project = credentials.get("project")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://dev.azure.com/{org}/{project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.0",
                auth=("", pat),
                json={"resources": {"repositories": {"self": {"refName": f"refs/heads/{branch}"}}}},
            )
            response.raise_for_status()
            return response.json()

    def get_oauth_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        return (
            f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            f"?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&state={state}"
            f"&scope=499b84ac-1321-427f-aa17-267ca6975798/.default offline_access"
        )
