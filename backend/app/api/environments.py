from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_project
from app.core.security import AuthUser
from app.db.session import get_db
from app.services.audit import AuditService
from app.services.environments import EnvironmentService

router = APIRouter(prefix="/projects/{project_id}/environments", tags=["Environments"])


class CreateEnvironmentRequest(BaseModel):
    name: str
    env_type: str = "dev"
    base_url: str | None = None
    config: dict | None = None
    secrets_hint: str | None = None
    is_default: bool = False


class UpdateEnvironmentRequest(BaseModel):
    name: str | None = None
    env_type: str | None = None
    base_url: str | None = None
    config: dict | None = None
    secrets_hint: str | None = None
    is_default: bool | None = None


@router.get("")
async def list_environments(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_project("viewer")),
):
    svc = EnvironmentService(db)
    return [svc.to_dict(e) for e in await svc.list_environments(project_id)]


@router.post("", status_code=201)
async def create_environment(
    project_id: UUID,
    body: CreateEnvironmentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_project("tester")),
):
    svc = EnvironmentService(db)
    env = await svc.create(
        project_id,
        body.name,
        body.env_type,
        body.base_url,
        body.config,
        body.secrets_hint,
        body.is_default,
    )
    await AuditService(db).log(
        "environment.create",
        user_id=user.id,
        project_id=project_id,
        resource_type="environment",
        resource_id=str(env.id),
        details={"name": body.name, "env_type": body.env_type},
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
    env = await svc.update(env_id, project_id, **body.model_dump(exclude_unset=True))
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
    if not await svc.delete(env_id, project_id):
        raise HTTPException(404, "Environment not found")
    await AuditService(db).log(
        "environment.delete",
        user_id=user.id,
        project_id=project_id,
        resource_type="environment",
        resource_id=str(env_id),
    )
