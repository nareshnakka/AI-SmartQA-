"""Global platform search across projects, tests, assets, and integrations."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AutomationAssetModel,
    DiscoverySessionModel,
    IntegrationModel,
    PerformanceAssetModel,
    ProjectModel,
    RequirementModel,
    TestCaseModel,
)


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, limit: int = 20) -> dict:
        q = query.strip()
        if not q:
            return {"query": q, "results": []}

        pattern = f"%{q.lower()}%"

        def ilike(col):
            return func.lower(col).like(pattern)
        results: list[dict] = []

        for project in (await self.db.execute(
            select(ProjectModel).where(
                or_(ilike(ProjectModel.name), ilike(ProjectModel.description))
            ).limit(limit)
        )).scalars():
            results.append({
                "type": "project",
                "id": str(project.id),
                "title": project.name,
                "subtitle": project.description or "",
                "href": f"/projects/{project.id}",
            })

        for tc in (await self.db.execute(
            select(TestCaseModel).where(
                or_(ilike(TestCaseModel.title), ilike(TestCaseModel.description))
            ).limit(limit)
        )).scalars():
            results.append({
                "type": "test_case",
                "id": str(tc.id),
                "title": tc.title,
                "subtitle": tc.priority,
                "href": f"/projects/{tc.project_id}",
            })

        for req in (await self.db.execute(
            select(RequirementModel).where(
                or_(ilike(RequirementModel.title), ilike(RequirementModel.content))
            ).limit(limit)
        )).scalars():
            results.append({
                "type": "requirement",
                "id": str(req.id),
                "title": req.title,
                "subtitle": req.source_type,
                "href": f"/projects/{req.project_id}",
            })

        for asset in (await self.db.execute(
            select(AutomationAssetModel).where(ilike(AutomationAssetModel.name)).limit(limit)
        )).scalars():
            results.append({
                "type": "automation",
                "id": str(asset.id),
                "title": asset.name,
                "subtitle": asset.framework,
                "href": f"/studio?project={asset.project_id}",
            })

        for asset in (await self.db.execute(
            select(PerformanceAssetModel).where(ilike(PerformanceAssetModel.name)).limit(limit)
        )).scalars():
            results.append({
                "type": "performance",
                "id": str(asset.id),
                "title": asset.name,
                "subtitle": asset.tool,
                "href": f"/performance?project={asset.project_id}",
            })

        for session in (await self.db.execute(
            select(DiscoverySessionModel).where(
                or_(ilike(DiscoverySessionModel.name), ilike(DiscoverySessionModel.base_url))
            ).limit(limit)
        )).scalars():
            results.append({
                "type": "discovery",
                "id": str(session.id),
                "title": session.name,
                "subtitle": session.base_url,
                "href": f"/discovery?project={session.project_id}",
            })

        for integration in (await self.db.execute(
            select(IntegrationModel).where(ilike(IntegrationModel.provider)).limit(limit)
        )).scalars():
            results.append({
                "type": "integration",
                "id": str(integration.id),
                "title": integration.provider,
                "subtitle": integration.status,
                "href": f"/integrations?project={integration.project_id}",
            })

        return {"query": q, "results": results[:limit]}
