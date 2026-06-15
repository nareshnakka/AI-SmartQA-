"""Export service for Phase 1 deliverables."""

import csv
import io
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequirementModel, TestCaseModel, TestSuiteModel


class ExportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_json(self, project_id: uuid.UUID) -> dict:
        requirements = await self._get_requirements(project_id)
        test_cases = await self._get_test_cases(project_id)
        suites = await self._get_suites(project_id)
        return {
            "project_id": str(project_id),
            "requirements": requirements,
            "test_cases": test_cases,
            "test_suites": suites,
        }

    async def export_csv(self, project_id: uuid.UUID) -> str:
        test_cases = await self._get_test_cases(project_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Title", "Description", "Priority", "Status",
            "Steps", "Expected Results", "Tags", "Requirement Refs",
        ])
        for tc in test_cases:
            writer.writerow([
                tc["id"],
                tc["title"],
                tc["description"],
                tc["priority"],
                tc["status"],
                " | ".join(tc["steps"]),
                " | ".join(tc["expected_results"]),
                ", ".join(tc["tags"]),
                ", ".join(tc["requirement_refs"]),
            ])
        return output.getvalue()

    async def _get_requirements(self, project_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(RequirementModel).where(RequirementModel.project_id == project_id)
        )
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "content": r.content,
                "source_type": r.source_type,
                "created_at": r.created_at.isoformat(),
            }
            for r in result.scalars().all()
        ]

    async def _get_test_cases(self, project_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(TestCaseModel).where(TestCaseModel.project_id == project_id)
        )
        return [
            {
                "id": str(c.id),
                "title": c.title,
                "description": c.description,
                "steps": c.steps,
                "expected_results": c.expected_results,
                "priority": c.priority,
                "tags": c.tags,
                "requirement_refs": c.requirement_refs,
                "status": c.status,
            }
            for c in result.scalars().all()
        ]

    async def _get_suites(self, project_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(TestSuiteModel).where(TestSuiteModel.project_id == project_id)
        )
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "suite_type": s.suite_type,
                "test_case_ids": s.test_case_ids,
            }
            for s in result.scalars().all()
        ]
