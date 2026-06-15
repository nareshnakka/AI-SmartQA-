from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.core.rbac import check_project_access
from app.core.security import AuthUser, get_request_user
from app.db.session import get_db
from app.models.schemas import AgentRunRequest, AgentRunResponse, AgentType
from app.services.agent_runs import AgentRunService

router = APIRouter(prefix="/agents", tags=["AI Agents"])


@router.get("")
async def list_agents():
    orchestrator = get_orchestrator()
    return {"agents": orchestrator.list_agents()}


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    body: AgentRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_request_user(request)
    await check_project_access(db, user, body.project_id, "tester")
    orchestrator = get_orchestrator()
    return await orchestrator.run_agent(
        agent_type=body.agent_type,
        project_id=body.project_id,
        input_data=body.input_data,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
    )


@router.post("/pipeline", response_model=list[AgentRunResponse])
async def run_pipeline(
    project_id: UUID,
    pipeline: list[AgentType],
    input_data: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    llm_provider: str | None = None,
    llm_model: str | None = None,
):
    user = get_request_user(request)
    await check_project_access(db, user, project_id, "tester")
    orchestrator = get_orchestrator()
    return await orchestrator.run_pipeline(
        project_id=project_id,
        pipeline=pipeline,
        initial_input=input_data,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = AgentRunService(db)
    model = await svc.get_run(run_id)
    if model:
        return svc.to_response(model)
    orchestrator = get_orchestrator()
    run = orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_agent_runs(
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentRunService(db)
    db_runs = await svc.list_runs(project_id)
    if db_runs:
        return [svc.to_response(r) for r in db_runs]
    orchestrator = get_orchestrator()
    return orchestrator.list_runs(project_id=project_id)
