from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.performance import PerformanceService, WORKLOAD_PROFILES

router = APIRouter(prefix="/projects/{project_id}/performance", tags=["Phase 3B — Performance Engineering"])


class GeneratePerformanceRequest(BaseModel):
    tool: str = "k6"
    flow_distribution: dict[str, int] | None = None
    name: str | None = None
    workload_profile: str = "load"
    base_url: str = "https://example.com"
    throughput_config: dict | None = None
    har_content: dict | str | None = None
    openapi_content: dict | str | None = None
    discovery_session_id: UUID | None = None


class UpdateFileRequest(BaseModel):
    path: str
    content: str
    save_version: bool = True


class UpdateScenariosRequest(BaseModel):
    scenarios: list[dict]


class UpdateDataPoolsRequest(BaseModel):
    data_pools: list[dict]


class UpdateWorkloadRequest(BaseModel):
    profile: str
    throughput_config: dict | None = None


class CorrelationSourceRequest(BaseModel):
    source_type: str  # har | openapi
    content: dict | str


class ExecuteRequest(BaseModel):
    workload_profile: str = "smoke"
    agent_id: UUID | None = None
    background: bool = True


class RegisterAgentRequest(BaseModel):
    name: str
    host: str = "localhost"
    agent_type: str = "local"
    max_vus: int = 500


@router.get("/tools")
async def list_tools():
    return {
        "tools": [
            {"id": "k6", "name": "k6", "language": "javascript"},
            {"id": "jmeter", "name": "Apache JMeter", "language": "xml"},
            {"id": "gatling", "name": "Gatling", "language": "scala"},
            {"id": "locust", "name": "Locust", "language": "python"},
        ]
    }


@router.get("/workload-profiles")
async def list_workload_profiles():
    return {
        "profiles": [
            {"id": k, **{kk: vv for kk, vv in v.items() if kk != "stages"}}
            for k, v in WORKLOAD_PROFILES.items()
        ]
    }


