"""Environment and secrets profile management."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EnvironmentModel


class EnvironmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_environments(self, project_id: uuid.UUID) -> list[EnvironmentModel]:
        result = await self.db.execute(
            select(EnvironmentModel)
            .where(EnvironmentModel.project_id == project_id)
            .order_by(EnvironmentModel.created_at)
        )
        return list(result.scalars().all())

    async def create(
        self,
        project_id: uuid.UUID,
        name: str,
        env_type: str = "dev",
        base_url: str | None = None,
        config: dict | None = None,
        secrets_hint: str | None = None,
        is_default: bool = False,
    ) -> EnvironmentModel:
        if is_default:
            existing = await self.list_environments(project_id)
            for env in existing:
                env.is_default = False

        env = EnvironmentModel(
            project_id=project_id,
            name=name,
            env_type=env_type,
            base_url=base_url,
            config=config or {},
            secrets_hint=secrets_hint,
            is_default=is_default,
        )
        self.db.add(env)
        await self.db.flush()
        return env

    async def update(
        self,
        env_id: uuid.UUID,
        project_id: uuid.UUID,
        **fields,
    ) -> EnvironmentModel | None:
        env = await self.db.get(EnvironmentModel, env_id)
        if not env or env.project_id != project_id:
            return None
        for key, value in fields.items():
            if value is not None and hasattr(env, key):
                setattr(env, key, value)
        if fields.get("is_default"):
            for other in await self.list_environments(project_id):
                if other.id != env_id:
                    other.is_default = False
        await self.db.flush()
        return env

    async def delete(self, env_id: uuid.UUID, project_id: uuid.UUID) -> bool:
        env = await self.db.get(EnvironmentModel, env_id)
        if not env or env.project_id != project_id:
            return False
        await self.db.delete(env)
        return True

    def to_dict(self, env: EnvironmentModel) -> dict:
        return {
            "id": str(env.id),
            "project_id": str(env.project_id),
            "name": env.name,
            "env_type": env.env_type,
            "base_url": env.base_url,
            "config": env.config,
            "secrets_hint": env.secrets_hint,
            "is_default": env.is_default,
            "created_at": env.created_at.isoformat(),
            "updated_at": env.updated_at.isoformat(),
        }
