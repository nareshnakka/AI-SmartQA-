from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.execution import ExecutionService
from app.services.execution_dashboard import ExecutionDashboardService, export_run_report
from app.services.runner_agent import agent_status

router = APIRouter(prefix="/projects/{project_id}/executions", tags=["Phase 5 — Execution"])


class RunExecutionRequest(BaseModel):
    asset_id: UUID
    mode: str = "live"
    apply_healing: bool = True
    background: bool = True


class BatchRunRequest(BaseModel):
    test_case_ids: list[UUID] = []
    asset_id: UUID | None = None
    performance_asset_id: UUID | None = None
    mode: str = "live"
    apply_healing: bool = False
    background: bool = True
    run_name: str | None = None
    sprint: str | None = None
    release: str | None = None
    base_url: str = "https://example.com"
    run_type: str = "automation"
    framework: str = "playwright"


@router.get("/dashboard")
async def execution_dashboard(
    project_id: UUID,
    sprint: str | None = None,
    release: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = ExecutionDashboardService(db)
    return await svc.dashboard(project_id, sprint, release)


@router.get("/runner-agent")
async def localhost_runner(db: AsyncSession = Depends(get_db)):
    return await agent_status(db)


@router.post("/batch-run")
async def batch_run(project_id: UUID, body: BatchRunRequest, db: AsyncSession = Depends(get_db)):
    svc = ExecutionService(db)
    try:
        run = await svc.start_batch_run(
            project_id,
            body.test_case_ids,
            asset_id=body.asset_id,
            mode=body.mode,
            apply_healing=body.apply_healing,
            background=body.background,
            run_name=body.run_name,
            sprint=body.sprint,
            release=body.release,
            base_url=body.base_url,
            run_type=body.run_type,
            performance_asset_id=body.performance_asset_id,
            framework=body.framework,
        )
        return svc.to_dict(run)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/run")
async def run_execution(project_id: UUID, body: RunExecutionRequest, db: AsyncSession = Depends(get_db)):
    svc = ExecutionService(db)
    try:
        run = await svc.start_automation(
            project_id,
            body.asset_id,
            body.mode,
            body.apply_healing,
            body.background,
        )
        return svc.to_dict(run)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
async def list_executions(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ExecutionService(db)
    runs = await svc.list_runs(project_id)
    return [svc.to_dict(r) for r in runs]


@router.get("/{run_id}/export")
async def export_execution(
    project_id: UUID,
    run_id: UUID,
    format: str = Query("html", alias="format"),
    db: AsyncSession = Depends(get_db),
):
    svc = ExecutionService(db)
    run = await svc.get_run(run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(404)
    content, media_type, filename = export_run_report(svc.to_dict(run), format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{run_id}")
async def get_execution(project_id: UUID, run_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ExecutionService(db)
    run = await svc.get_run(run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(run)


@router.get("/{run_id}/videos/{video_id}")
async def get_execution_video(
    project_id: UUID,
    run_id: UUID,
    video_id: int,
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import FileResponse

    svc = ExecutionService(db)
    run = await svc.get_run(run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(404, "Execution run not found")

    path = svc.resolve_video(project_id, run_id, video_id)
    if not path:
        raise HTTPException(404, "Video not found")

    media_type = "video/mp4" if path.suffix == ".mp4" else "video/webm"
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        headers={"Accept-Ranges": "bytes"},
    )