@router.post("/generate")
async def generate_performance(
    project_id: UUID, body: GeneratePerformanceRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    try:
        asset = await svc.generate(
            project_id, body.tool, body.flow_distribution, body.name,
            body.workload_profile, body.base_url, body.har_content,
            body.openapi_content, body.throughput_config,
            discovery_session_id=body.discovery_session_id,
        )
        await svc.seed_local_agent(project_id)
        return svc.to_dict(asset)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/assets")
async def list_assets(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PerformanceService(db)
    return [svc.to_dict(a) for a in await svc.list_assets(project_id)]


@router.get("/assets/{asset_id}")
async def get_asset(project_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PerformanceService(db)
    asset = await svc.get_asset(asset_id)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(asset)


@router.put("/assets/{asset_id}")
async def update_asset(
    project_id: UUID, asset_id: UUID, body: dict, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    asset = await svc.update_scripts(
        asset_id, project_id, body.get("scripts"), body.get("name"), body.get("workload_model")
    )
    if not asset:
        raise HTTPException(404)
    return svc.to_dict(asset)


@router.put("/assets/{asset_id}/files")
async def update_file(
    project_id: UUID, asset_id: UUID, body: UpdateFileRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    try:
        asset = await svc.update_file(asset_id, body.path, body.content, body.save_version)
        if asset.project_id != project_id:
            raise HTTPException(404)
        return svc.to_dict(asset)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/assets/{asset_id}/versions")
async def list_versions(project_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PerformanceService(db)
    return [svc.to_dict(v) for v in await svc.list_versions(asset_id) if v.project_id == project_id]


@router.get("/assets/{asset_id}/diff/{other_id}")
async def diff_versions(
    project_id: UUID, asset_id: UUID, other_id: UUID, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    a, b = await svc.get_asset(asset_id), await svc.get_asset(other_id)
    if not a or not b or a.project_id != project_id:
        raise HTTPException(404)
    return {"diffs": svc.diff_scripts(a.scripts or [], b.scripts or [])}


@router.put("/assets/{asset_id}/scenarios")
async def update_scenarios(
    project_id: UUID, asset_id: UUID, body: UpdateScenariosRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    asset = await svc.update_scenario(asset_id, body.scenarios)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(asset)


@router.put("/assets/{asset_id}/data-pools")
async def update_data_pools(
    project_id: UUID, asset_id: UUID, body: UpdateDataPoolsRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    asset = await svc.update_data_pools(asset_id, body.data_pools)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(asset)


@router.put("/assets/{asset_id}/workload")
async def update_workload(
    project_id: UUID, asset_id: UUID, body: UpdateWorkloadRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    asset = await svc.update_workload(asset_id, body.profile, body.throughput_config)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(asset)


@router.post("/assets/{asset_id}/correlation")
async def apply_correlation(
    project_id: UUID, asset_id: UUID, body: CorrelationSourceRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    asset = await svc.apply_correlation_from_source(asset_id, body.source_type, body.content)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(asset)


@router.post("/assets/{asset_id}/execute")
async def execute_load_test(
    project_id: UUID, asset_id: UUID, body: ExecuteRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    try:
        run = await svc.execute(project_id, asset_id, body.workload_profile, body.agent_id, body.background)
        return svc.run_to_dict(run)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/dashboard")
async def performance_dashboard(project_id: UUID, db: AsyncSession = Depends(get_db)):
    from app.services.performance.performance_dashboard import PerformanceDashboardService

    svc = PerformanceDashboardService(db)
    return await svc.overview(project_id)


@router.get("/runs/{run_id}/dashboard")
async def performance_run_dashboard(project_id: UUID, run_id: UUID, db: AsyncSession = Depends(get_db)):
    from app.services.performance.performance_dashboard import PerformanceDashboardService

    svc = PerformanceDashboardService(db)
    detail = await svc.run_detail(project_id, run_id)
    if not detail:
        raise HTTPException(404)
    return detail


@router.get("/runs/{run_id}/export")
async def export_performance_run(
    project_id: UUID,
    run_id: UUID,
    format: str = "html",
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services.performance.performance_dashboard import PerformanceDashboardService
    from app.services.performance.performance_report import export_performance_report

    dash_svc = PerformanceDashboardService(db)
    detail = await dash_svc.run_detail(project_id, run_id)
    if not detail:
        raise HTTPException(404)
    content, media_type, filename = export_performance_report(detail, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs")
async def list_runs(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PerformanceService(db)
    return [svc.run_to_dict(r) for r in await svc.list_runs(project_id)]


@router.get("/runs/{run_id}")
async def get_run(project_id: UUID, run_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PerformanceService(db)
    run = await svc.get_run(run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(404)
    return svc.run_to_dict(run)


@router.get("/agents")
async def list_agents(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PerformanceService(db)
    await svc.seed_local_agent(project_id)
    return [svc.agent_to_dict(a) for a in await svc.list_agents(project_id)]


@router.post("/agents")
async def register_agent(
    project_id: UUID, body: RegisterAgentRequest, db: AsyncSession = Depends(get_db)
):
    svc = PerformanceService(db)
    agent = await svc.register_agent(body.name, body.host, body.agent_type, body.max_vus, project_id)
    return svc.agent_to_dict(agent)


@router.post("/ingest/har")
async def ingest_har(
    project_id: UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    import json
    content = json.loads(await file.read())
    svc = PerformanceService(db)
    asset = await svc.generate(project_id, har_content=content, workload_profile="load", name=f"HAR — {file.filename}")
    return svc.to_dict(asset)


@router.post("/ingest/openapi")
async def ingest_openapi(
    project_id: UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    import json
    raw = await file.read()
    try:
        content = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "OpenAPI must be JSON")
    svc = PerformanceService(db)
    asset = await svc.generate(project_id, openapi_content=content, name=f"OpenAPI — {file.filename}")
    return svc.to_dict(asset)
