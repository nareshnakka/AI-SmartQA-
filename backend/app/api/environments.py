from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_project
from app.core.security import AuthUser
from app.db.models import TestCaseModel
from app.db.session import get_db
from app.services.audit import AuditService
from app.services.environments import EnvironmentService
from app.services.modules import ModuleService, ensure_default_modules

router = APIRouter(prefix="/projects/{project_id}/environments", tags=["Environments"])


class CreateEnvironmentRequest(BaseModel):
    name: str
    base_url: str | None = None
    config: dict | None = None
    secrets_hint: str | None = None
    is_default: bool = False


class UpdateEnvironmentRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    config: dict | None = None
    secrets_hint: str | None = None
    is_default: bool | None = None


async def _env_counts(db: AsyncSession, project_id: UUID) -> dict[str, int]:
    result = await db.execute(
        select(TestCaseModel.environment_id, func.count(TestCaseModel.id))
        .where(TestCaseModel.project_id == project_id, TestCaseModel.environment_id.isnot(None))
        .group_by(TestCaseModel.environment_id)
    )
    return {str(eid): int(cnt) for eid, cnt in result.all()}


@router.get("")
async def list_environments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_project("viewer")),
):
    svc = EnvironmentService(db)
    counts = await _env_counts(db, project_id)
    return [svc.to_dict(e, test_case_count=counts.get(str(e.id), 0)) for e in await svc.list_environments(project_id)]


@router.get("/hierarchy")
async def workspace_hierarchy(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_project("viewer")),
):
    """Project → Environment → Module tree (all names user-configured)."""
    env_svc = EnvironmentService(db)
    mod_svc = ModuleService(db)
    environments = await env_svc.list_environments(project_id)

    tree = []
    for env in environments:
        await ensure_default_modules(db, project_id, env.id)
        modules = await mod_svc.list_modules(project_id, env.id)
        mod_counts = {}
        result = await db.execute(
            select(TestCaseModel.module_id, func.count(TestCaseModel.id))
            .where(
                TestCaseModel.project_id == project_id,
                TestCaseModel.environment_id == env.id,
                TestCaseModel.module_id.isnot(None),
            )
            .group_by(TestCaseModel.module_id)
        )
        for mid, cnt in result.all():
            mod_counts[str(mid)] = int(cnt)
        tree.append({
            **env_svc.to_dict(env, test_case_count=await _env_case_count(db, project_id, env.id)),
            "modules": [
                mod_svc.to_dict(m, test_case_count=mod_counts.get(str(m.id), 0)) for m in modules
            ],
        })
    return {"project_id": str(project_id), "environments": tree}


async def _env_case_count(db: AsyncSession, project_id: UUID, env_id: UUID) -> int:
    result = await db.execute(
        select(func.count(TestCaseModel.id)).where(
            TestCaseModel.project_id == project_id,
            TestCaseModel.environment_id == env_id,
        )
    )
    return int(result.scalar() or 0)


@router.post("", status_code=201)
async def create_environment(
    project_id: UUID,
    body: CreateEnvironmentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_project("tester")),
):
    svc = EnvironmentService(db)
    try:
        env = await svc.create(
            project_id,
            body.name,
            base_url=body.base_url,
            config=body.config,
            secrets_hint=body.secrets_hint,
            is_default=body.is_default,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await ensure_default_modules(db, project_id, env.id)
    await AuditService(db).log(
        "environment.create",
        user_id=user.id,
        project_id=project_id,
        resource_type="environment",
        resource_id=str(env.id),
        details={"name": body.name},
    )
    return svc.to_dict(env)


@router.patch("/{env_id}")
async def update_environment(
    project_id: UUID,
    env_id: UUID,
    body: UpdateEnvironmentRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_project("tester")),
):
    svc = EnvironmentService(db)
    try:
        env = await svc.update(env_id, project_id, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not env:
        raise HTTPException(404, "Environment not found")
    await AuditService(db).log(
        "environment.update",
        user_id=user.id,
        project_id=project_id,
        resource_type="environment",
        resource_id=str(env_id),
    )
    return svc.to_dict(env)


@router.delete("/{env_id}", status_code=204)
async def delete_environment(
    project_id: UUID,
    env_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_project("qa_lead")),
):
    svc = EnvironmentService(db)
    try:
        if not await svc.delete(env_id, project_id):
            raise HTTPException(404, "Environment not found")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await AuditService(db).log(
        "environment.delete",
        user_id=user.id,
        project_id=project_id,
        resource_type="environment",
        resource_id=str(env_id),
    )
