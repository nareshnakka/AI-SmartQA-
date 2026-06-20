"""Test case management helpers."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    AutomationAssetModel,
    EnvironmentModel,
    ProjectModuleModel,
    SprintModel,
    TestCaseModel,
    TestSuiteModel,
)

DISABLED_STATUS = "disabled"


def is_automation_enabled(case: TestCaseModel) -> bool:
    return (case.status or "").lower() != DISABLED_STATUS


def test_case_to_dict(case: TestCaseModel) -> dict:
    mod = case.module
    env = case.environment
    return {
        "id": case.id,
        "project_id": case.project_id,
        "module_id": case.module_id,
        "module_name": mod.name if mod else None,
        "environment_id": case.environment_id,
        "environment_name": env.name if env else None,
        "case_code": case.case_code,
        "title": case.title,
        "description": case.description,
        "steps": case.steps,
        "expected_results": case.expected_results,
        "priority": case.priority,
        "tags": case.tags,
        "requirement_refs": case.requirement_refs,
        "status": case.status,
        "created_at": case.created_at,
    }


async def list_project_test_cases(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    for_automation: bool = False,
    module_ids: list[uuid.UUID] | None = None,
    environment_id: uuid.UUID | None = None,
    environment_ids: list[uuid.UUID] | None = None,
) -> list[TestCaseModel]:
    query = (
        select(TestCaseModel)
        .options(selectinload(TestCaseModel.module), selectinload(TestCaseModel.environment))
        .where(TestCaseModel.project_id == project_id)
        .order_by(TestCaseModel.case_code.asc(), TestCaseModel.created_at.desc())
    )
    if module_ids:
        query = query.where(TestCaseModel.module_id.in_(module_ids))
    if environment_id:
        query = query.where(TestCaseModel.environment_id == environment_id)
    elif environment_ids:
        query = query.where(TestCaseModel.environment_id.in_(environment_ids))
    result = await db.execute(query)
    cases = list(result.scalars().all())
    if for_automation:
        return [c for c in cases if is_automation_enabled(c)]
    return cases


async def create_project_test_case(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    title: str | None,
    description: str,
    steps: list,
    expected_results: list,
    priority: str,
    module_id: uuid.UUID | None,
    module_name: str | None,
    environment_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    status: str = "approved",
    case_type: str = "functional",
) -> TestCaseModel:
    from app.services.environments import EnvironmentService
    from app.services.modules import ModuleService
    from app.services.test_case_naming import next_case_code

    mod_svc = ModuleService(db)
    env_svc = EnvironmentService(db)
    mod = None
    env = None

    if environment_id:
        env = await env_svc.get_environment(environment_id)
        if not env or env.project_id != project_id:
            raise ValueError("Environment not found")
    else:
        env = await env_svc.get_default_environment(project_id)
    if not env:
        raise ValueError("No environment configured — add one in Settings")

    if module_id:
        mod = await mod_svc.get_module(module_id)
        if not mod or mod.project_id != project_id:
            raise ValueError("Module not found")
        if mod.environment_id != env.id:
            raise ValueError("Module does not belong to the selected environment")
    elif module_name:
        mod = await mod_svc.get_or_create_module(project_id, env.id, module_name)
    else:
        mod = await mod_svc.get_or_create_module(project_id, env.id, "General")

    case_code = await next_case_code(db, project_id, mod.id, case_type, env.id)
    human = (title or description or "Test case").strip()
    case = TestCaseModel(
        project_id=project_id,
        module_id=mod.id,
        environment_id=env.id,
        case_code=case_code,
        title=case_code,
        description=f"{human}\n\n{description}".strip() if description else human,
        steps=steps,
        expected_results=expected_results or ["Test completes successfully"],
        priority=priority,
        tags=tags or [],
        status=status,
    )
    db.add(case)
    await db.flush()
    await db.refresh(case, attribute_names=["module", "environment"])
    return case


async def remove_case_references(
    db: AsyncSession, project_id: uuid.UUID, case_ids: set[str]
) -> None:
    if not case_ids:
        return
    for model in (AutomationAssetModel, TestSuiteModel, SprintModel):
        result = await db.execute(select(model).where(model.project_id == project_id))
        for row in result.scalars().all():
            ids = row.test_case_ids or []
            filtered = [i for i in ids if i not in case_ids]
            if len(filtered) != len(ids):
                row.test_case_ids = filtered


async def bulk_test_case_action(
    db: AsyncSession,
    project_id: uuid.UUID,
    test_case_ids: list[uuid.UUID],
    action: str,
) -> dict:
    if action not in {"delete", "disable", "enable"}:
        raise ValueError(f"Unsupported action: {action}")
    if not test_case_ids:
        return {"updated": 0, "deleted": 0}

    id_set = set(test_case_ids)
    result = await db.execute(
        select(TestCaseModel).where(
            TestCaseModel.project_id == project_id,
            TestCaseModel.id.in_(id_set),
        )
    )
    cases = list(result.scalars().all())
    if not cases:
        return {"updated": 0, "deleted": 0}

    if action == "delete":
        str_ids = {str(c.id) for c in cases}
        await remove_case_references(db, project_id, str_ids)
        for case in cases:
            await db.delete(case)
        return {"updated": 0, "deleted": len(cases)}

    new_status = DISABLED_STATUS if action == "disable" else "ready"
    for case in cases:
        case.status = new_status
    await db.flush()
    return {"updated": len(cases), "deleted": 0}
