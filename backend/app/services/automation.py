"""Phase 2 — Automation generation and asset management."""

import difflib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRunModel, AutomationAssetModel, TestCaseModel
from app.intelligence.generators import AutomationGenerator
from app.models.schemas import AgentStatus, AgentType
from app.services.test_cases import is_automation_enabled


FRAMEWORK_LANGUAGES = {
    "playwright": "typescript",
    "selenium": "java",
    "cypress": "javascript",
    "webdriverio": "typescript",
    "robot_framework": "python",
    "appium": "python",
    "puppeteer": "javascript",
    "testcafe": "javascript",
}


class AutomationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.generator = AutomationGenerator()

    async def generate(
        self,
        project_id: uuid.UUID,
        framework: str = "playwright",
        test_case_ids: list[str] | None = None,
        name: str | None = None,
        module_ids: list[uuid.UUID] | None = None,
    ) -> AutomationAssetModel:
        query = select(TestCaseModel).where(TestCaseModel.project_id == project_id)
        result = await self.db.execute(query)
        cases = list(result.scalars().all())

        if test_case_ids:
            id_set = set(test_case_ids)
            cases = [c for c in cases if str(c.id) in id_set]
        elif module_ids:
            id_set = set(module_ids)
            cases = [c for c in cases if c.module_id and c.module_id in id_set]

        cases = [c for c in cases if is_automation_enabled(c)]

        if not cases:
            raise ValueError("No test cases found. Generate test cases in Phase 1 first.")

        from app.services.test_case_naming import next_case_code

        case_type = "playwright" if framework == "playwright" else f"automation_{framework}"
        tc_data = []
        for c in cases:
            if framework == "playwright":
                ap_code = await next_case_code(
                    self.db, project_id, c.module_id, case_type, c.environment_id
                )
            else:
                ap_code = c.case_code
            tc_data.append({
                "id": str(c.id),
                "title": ap_code or c.title,
                "case_code": ap_code or c.case_code,
                "description": c.description,
                "steps": c.steps,
                "expected_results": c.expected_results,
                "priority": c.priority,
                "tags": (c.tags or []) + ([f"automation_code:{ap_code}"] if ap_code else []),
            })

        output = self.generator.generate({"framework": framework, "test_cases": tc_data})
        files = output.get("files", [])
        if framework == "playwright":
            for i, f in enumerate(files):
                if f.get("type") == "test" and tc_data:
                    code = tc_data[min(i, len(tc_data) - 1)].get("case_code")
                    if code and f.get("path"):
                        f["path"] = f"tests/{code}.spec.ts"
        language = FRAMEWORK_LANGUAGES.get(framework, output.get("language", "typescript"))

        asset = AutomationAssetModel(
            project_id=project_id,
            name=name or f"{framework.title()} Automation Suite",
            framework=framework,
            language=language,
            files=files,
            dependencies=output.get("dependencies", []),
            ci_pipeline_snippet=output.get("ci_pipeline_snippet"),
            test_case_ids=[str(c.id) for c in cases],
            version=1,
            status="generated",
        )
        self.db.add(asset)

        run = AgentRunModel(
            project_id=project_id,
            agent_type=AgentType.AUTOMATION.value,
            status=AgentStatus.COMPLETED.value,
            input_data={"framework": framework, "test_case_ids": asset.test_case_ids},
            output_data=output,
            llm_provider="qeos-native",
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()
        return asset

    async def list_assets(self, project_id: uuid.UUID) -> list[AutomationAssetModel]:
        result = await self.db.execute(
            select(AutomationAssetModel)
            .where(AutomationAssetModel.project_id == project_id)
            .order_by(AutomationAssetModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_asset(self, asset_id: uuid.UUID) -> AutomationAssetModel | None:
        return await self.db.get(AutomationAssetModel, asset_id)

    async def update_file(
        self, asset_id: uuid.UUID, file_path: str, content: str, save_version: bool = True
    ) -> AutomationAssetModel:
        asset = await self.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")

        files = list(asset.files or [])
        found = False
        for f in files:
            if f.get("path") == file_path:
                f["content"] = content
                found = True
                break
        if not found:
            files.append({"path": file_path, "content": content, "type": "test"})

        if save_version:
            # Create new version snapshot
            new_asset = AutomationAssetModel(
                project_id=asset.project_id,
                name=asset.name,
                framework=asset.framework,
                language=asset.language,
                files=files,
                dependencies=asset.dependencies,
                ci_pipeline_snippet=asset.ci_pipeline_snippet,
                test_case_ids=asset.test_case_ids,
                version=asset.version + 1,
                parent_id=asset.id,
                status="edited",
            )
            self.db.add(new_asset)
            await self.db.flush()
            return new_asset

        asset.files = files
        asset.status = "edited"
        asset.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return asset

    async def delete_files(
        self, asset_id: uuid.UUID, file_paths: list[str], save_version: bool = True
    ) -> AutomationAssetModel:
        asset = await self.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")

        paths_set = {p for p in file_paths if p}
        if not paths_set:
            raise ValueError("No files selected")

        existing = list(asset.files or [])
        files = [f for f in existing if f.get("path") not in paths_set]
        removed = len(existing) - len(files)
        if removed == 0:
            raise ValueError("No matching files found")

        from sqlalchemy.orm.attributes import flag_modified

        if save_version:
            new_asset = AutomationAssetModel(
                project_id=asset.project_id,
                name=asset.name,
                framework=asset.framework,
                language=asset.language,
                files=files,
                dependencies=asset.dependencies,
                ci_pipeline_snippet=asset.ci_pipeline_snippet,
                test_case_ids=asset.test_case_ids,
                version=asset.version + 1,
                parent_id=asset.id,
                status="edited",
            )
            self.db.add(new_asset)
            await self.db.flush()
            return new_asset

        asset.files = files
        asset.status = "edited"
        asset.updated_at = datetime.now(timezone.utc)
        flag_modified(asset, "files")
        await self.db.flush()
        return asset

    async def list_versions(self, asset_id: uuid.UUID) -> list[AutomationAssetModel]:
        """Get version chain for an asset."""
        asset = await self.get_asset(asset_id)
        if not asset:
            return []

        # Walk up to root
        root_id = asset_id
        current = asset
        while current.parent_id:
            parent = await self.get_asset(current.parent_id)
            if not parent:
                break
            root_id = parent.id
            current = parent

        # Collect all versions in chain from this project with same name
        result = await self.db.execute(
            select(AutomationAssetModel)
            .where(
                AutomationAssetModel.project_id == asset.project_id,
                AutomationAssetModel.name == asset.name,
            )
            .order_by(AutomationAssetModel.version.asc())
        )
        return list(result.scalars().all())

    def diff_files(self, files_a: list, files_b: list) -> list[dict]:
        """Diff two file sets."""
        map_a = {f["path"]: f.get("content", "") for f in files_a}
        map_b = {f["path"]: f.get("content", "") for f in files_b}
        all_paths = sorted(set(map_a) | set(map_b))
        diffs = []
        for path in all_paths:
            content_a = map_a.get(path, "")
            content_b = map_b.get(path, "")
            if content_a != content_b:
                diff_lines = list(difflib.unified_diff(
                    content_a.splitlines(keepends=True),
                    content_b.splitlines(keepends=True),
                    fromfile=f"v prev/{path}",
                    tofile=f"v curr/{path}",
                ))
                diffs.append({
                    "path": path,
                    "changed": True,
                    "diff": "".join(diff_lines) if diff_lines else "Content changed",
                })
            else:
                diffs.append({"path": path, "changed": False, "diff": ""})
        return diffs

    async def validate(self, asset_id: uuid.UUID) -> dict:
        """Basic syntax validation of generated scripts."""
        asset = await self.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")

        issues = []
        for f in asset.files or []:
            content = f.get("content", "")
            path = f.get("path", "")
            if not content.strip():
                issues.append({"path": path, "severity": "error", "message": "Empty file"})
            if path.endswith(".ts") and "import" not in content and f.get("type") == "test":
                issues.append({"path": path, "severity": "warning", "message": "Missing import statements"})
            if "TODO" in content or "/* Step:" in content:
                issues.append({"path": path, "severity": "info", "message": "Contains placeholder steps to implement"})

        return {
            "valid": not any(i["severity"] == "error" for i in issues),
            "file_count": len(asset.files or []),
            "issues": issues,
        }

    def build_zip_bytes(self, asset: AutomationAssetModel) -> bytes:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in asset.files or []:
                path = f.get("path", "")
                content = f.get("content", "")
                if path:
                    zf.writestr(path, content)
            if asset.ci_pipeline_snippet:
                zf.writestr(".github/workflows/qeos-ci.yml", asset.ci_pipeline_snippet)
            deps = asset.dependencies or []
            if deps:
                zf.writestr("package.json", '{"name":"qeos-automation","dependencies":{}}')
        buffer.seek(0)
        return buffer.read()

    def to_dict(self, asset: AutomationAssetModel) -> dict:
        return {
            "id": str(asset.id),
            "project_id": str(asset.project_id),
            "name": asset.name,
            "framework": asset.framework,
            "language": asset.language,
            "files": asset.files,
            "dependencies": asset.dependencies,
            "ci_pipeline_snippet": asset.ci_pipeline_snippet,
            "test_case_ids": asset.test_case_ids,
            "version": asset.version,
            "parent_id": str(asset.parent_id) if asset.parent_id else None,
            "status": asset.status,
            "created_at": asset.created_at.isoformat(),
            "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        }
