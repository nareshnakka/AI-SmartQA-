"""Persistent integration storage + manager hydration."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IntegrationModel
from app.integrations.base import IntegrationConfig
from app.models.schemas import IntegrationProvider, IntegrationResponse


async def hydrate_integration_manager() -> int:
    """Load persisted integrations into the in-memory manager on startup."""
    from app.db.session import AsyncSessionLocal
    from app.integrations.manager import get_integration_manager

    async with AsyncSessionLocal() as db:
        store = IntegrationStore(db)
        configs = await store.load_all()

    manager = get_integration_manager()
    manager.hydrate(configs)
    return len(configs)


class IntegrationStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save(
        self,
        response: IntegrationResponse,
        credentials: dict,
        config: dict | None = None,
    ) -> IntegrationModel:
        existing = await self.db.get(IntegrationModel, response.id)
        if existing:
            existing.credentials = credentials
            existing.config = config or {}
            existing.status = response.status
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing

        row = IntegrationModel(
            id=response.id,
            project_id=response.project_id,
            provider=response.provider.value,
            credentials=credentials,
            config=config or {},
            status=response.status,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def load_all(self) -> list[IntegrationConfig]:
        result = await self.db.execute(select(IntegrationModel))
        configs: list[IntegrationConfig] = []
        for row in result.scalars().all():
            configs.append(
                IntegrationConfig(
                    id=row.id,
                    provider=IntegrationProvider(row.provider),
                    project_id=row.project_id,
                    credentials=row.credentials or {},
                    config=row.config or {},
                    status=row.status,
                )
            )
        return configs

    async def list_for_project(self, project_id: uuid.UUID) -> list[IntegrationResponse]:
        result = await self.db.execute(
            select(IntegrationModel)
            .where(IntegrationModel.project_id == project_id)
            .order_by(IntegrationModel.created_at.desc())
        )
        return [
            IntegrationResponse(
                id=r.id,
                provider=IntegrationProvider(r.provider),
                project_id=r.project_id,
                status=r.status,
                config={k: v for k, v in (r.config or {}).items()},
                created_at=r.created_at,
            )
            for r in result.scalars().all()
        ]

    async def get_credentials(self, integration_id: uuid.UUID) -> tuple[IntegrationModel, dict] | None:
        row = await self.db.get(IntegrationModel, integration_id)
        if not row:
            return None
        return row, row.credentials or {}
