"""Test case management helpers."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AutomationAssetModel,
    SprintModel,
    TestCaseModel,
    TestSuiteModel,
)

DISABLED_STATUS = "disabled"


def is_automation_enabled(case: TestCaseModel) -> bool:
    return (case.status or "").lower() != DISABLED_STATUS


async def list_project_test_cases(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    for_automation: bool = False,
) -> list[TestCaseModel]:
    result = await db.execute(
        select(TestCaseModel)
        .where(TestCaseModel.project_id == project_id)
        .order_by(TestCaseModel.created_at.desc())
    )
    cases = list(result.scalars().all())
    if for_automation:
        return [c for c in cases if is_automation_enabled(c)]
    return cases


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
