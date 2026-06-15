from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.pipeline import PipelineService

router = APIRouter(prefix="/projects/{project_id}/pipelines", tags=["Phase 4 — Pipelines"])


class RunPipelineRequest(BaseModel):
    pipeline_key: str
    content: str = ""
    source_type: str = "user_story"
    framework: str = "playwright"
    tool: str = "k6"


@router.get("/templates")
async def list_templates():
    return {"templates": PipelineService.list_templates()}


@router.post("/run")
async def run_pipeline(
    project_id: UUID, body: RunPipelineRequest, db: AsyncSession = Depends(get_db)
):
    svc = PipelineService(db)
    try:
        run = await svc.run_pipeline(
            project_id,
            body.pipeline_key,
            {
                "content": body.content,
                "source_type": body.source_type,
                "framework": body.framework,
                "tool": body.tool,
            },
        )
        return {
            "id": str(run.id),
            "name": run.name,
            "status": run.status,
            "pipeline": run.pipeline,
            "steps": run.steps,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/runs")
async def list_runs(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    runs = await svc.list_runs(project_id)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "status": r.status,
            "pipeline": r.pipeline,
            "steps": r.steps,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(project_id: UUID, run_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PipelineService(db)
    run = await svc.get_run(run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(404)
    return {
        "id": str(run.id),
        "name": run.name,
        "status": run.status,
        "pipeline": run.pipeline,
        "steps": run.steps,
        "input_data": run.input_data,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
