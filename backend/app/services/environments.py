"""Environment and secrets profile management."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EnvironmentModel, TestCaseModel


def slug_from_name(name: str) -> str:
    """Optional short tag derived from name (used in metadata, not shown as fixed enum)."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip()).strip("_").lower()
    return cleaned[:30] if cleaned else "custom"


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

    async def get_environment(self, env_id: uuid.UUID) -> EnvironmentModel | None:
        return await self.db.get(EnvironmentModel, env_id)

    async def get_default_environment(self, project_id: uuid.UUID) -> EnvironmentModel | None:
        envs = await self.list_environments(project_id)
        for env in envs:
            if env.is_default:
                return env
        return envs[0] if envs else None

    async def create(
        self,
        project_id: uuid.UUID,
        name: str,
        env_type: str | None = None,
        base_url: str | None = None,
        config: dict | None = None,
        secrets_hint: str | None = None,
        is_default: bool = False,
    ) -> EnvironmentModel:
        name = (name or "").strip()
        if not name:
            raise ValueError("Environment name is required")

        existing = await self.db.execute(
            select(EnvironmentModel).where(
                EnvironmentModel.project_id == project_id,
                EnvironmentModel.name.ilike(name),
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Environment '{name}' already exists")

        envs = await self.list_environments(project_id)
        if is_default or not envs:
            is_default = True
            for env in envs:
                env.is_default = False

        env = EnvironmentModel(
            project_id=project_id,
            name=name,
            env_type=env_type or slug_from_name(name),
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

        if fields.get("name") is not None:
            new_name = str(fields["name"]).strip()
            if not new_name:
                raise ValueError("Environment name cannot be empty")
            dup = await self.db.execute(
                select(EnvironmentModel).where(
                    EnvironmentModel.project_id == project_id,
                    EnvironmentModel.name.ilike(new_name),
                    EnvironmentModel.id != env_id,
                )
            )
            if dup.scalars().first():
                raise ValueError(f"Environment '{new_name}' already exists")
            fields["name"] = new_name
            if "env_type" not in fields or fields.get("env_type") is None:
                fields["env_type"] = slug_from_name(new_name)

        for key, value in fields.items():
            if key in fields and hasattr(env, key):
                if key in ("base_url", "secrets_hint") and value == "":
                    setattr(env, key, None)
                elif value is not None:
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

        cases = await self.db.execute(
            select(TestCaseModel).where(
                TestCaseModel.project_id == project_id,
                TestCaseModel.environment_id == env_id,
            )
        )
        if cases.scalars().first():
            raise ValueError("Cannot delete environment with test cases — delete cases first")

        was_default = env.is_default
        await self.db.delete(env)
        await self.db.flush()

        if was_default:
            remaining = await self.list_environments(project_id)
            if remaining:
                remaining[0].is_default = True
                await self.db.flush()
        return True

    def to_dict(self, env: EnvironmentModel, *, test_case_count: int = 0) -> dict:
        return {
            "id": str(env.id),
            "project_id": str(env.project_id),
            "name": env.name,
            "env_type": env.env_type,
            "base_url": env.base_url,
            "config": env.config,
            "secrets_hint": env.secrets_hint,
            "is_default": env.is_default,
            "test_case_count": test_case_count,
            "created_at": env.created_at.isoformat(),
            "updated_at": env.updated_at.isoformat(),
        }
