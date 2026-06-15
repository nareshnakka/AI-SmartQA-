"""Project-scoped RBAC helpers."""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import AuthUser, get_request_user
from app.db.models import ProjectMemberModel, ProjectModel
from app.db.session import get_db

ROLE_HIERARCHY = {
    "viewer": 0,
    "tester": 1,
    "qa_lead": 2,
    "engineering_lead": 3,
    "platform_admin": 4,
}

MUTATION_ROLES = {"tester", "qa_lead", "engineering_lead", "platform_admin"}
ADMIN_ROLES = {"platform_admin", "engineering_lead"}


async def check_project_access(
    db: AsyncSession,
    user: AuthUser,
    project_id: uuid.UUID,
    min_role: str = "viewer",
) -> str:
    """Return effective role for user on project. Raises 403/404 if denied."""
    if user.role == "platform_admin":
        return "platform_admin"

    project = await db.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.tenant_id and user.id != uuid.UUID("00000000-0000-0000-0000-000000000001"):
        # Tenant isolation when tenant_id is set on project
        pass  # Future: match user.tenant_id

    result = await db.execute(
        select(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.user_id == user.id,
        )
    )
    member = result.scalar_one_or_none()
    effective = member.role if member else user.role

    if ROLE_HIERARCHY.get(effective, 0) < ROLE_HIERARCHY.get(min_role, 0):
        raise HTTPException(status_code=403, detail="Insufficient project permissions")
    return effective


def require_project(min_role: str = "viewer"):
    async def dependency(
        project_id: uuid.UUID,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> AuthUser:
        user = get_request_user(request)
        if settings.qeos_auth_enabled:
            await check_project_access(db, user, project_id, min_role)
        return user

    return dependency


def require_mutation():
    async def dependency(request: Request) -> AuthUser:
        user = get_request_user(request)
        if settings.qeos_auth_enabled and user.role not in MUTATION_ROLES:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency
