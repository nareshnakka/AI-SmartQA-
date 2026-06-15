"""Quality Studio API — unified one-stop QA hub."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.services.quality_studio import QualityStudioService

router = APIRouter(prefix="/projects/{project_id}/quality-studio", tags=["Quality Studio"])


class GenerateFunctionalRequest(BaseModel):
    input_type: str = "prompt"
    content: str | dict | list
    title: str | None = None
    llm_provider: str | None = None
    persist: bool = True


class GenerateAutomationRequest(BaseModel):
    input_type: str = "prompt"
    content: str | dict | list
    framework: str = "playwright"
    name: str | None = None
    base_url: str = ""
    llm_provider: str | None = None
    discovery_session_id: UUID | None = None


class GeneratePerformanceRequest(BaseModel):
    input_type: str = "prompt"
    content: str | dict | list = ""
    tool: str = "k6"
    workload_profile: str = "load"
    base_url: str = "https://example.com"
    name: str | None = None
    llm_provider: str | None = None
    nfr_document_id: UUID | None = None
    discovery_session_id: UUID | None = None


class CreateSprintRequest(BaseModel):
    name: str
    goal: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    test_case_ids: list[str] = Field(default_factory=list)


class UpdateSprintRequest(BaseModel):
    name: str | None = None
    goal: str | None = None
    status: str | None = None
    test_case_ids: list[str] | None = None


class CreateReleaseRequest(BaseModel):
    name: str
    version: str = "1.0.0"
    target_date: str | None = None
    sprint_ids: list[str] = Field(default_factory=list)
    test_case_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class CreateNfrRequest(BaseModel):
    title: str
    content: str
    source_type: str = "mixed"


class ExecuteSprintRequest(BaseModel):
    sprint_id: UUID
    framework: str = "playwright"
    base_url: str = "https://example.com"
    mode: str = "live"


@router.get("/overview")
async def studio_overview(project_id: UUID, db: AsyncSession = Depends(get_db)):
    return await QualityStudioService(db).overview(project_id)


@router.get("/llm-providers")
async def list_llm_providers():
    from app.llm.router import get_llm_router
    return {
        "default": settings.default_llm_provider,
        "providers": get_llm_router().list_providers(),
    }


@router.post("/functional/generate")
async def generate_functional(
    project_id: UUID, body: GenerateFunctionalRequest, db: AsyncSession = Depends(get_db)
):
    svc = QualityStudioService(db)
    try:
        return await svc.generate_functional(
            project_id, body.input_type, body.content, body.title, body.llm_provider, body.persist
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/automation/generate")
async def generate_automation_standalone(
    project_id: UUID, body: GenerateAutomationRequest, db: AsyncSession = Depends(get_db)
):
    svc = QualityStudioService(db)
    try:
        return await svc.generate_automation_standalone(
            project_id,
            body.input_type,
            body.content,
            body.framework,
            body.name,
            body.base_url,
            body.llm_provider,
            body.discovery_session_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/performance/generate")
async def generate_performance_standalone(
    project_id: UUID, body: GeneratePerformanceRequest, db: AsyncSession = Depends(get_db)
):
    svc = QualityStudioService(db)
    try:
        return await svc.generate_performance_standalone(
            project_id,
            body.input_type,
            body.content or "",
            body.tool,
            body.workload_profile,
            body.base_url,
            body.name,
            body.llm_provider,
            body.nfr_document_id,
            body.discovery_session_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/sprints")
async def list_sprints(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    return [svc.sprint_dict(s) for s in await svc.list_sprints(project_id)]


@router.post("/sprints")
async def create_sprint(project_id: UUID, body: CreateSprintRequest, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    sprint = await svc.create_sprint(
        project_id, body.name, body.goal, body.start_date, body.end_date, body.test_case_ids
    )
    return svc.sprint_dict(sprint)


@router.patch("/sprints/{sprint_id}")
async def update_sprint(
    project_id: UUID, sprint_id: UUID, body: UpdateSprintRequest, db: AsyncSession = Depends(get_db)
):
    svc = QualityStudioService(db)
    sprint = await svc.update_sprint(sprint_id, **body.model_dump(exclude_unset=True))
    if not sprint or sprint.project_id != project_id:
        raise HTTPException(404, "Sprint not found")
    return svc.sprint_dict(sprint)


@router.get("/releases")
async def list_releases(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    return [svc.release_dict(r) for r in await svc.list_releases(project_id)]


@router.post("/releases")
async def create_release(project_id: UUID, body: CreateReleaseRequest, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    release = await svc.create_release(
        project_id, body.name, body.version, body.target_date, body.sprint_ids, body.test_case_ids, body.notes
    )
    return svc.release_dict(release)


@router.get("/nfr")
async def list_nfr(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    return [svc.nfr_dict(n) for n in await svc.list_nfr_documents(project_id)]


@router.post("/nfr")
async def create_nfr(project_id: UUID, body: CreateNfrRequest, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    doc = await svc.create_nfr_document(project_id, body.title, body.content, body.source_type)
    return svc.nfr_dict(doc)


@router.post("/sprints/execute")
async def execute_sprint(project_id: UUID, body: ExecuteSprintRequest, db: AsyncSession = Depends(get_db)):
    svc = QualityStudioService(db)
    try:
        return await svc.execute_sprint(
            project_id, body.sprint_id, body.framework, body.base_url, body.mode
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
