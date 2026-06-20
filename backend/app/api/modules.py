from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProjectModuleModel, TestCaseModel
from app.db.session import get_db
from app.services.modules import ModuleService

router = APIRouter(prefix="/projects/{project_id}/modules", tags=["Modules"])


class ModuleCreate(BaseModel):
    name: str
    environment_id: UUID
    description: str | None = None
    code: str | None = None


class ModuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


async def _module_counts(
    db: AsyncSession,
    project_id: UUID,
    environment_id: UUID | None = None,
) -> dict[str, int]:
    count_query = (
        select(TestCaseModel.module_id, func.count(TestCaseModel.id))
        .where(
            TestCaseModel.project_id == project_id,
            TestCaseModel.module_id.isnot(None),
        )
    )
    if environment_id:
        count_query = count_query.where(TestCaseModel.environment_id == environment_id)
    count_query = count_query.group_by(TestCaseModel.module_id)
    result = await db.execute(count_query)
    return {str(mid): int(cnt) for mid, cnt in result.all()}


@router.get("")
async def list_modules(
    project_id: UUID,
    environment_id: UUID = Query(..., description="Environment scope (required)"),
    db: AsyncSession = Depends(get_db),
):
    svc = ModuleService(db)
    modules = await svc.list_modules(project_id, environment_id)
    counts = await _module_counts(db, project_id, environment_id)
    return [svc.to_dict(m, test_case_count=counts.get(str(m.id), 0)) for m in modules]


@router.post("", status_code=201)
async def create_module(project_id: UUID, body: ModuleCreate, db: AsyncSession = Depends(get_db)):
    svc = ModuleService(db)
    try:
        mod = await svc.create_module(
            project_id, body.environment_id, body.name, body.description, body.code
        )
        return svc.to_dict(mod)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/{module_id}")
async def update_module(
    project_id: UUID, module_id: UUID, body: ModuleUpdate, db: AsyncSession = Depends(get_db)
):
    svc = ModuleService(db)
    try:
        mod = await svc.update_module(project_id, module_id, body.name, body.description)
        return svc.to_dict(mod)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/{module_id}")
async def delete_module(project_id: UUID, module_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ModuleService(db)
    try:
        await svc.delete_module(project_id, module_id)
        return {"deleted": True}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
