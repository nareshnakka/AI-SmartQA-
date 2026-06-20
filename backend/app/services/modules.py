"""Project module management — scoped under Project → Environment → Module."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EnvironmentModel, ProjectModuleModel, TestCaseModel
from app.services.naming_patterns import name_prefix


class ModuleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _ensure_environment(self, project_id: uuid.UUID, environment_id: uuid.UUID) -> EnvironmentModel:
        env = await self.db.get(EnvironmentModel, environment_id)
        if not env or env.project_id != project_id:
            raise ValueError("Environment not found")
        return env

    async def list_modules(
        self,
        project_id: uuid.UUID,
        environment_id: uuid.UUID | None = None,
    ) -> list[ProjectModuleModel]:
        query = (
            select(ProjectModuleModel)
            .where(ProjectModuleModel.project_id == project_id)
            .order_by(ProjectModuleModel.name.asc())
        )
        if environment_id is not None:
            query = query.where(ProjectModuleModel.environment_id == environment_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_module(self, module_id: uuid.UUID) -> ProjectModuleModel | None:
        return await self.db.get(ProjectModuleModel, module_id)

    async def create_module(
        self,
        project_id: uuid.UUID,
        environment_id: uuid.UUID,
        name: str,
        description: str | None = None,
        code: str | None = None,
    ) -> ProjectModuleModel:
        await self._ensure_environment(project_id, environment_id)
        name = (name or "").strip()
        if not name:
            raise ValueError("Module name is required")

        existing = await self.db.execute(
            select(ProjectModuleModel).where(
                ProjectModuleModel.project_id == project_id,
                ProjectModuleModel.environment_id == environment_id,
                ProjectModuleModel.name.ilike(name),
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Module '{name}' already exists in this environment")

        mod = ProjectModuleModel(
            project_id=project_id,
            environment_id=environment_id,
            name=name,
            code=code or name_prefix(name),
            description=description or "",
        )
        self.db.add(mod)
        await self.db.flush()
        return mod

    async def get_or_create_module(
        self,
        project_id: uuid.UUID,
        environment_id: uuid.UUID,
        name: str,
    ) -> ProjectModuleModel:
        await self._ensure_environment(project_id, environment_id)
        name = (name or "General").strip() or "General"
        result = await self.db.execute(
            select(ProjectModuleModel).where(
                ProjectModuleModel.project_id == project_id,
                ProjectModuleModel.environment_id == environment_id,
                ProjectModuleModel.name.ilike(name),
            )
        )
        mod = result.scalar_one_or_none()
        if mod:
            return mod
        return await self.create_module(project_id, environment_id, name)

    async def update_module(
        self,
        project_id: uuid.UUID,
        module_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectModuleModel:
        mod = await self.get_module(module_id)
        if not mod or mod.project_id != project_id:
            raise ValueError("Module not found")
        if name is not None:
            mod.name = name.strip()
            mod.code = name_prefix(mod.name)
        if description is not None:
            mod.description = description
        await self.db.flush()
        return mod

    async def delete_module(self, project_id: uuid.UUID, module_id: uuid.UUID) -> None:
        mod = await self.get_module(module_id)
        if not mod or mod.project_id != project_id:
            raise ValueError("Module not found")

        cases = await self.db.execute(
            select(TestCaseModel).where(
                TestCaseModel.project_id == project_id,
                TestCaseModel.module_id == module_id,
                TestCaseModel.environment_id == mod.environment_id,
            )
        )
        if cases.scalars().first():
            raise ValueError("Cannot delete module with test cases — move or delete cases first")

        await self.db.delete(mod)
        await self.db.flush()

    def to_dict(self, mod: ProjectModuleModel, *, test_case_count: int = 0) -> dict:
        return {
            "id": str(mod.id),
            "project_id": str(mod.project_id),
            "environment_id": str(mod.environment_id) if mod.environment_id else None,
            "name": mod.name,
            "code": mod.code,
            "description": mod.description or "",
            "test_case_count": test_case_count,
            "created_at": mod.created_at.isoformat(),
        }


async def backfill_module_environments(db: AsyncSession) -> None:
    """Assign legacy project-level modules to each project's default environment."""
    from app.services.environments import EnvironmentService

    result = await db.execute(
        select(ProjectModuleModel).where(ProjectModuleModel.environment_id.is_(None))
    )
    modules = list(result.scalars().all())
    if not modules:
        return

    env_svc = EnvironmentService(db)
    by_project: dict[uuid.UUID, list[ProjectModuleModel]] = {}
    for mod in modules:
        by_project.setdefault(mod.project_id, []).append(mod)

    for project_id, project_modules in by_project.items():
        envs = await env_svc.list_environments(project_id)
        default = await env_svc.get_default_environment(project_id)
        if not default:
            continue
        for mod in project_modules:
            mod.environment_id = default.id
        await ensure_default_modules(db, project_id, default.id)

    await db.flush()


async def ensure_default_modules(
    db: AsyncSession, project_id: uuid.UUID, environment_id: uuid.UUID
) -> None:
    svc = ModuleService(db)
    await svc.get_or_create_module(project_id, environment_id, "General")
