from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.manager import get_integration_manager
from app.models.schemas import (
    GitRepositoryInfo,
    IntegrationConnectRequest,
    IntegrationProvider,
    IntegrationResponse,
)
from app.services.integration_store import IntegrationStore

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/providers")
async def list_providers():
    manager = get_integration_manager()
    return {"providers": manager.list_providers()}


@router.post("/connect", response_model=IntegrationResponse, status_code=201)
async def connect_integration(body: IntegrationConnectRequest, db: AsyncSession = Depends(get_db)):
    manager = get_integration_manager()
    try:
        response = await manager.connect(
            provider=body.provider,
            project_id=body.project_id,
            credentials=body.credentials,
            config=body.config,
        )
        await IntegrationStore(db).save(response, body.credentials, body.config)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(project_id: UUID | None = None):
    manager = get_integration_manager()
    return manager.list_connected(project_id=project_id)


@router.get("/{integration_id}/repositories", response_model=list[GitRepositoryInfo])
async def list_repositories(integration_id: UUID):
    manager = get_integration_manager()
    try:
        return await manager.list_repositories(integration_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Integration not found")


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: IntegrationProvider,
    client_id: str,
    redirect_uri: str,
    state: str,
    base_url: str | None = None,
):
    manager = get_integration_manager()
    url = manager.get_oauth_url(provider, client_id, redirect_uri, state, base_url=base_url)
    if not url:
        raise HTTPException(status_code=400, detail="OAuth not supported for this provider")
    return {"authorization_url": url}


@router.post("/webhooks/{provider}")
async def handle_webhook(provider: IntegrationProvider, request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event") or \
                 request.headers.get("X-Event-Key") or \
                 request.headers.get("X-Gitlab-Event") or \
                 "unknown"

    manager = get_integration_manager()
    result = await manager.handle_webhook(provider, event_type, payload)

    if result.get("action") == "sync_requirements" and result.get("issue_key"):
        from app.services.generation import GenerationService
        project_id = payload.get("project_id") or result.get("project_id")
        if project_id:
            try:
                issue = payload.get("issue", {})
                fields = issue.get("fields", {})
                content = fields.get("description") or fields.get("summary", "")
                title = fields.get("summary", result["issue_key"])
                gen = GenerationService(db)
                await gen.generate_from_requirement(
                    project_id=__import__("uuid").UUID(str(project_id)),
                    content=str(content),
                    source_type="jira",
                    title=title,
                )
                result["synced"] = True
            except Exception as e:
                result["sync_error"] = str(e)

    if event_type in ("push", "pull_request") and payload.get("repository"):
        result["pipeline_trigger"] = "regression_ready"
        result["suggested_action"] = "POST /api/v1/projects/{id}/pipelines/run"

    return result


class JiraSyncRequest(BaseModel):
    integration_id: UUID
    jql: str = "project = DEMO AND type = Story ORDER BY created DESC"
    project_id: UUID


@router.post("/jira/sync")
async def sync_jira_issues(body: JiraSyncRequest, db: AsyncSession = Depends(get_db)):
    from app.integrations.enterprise import JiraIntegration
    from app.services.integration_store import IntegrationStore
    from app.services.generation import GenerationService

    store = IntegrationStore(db)
    creds = await store.get_credentials(body.integration_id)
    if not creds:
        raise HTTPException(404, "Jira integration not found")
    record, credentials = creds
    if record.provider != "jira":
        raise HTTPException(400, "Integration is not Jira")

    jira = JiraIntegration()
    issues = await jira.search_issues(credentials, body.jql)
    gen = GenerationService(db)
    synced = []
    for issue in issues[:20]:
        fields = issue.get("fields", {})
        summary = fields.get("summary", issue.get("key", "Issue"))
        desc = fields.get("description") or summary
        if isinstance(desc, dict):
            desc = summary
        result = await gen.generate_from_requirement(
            body.project_id,
            content=str(desc),
            source_type="jira",
            title=f"{issue.get('key')}: {summary}",
        )
        synced.append({"issue_key": issue.get("key"), "requirement_id": result["requirement_id"]})

    return {"synced_count": len(synced), "issues": synced}
