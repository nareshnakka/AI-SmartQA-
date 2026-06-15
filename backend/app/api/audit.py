from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_project
from app.core.security import AuthUser, require_roles
from app.db.session import get_db
from app.services.audit import AuditService

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("")
async def list_audit_logs(
    project_id: UUID | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_roles("platform_admin", "engineering_lead", "qa_lead")),
):
    svc = AuditService(db)
    return [svc.to_dict(e) for e in await svc.list_logs(project_id, limit)]
