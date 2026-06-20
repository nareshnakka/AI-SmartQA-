"""Generate test case codes from project naming patterns."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EnvironmentModel, ProjectModel, ProjectModuleModel, TestCaseModel
from app.services.naming_patterns import (
    NamingPatternService,
    build_case_code,
    name_prefix,
    pattern_prefix,
)


async def next_case_code(
    db: AsyncSession,
    project_id: uuid.UUID,
    module_id: uuid.UUID | None,
    case_type: str = "functional",
    environment_id: uuid.UUID | None = None,
) -> str:
    project = await db.get(ProjectModel, project_id)
    if not project:
        raise ValueError("Project not found")

    module_name = "GENERAL"
    if module_id:
        mod = await db.get(ProjectModuleModel, module_id)
        if mod and mod.project_id == project_id:
            module_name = mod.name

    env_name = "GENER"
    if environment_id:
        env = await db.get(EnvironmentModel, environment_id)
        if env and env.project_id == project_id:
            env_name = env.name

    pattern_svc = NamingPatternService(db)
    pattern, seq_digits, _cat = await pattern_svc.get_pattern_for_type(project_id, case_type)

    proj5 = name_prefix(project.name)
    env5 = name_prefix(env_name)
    mod5 = name_prefix(module_name)
    prefix = pattern_prefix(pattern, proj5=proj5, env5=env5, mod5=mod5, seq_digits=seq_digits)

    query = select(TestCaseModel.case_code).where(
        TestCaseModel.project_id == project_id,
        TestCaseModel.case_code.isnot(None),
        TestCaseModel.case_code.like(f"{prefix}%"),
    )
    if environment_id:
        query = query.where(TestCaseModel.environment_id == environment_id)
    if module_id:
        query = query.where(TestCaseModel.module_id == module_id)

    result = await db.execute(query)
    max_num = 0
    for (code,) in result.all():
        if not code or not code.startswith(prefix):
            continue
        tail = code[len(prefix) :]
        digits = re.sub(r"\D", "", tail)
        if digits:
            max_num = max(max_num, int(digits))

    return build_case_code(
        pattern,
        proj5=proj5,
        env5=env5,
        mod5=mod5,
        seq=max_num + 1,
        seq_digits=seq_digits,
    )
