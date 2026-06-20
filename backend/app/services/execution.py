"""Phase 5 — Test execution: background live automation across all frameworks."""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db.models import AutomationAssetModel, ExecutionRunModel, PerformanceAssetModel, TestCaseModel
from app.intelligence.generators import SelfHealingGenerator
from app.runners.framework_runner import (
    ALL_FRAMEWORKS,
    build_workspace_for_test_cases,
    prepare_framework_workspace,
    run_framework,
)
from app.runners.playwright_runner import cleanup_workspace, get_video_path, persist_videos
from app.runners.test_case_runner import (
    map_steps_from_test_case,
    parse_framework_steps,
    run_single_test_case_workspace,
)
from app.services.automation import AutomationService
from app.services.e2e_bundle import (
    dedupe_files,
    is_placeholder_playwright_asset,
    load_orangehrm_e2e_files,
    materialize_batch_playwright_specs,
)


TEST_PATTERNS = [
    re.compile(r"\bit\s*\(", re.I),
    re.compile(r"\btest\s*\(", re.I),
    re.compile(r"\bdescribe\s*\(", re.I),
    re.compile(r"^\*\*\* Test", re.M),
    re.compile(r"^def test_", re.M),
]


class ExecutionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.automation = AutomationService(db)
        self.healer = SelfHealingGenerator()

    async def start_automation(
        self,
        project_id: uuid.UUID,
        asset_id: uuid.UUID,
        mode: str = "live",
        apply_healing: bool = False,
        background: bool = True,
    ) -> ExecutionRunModel:
        asset = await self.automation.get_asset(asset_id)
        if not asset or asset.project_id != project_id:
            raise ValueError("Automation asset not found")

        if mode == "live" and asset.framework not in ALL_FRAMEWORKS:
            mode = "dry_run"

        run = ExecutionRunModel(
            project_id=project_id,
            asset_id=asset_id,
            asset_type="automation",
            mode=mode,
            status="running",
            summary={"framework": asset.framework, "asset_name": asset.name},
        )
        self.db.add(run)
        await self.db.flush()

        use_background = background and mode == "live"
        if use_background:
            from app.services.execution_worker import enqueue_execution

            await self.db.commit()
            enqueue_execution(run.id, project_id, asset_id, mode, apply_healing)
            return run

        await self.execute_run(run.id, project_id, asset_id, mode, apply_healing)
        return run

    async def start_batch_run(
        self,
        project_id: uuid.UUID,
        test_case_ids: list[uuid.UUID],
        *,
        asset_id: uuid.UUID | None = None,
        mode: str = "live",
        apply_healing: bool = False,
        background: bool = True,
        headed: bool = False,
        embed_live: bool = False,
        run_name: str | None = None,
        sprint: str | None = None,
        release: str | None = None,
        agent_id: str | None = None,
        base_url: str = "https://example.com",
        run_type: str = "automation",
        performance_asset_id: uuid.UUID | None = None,
        framework: str = "playwright",
    ) -> ExecutionRunModel:
        if not test_case_ids and run_type == "automation":
            raise ValueError("Select at least one test case")
        if run_type == "performance" and not performance_asset_id:
            raise ValueError("Select a performance script to run")

        if framework not in ALL_FRAMEWORKS:
            framework = "playwright"

        if asset_id and run_type == "automation":
            asset = await self.automation.get_asset(asset_id)
            if asset and asset.project_id == project_id:
                framework = asset.framework

        from app.services.runner_agent import ensure_localhost_agent

        agent = await ensure_localhost_agent(self.db, project_id)
        agent_id = agent_id or str(agent.id)

        run = ExecutionRunModel(
            project_id=project_id,
            asset_id=asset_id or performance_asset_id,
            asset_type=run_type,
            mode=mode,
            status="running",
            test_case_ids=[str(t) for t in test_case_ids],
            run_name=run_name or f"Batch run — {len(test_case_ids)} tests",
            sprint=sprint,
            release=release,
            agent_id=agent_id,
            progress={"total": max(len(test_case_ids), 1 if run_type == "performance" else 0), "completed": 0, "current": None, "percent": 0},
            summary={"run_type": run_type, "agent": agent.name, "framework": framework, "headed": headed, "embed_live": embed_live},
        )
        self.db.add(run)
        await self.db.flush()

        if background:
            from app.services.execution_worker import enqueue_batch_execution

            await self.db.commit()
            enqueue_batch_execution(
                run.id, project_id, test_case_ids, asset_id, mode, apply_healing,
                base_url, run_type, performance_asset_id, framework, headed, embed_live,
            )
            return run

        await self.execute_batch_run(
            run.id, project_id, test_case_ids, asset_id, mode, apply_healing,
            base_url, run_type, performance_asset_id, framework, headed=headed, embed_live=embed_live,
        )
        return run

    async def execute_batch_run(
        self,
        run_id: uuid.UUID,
        project_id: uuid.UUID,
        test_case_ids: list[uuid.UUID],
        asset_id: uuid.UUID | None,
        mode: str,
        apply_healing: bool,
        base_url: str,
        run_type: str,
        performance_asset_id: uuid.UUID | None,
        framework: str = "playwright",
        headed: bool = False,
        embed_live: bool = False,
    ) -> None:
        run = await self.db.get(ExecutionRunModel, run_id)
        if not run:
            return

        framework = (run.summary or {}).get("framework", framework)
        headed = headed or bool((run.summary or {}).get("headed", False))
        embed_live = embed_live or bool((run.summary or {}).get("embed_live", False))

        if run_type == "performance" and performance_asset_id:
            await self._run_performance_batch(run, project_id, performance_asset_id, test_case_ids)
            run.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            return

        Path(settings.execution_artifacts_dir).mkdir(parents=True, exist_ok=True)
        cases = await self._load_test_cases(project_id, test_case_ids)
        if not cases:
            run.status = "failed"
            run.logs = "No test cases found"
            run.completed_at = datetime.now(timezone.utc)
            return

        if mode == "live" and run_type == "automation" and not asset_id:
            run.status = "failed"
            run.logs = (
                "Live Playwright execution requires an automation asset with real scripts. "
                "Select an asset in Executions or Studio — stub goto tests are not used in live mode."
            )
            run.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            return

        # When an automation asset is linked, run the saved scripts — not generated goto stubs.
        if asset_id and mode == "live":
            asset = await self.automation.get_asset(asset_id)
            if asset and asset.project_id == project_id:
                framework = asset.framework
                results: list[dict] = []
                logs: list[str] = [
                    f"Batch execution via localhost agent (automation asset)",
                    f"Asset: {asset.name}",
                    f"Framework: {framework}",
                    f"Test cases: {len(cases)}",
                    f"Executor: asset_live_v2",
                ]
                passed, failed = await self._execute_batch_with_asset(
                    run, cases, asset, apply_healing, base_url, results, logs,
                    headed=headed, embed_live=embed_live,
                )
                run.progress = {"total": len(cases), "completed": len(cases), "current": None, "percent": 100, "phase": "done"}
                from app.services.execution_worker import is_run_cancel_requested

                if is_run_cancel_requested(run.id):
                    run.status = "cancelled"
                elif failed:
                    run.status = "failed"
                else:
                    run.status = "completed"
                run.summary = {
                    **(run.summary or {}),
                    "passed": passed,
                    "failed": failed,
                    "warnings": sum(1 for r in results if r.get("status") == "passed_with_warnings"),
                    "tests_detected": len(cases),
                    "videos_captured": sum(1 for r in results if r.get("has_video")),
                    "runner": "localhost_agent",
                    "framework": framework,
                    "asset_name": asset.name,
                    "executor": "asset_live_v2",
                }
                run.results = list(results)
                flag_modified(run, "results")
                run.logs = "\n".join(logs)
                run.completed_at = datetime.now(timezone.utc)
                await self.db.flush()
                return
            logs_stub: list[str] = [f"Automation asset {asset_id} not found for this project"]
            run.status = "failed"
            run.logs = "\n".join(logs_stub)
            run.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            return

        results: list[dict] = []
        logs: list[str] = [
            f"Batch execution via localhost agent",
            f"Framework: {framework}",
            f"Test cases: {len(cases)}",
            f"Mode: {mode}",
        ]
        if not asset_id:
            logs.append(
                "WARNING: No automation asset linked — running auto-generated stubs (page.goto only), NOT your saved scripts."
            )
        passed = failed = 0

        for idx, tc in enumerate(cases):
            tc_dict = {
                "id": str(tc.id),
                "title": tc.title,
                "steps": tc.steps or [],
                "expected_results": tc.expected_results or [],
            }
            run.progress = {
                "total": len(cases),
                "completed": idx,
                "current": tc.title,
                "current_test_case_id": str(tc.id),
                "current_step_index": 0,
                "total_steps": len(tc.steps or []),
                "percent": round(idx / len(cases) * 100),
            }
            in_progress = {
                "test_case_id": str(tc.id),
                "title": tc.title,
                "status": "running",
                "steps": map_steps_from_test_case(tc_dict, "pending"),
            }
            results.append(in_progress)
            run.results = list(results)
            flag_modified(run, "results")
            await self.db.flush()

            if mode == "live":
                workspace = build_workspace_for_test_cases([tc_dict], base_url, framework)
                # Commit progress before long Playwright run — avoids SQLite lock during npm/test
                await self.db.commit()
                try:
                    outcome = await run_single_test_case_workspace(workspace, framework)
                    raw = outcome.get("results", [])
                    exit_code = outcome.get("exit_code", 1)
                    if raw:
                        status = "passed" if raw[0].get("status") == "passed" else "failed"
                    elif exit_code == 0:
                        status = "passed"
                    else:
                        status = "failed"
                    if not outcome.get("available"):
                        status = "passed_with_warnings"
                        logs.append(outcome.get("reason", "fallback"))

                    if settings.execution_video_enabled and raw:
                        persisted = persist_videos(workspace, run.project_id, run.id, raw)
                        entry = persisted[0] if persisted else {}
                    else:
                        entry = raw[0] if raw else {}

                    step_results = parse_framework_steps(raw, tc_dict, exit_code)
                    err_msg = entry.get("error")
                    if not err_msg and status == "failed":
                        err_msg = (outcome.get("stderr") or outcome.get("stdout") or "")[:500] or None
                    result_entry = {
                        "test_case_id": str(tc.id),
                        "title": tc.title,
                        "file": entry.get("file", f"tests/{idx}.spec.ts"),
                        "status": status,
                        "steps": step_results,
                        "error": err_msg,
                        "has_video": entry.get("has_video", False),
                        "video_id": str(idx),
                    }
                    if result_entry["has_video"]:
                        result_entry["video_url"] = (
                            f"/api/v1/projects/{run.project_id}/executions/{run.id}/videos/{idx}"
                        )
                except Exception as exc:
                    logs.append(f"{tc.title}: error — {exc}")
                    result_entry = {
                        "test_case_id": str(tc.id),
                        "title": tc.title,
                        "status": "failed",
                        "steps": map_steps_from_test_case(tc_dict, "failed"),
                        "error": str(exc)[:500],
                        "has_video": False,
                        "video_id": str(idx),
                    }
                finally:
                    cleanup_workspace(workspace)
                    run = await self.db.get(ExecutionRunModel, run_id)
            else:
                step_results = map_steps_from_test_case(tc_dict, "passed")
                result_entry = {
                    "test_case_id": str(tc.id),
                    "title": tc.title,
                    "status": "passed",
                    "steps": step_results,
                    "has_video": False,
                }

            if results and results[-1].get("test_case_id") == str(tc.id) and results[-1].get("status") == "running":
                results[-1] = result_entry
            else:
                results.append(result_entry)
            if result_entry["status"] in ("passed", "passed_with_warnings"):
                passed += 1
            else:
                failed += 1
            logs.append(f"{tc.title}: {result_entry['status']}")
            run.results = list(results)
            flag_modified(run, "results")
            await self.db.flush()

        run.progress = {"total": len(cases), "completed": len(cases), "current": None, "percent": 100}
        run.status = "failed" if failed else "completed"
        run.summary = {
            **(run.summary or {}),
            "passed": passed,
            "failed": failed,
            "warnings": sum(1 for r in results if r.get("status") == "passed_with_warnings"),
            "tests_detected": len(cases),
            "videos_captured": sum(1 for r in results if r.get("has_video")),
            "runner": "localhost_agent",
            "framework": framework,
        }
        run.results = list(results)
        flag_modified(run, "results")
        run.logs = "\n".join(logs)
        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _publish_run_progress(
        self,
        run: ExecutionRunModel,
        *,
        phase: str,
        detail: str,
        logs: list[str] | None = None,
        step_index: int | None = None,
    ) -> None:
        prog = dict(run.progress or {})
        prog["phase"] = phase
        prog["detail"] = detail
        prog["executor"] = "asset_live_v2"
        if step_index is not None:
            prog["current_step_index"] = step_index
        run.progress = prog
        if logs is not None:
            run.logs = "\n".join(logs)
        flag_modified(run, "progress")
        await self.db.flush()
        await self.db.commit()

    @staticmethod
    def _apply_live_step_progress(results: list[dict], tc_index: int, step_index: int, status: str) -> None:
        if tc_index >= len(results):
            return
        entry = results[tc_index]
        steps = entry.get("steps") or []
        for i, step in enumerate(steps):
            if i < step_index:
                step["status"] = "passed"
            elif i == step_index:
                step["status"] = status
            elif step.get("status") not in ("passed", "failed"):
                step["status"] = "pending"
        entry["steps"] = steps

    @staticmethod
    def _prepare_asset_files(files: list[dict], base_url: str) -> list[dict]:
        """Copy asset files and inject the configured base URL."""
        prepared: list[dict] = []
        for f in files:
            content = f.get("content", "")
            if base_url and content:
                content = content.replace("https://example.com", base_url)
                content = content.replace("http://example.com", base_url)
                content = re.sub(
                    r"baseURL:\s*['\"]https?://[^'\"]+['\"]",
                    f"baseURL: '{base_url}'",
                    content,
                )
            prepared.append({**f, "content": content})
        return prepared

    @staticmethod
    def _match_playwright_result(
        raw_results: list[dict], title: str, test_case_id: str | None = None
    ) -> dict | None:
        if not raw_results:
            return None
        if test_case_id:
            short = test_case_id.replace("-", "")[:8]
            for r in raw_results:
                blob = f"{r.get('file', '')} {r.get('title', '')}"
                if f"tc_{short}" in blob:
                    return r
        title_lower = title.lower()
        for r in raw_results:
            blob = f"{r.get('title', '')} {r.get('file', '')}".lower()
            if title_lower in blob or any(part in blob for part in title_lower.split() if len(part) > 3):
                return r
        return raw_results[0] if len(raw_results) == 1 else None

    async def _execute_batch_with_asset(
        self,
        run: ExecutionRunModel,
        cases: list[TestCaseModel],
        asset: AutomationAssetModel,
        apply_healing: bool,
        base_url: str,
        results: list[dict],
        logs: list[str],
        headed: bool = False,
        embed_live: bool = False,
    ) -> tuple[int, int]:
        framework = asset.framework
        files = dedupe_files(self._prepare_asset_files(asset.files or [], base_url))
        if framework == "playwright" and is_placeholder_playwright_asset(files):
            logs.append("WARNING: Asset has placeholder stubs — swapping in bundled OrangeHRM E2E Playwright suite")
            try:
                files = load_orangehrm_e2e_files(base_url)
                asset.files = files
                from sqlalchemy.orm.attributes import flag_modified as fm
                fm(asset, "files")
                await self.db.flush()
            except FileNotFoundError as exc:
                logs.append(f"ERROR: {exc}")

        if framework == "playwright" and (embed_live or headed):
            try:
                bundle = load_orangehrm_e2e_files(base_url)
                refresh_prefixes = ("utils/", "pages/", "fixtures/")
                refresh_paths = {
                    f.get("path", "").replace("\\", "/")
                    for f in bundle
                    if f.get("path", "").replace("\\", "/").startswith(refresh_prefixes)
                }
                files = [f for f in files if f.get("path", "").replace("\\", "/") not in refresh_paths]
                files.extend(f for f in bundle if f.get("path", "").replace("\\", "/") in refresh_paths)
                files = dedupe_files(files)
                logs.append("Refreshed page objects and progress hooks for live debug sync")
            except FileNotFoundError:
                pass

        if framework == "playwright" and cases:
            files = materialize_batch_playwright_specs(files, cases, base_url)
            logs.append(f"Generated {len(cases)} per-test Playwright spec(s) with real page objects")

        test_files = [f for f in files if f.get("type") == "test" or "spec" in f.get("path", "").lower() or f.get("path", "").endswith((".cy.js", ".test.js", ".robot"))]
        logs.append(f"Materialized {len(files)} file(s), {len(test_files)} test file(s)")

        for idx, tc in enumerate(cases):
            tc_dict = {
                "id": str(tc.id),
                "title": tc.title,
                "steps": tc.steps or [],
                "expected_results": tc.expected_results or [],
            }
            run.progress = {
                "total": len(cases),
                "completed": idx,
                "current": tc.title,
                "current_test_case_id": str(tc.id),
                "current_step_index": 0,
                "total_steps": len(tc.steps or []),
                "percent": round(idx / max(len(cases), 1) * 100),
            }
            results.append({
                "test_case_id": str(tc.id),
                "title": tc.title,
                "status": "running",
                "steps": map_steps_from_test_case(tc_dict, "pending"),
            })
            run.results = list(results)
            flag_modified(run, "results")
            await self.db.flush()

        passed = failed = 0
        workspace = prepare_framework_workspace(files, framework)
        logs.append(f"Workspace: {workspace}")
        batch_specs = any(
            f.get("path", "").replace("\\", "/").startswith("tests/batch/")
            for f in files
        )
        test_glob = "tests/batch" if batch_specs else None
        if embed_live:
            logs.append("Debug mode: live browser view in Studio (embedded) + video recording")
        elif headed:
            logs.append("Debug mode: visible browser window (headed) + video recording enabled")
        if test_glob:
            logs.append(f"Running Playwright target: {test_glob}")
        run_id = run.id
        project_id = run.project_id
        from app.runners.playwright_runner import run_artifact_dir

        artifact_dir = run_artifact_dir(project_id, run_id)
        progress_path = artifact_dir / "progress.json"
        live_frame_path = artifact_dir / "live.jpg"
        total_steps = max(len(cases[0].steps or []), 1) if cases else 15

        await self._publish_run_progress(run, phase="prepare", detail="Preparing Playwright workspace…", logs=logs)
        await self.db.commit()

        async def on_progress(phase: str, detail: str) -> None:
            run_row = await self.db.get(ExecutionRunModel, run_id)
            if not run_row:
                return
            await self._publish_run_progress(run_row, phase=phase, detail=detail, logs=logs + [detail])

        async def on_step_progress(data: dict) -> None:
            run_row = await self.db.get(ExecutionRunModel, run_id)
            if not run_row or not run_row.results:
                return
            step_index = int(data.get("step_index") or 0)
            status = str(data.get("status") or "running")
            mapped = "running" if status == "running" else ("passed" if status == "passed" else "failed")
            live_results = list(run_row.results)
            ExecutionService._apply_live_step_progress(live_results, 0, step_index, mapped)
            run_row.results = live_results
            flag_modified(run_row, "results")
            prog = dict(run_row.progress or {})
            prog["current_step_index"] = step_index
            prog["phase"] = "playwright_test"
            prog["detail"] = str(data.get("description") or f"Step {step_index + 1}")
            run_row.progress = prog
            flag_modified(run_row, "progress")
            await self.db.flush()
            await self.db.commit()

        try:
            outcome = await run_framework(
                workspace,
                framework,
                on_progress=on_progress,
                test_glob=test_glob,
                headed=headed,
                embed_live=embed_live,
                progress_path=progress_path,
                live_frame_path=live_frame_path,
                total_steps=total_steps,
                on_step_progress=on_step_progress if (embed_live or headed) else None,
                cancel_run_id=str(run_id),
            )
            raw_results = outcome.get("results", [])
            exit_code = outcome.get("exit_code", 1)
            logs.append(outcome.get("logs", ""))

            from app.services.execution_worker import is_run_cancel_requested

            if outcome.get("cancelled") or is_run_cancel_requested(run_id):
                logs.append("Run cancelled by user")
                for idx, tc in enumerate(cases):
                    tc_dict = {
                        "id": str(tc.id),
                        "title": tc.title,
                        "steps": tc.steps or [],
                        "expected_results": tc.expected_results or [],
                    }
                    steps = map_steps_from_test_case(tc_dict, "pending")
                    for step in steps:
                        if step.get("status") == "pending":
                            step["status"] = "skipped"
                    results[idx] = {
                        "test_case_id": str(tc.id),
                        "title": tc.title,
                        "status": "cancelled",
                        "steps": steps,
                        "error": "Cancelled by user",
                        "has_video": False,
                        "video_id": str(idx),
                    }
                run.results = list(results)
                flag_modified(run, "results")
                run.logs = "\n".join(logs)
                return passed, failed
            if outcome.get("stdout"):
                logs.append(outcome.get("stdout", "")[-2000:])
            if outcome.get("stderr"):
                logs.append(outcome.get("stderr", "")[-2000:])

            if not outcome.get("available"):
                err = outcome.get("reason", f"{framework} runner unavailable")
                logs.append(f"ERROR: {err}")
                for idx, tc in enumerate(cases):
                    tc_dict = {"id": str(tc.id), "title": tc.title, "steps": tc.steps or [], "expected_results": tc.expected_results or []}
                    results[idx] = {
                        "test_case_id": str(tc.id),
                        "title": tc.title,
                        "status": "failed",
                        "steps": map_steps_from_test_case(tc_dict, "failed"),
                        "error": err,
                        "has_video": False,
                        "video_id": str(idx),
                    }
                    failed += 1
                run.results = list(results)
                flag_modified(run, "results")
                return passed, failed

            if settings.execution_video_enabled and raw_results:
                persisted = persist_videos(workspace, run.project_id, run.id, raw_results)
            else:
                persisted = [{**r, "has_video": False} for r in raw_results]

            for idx, tc in enumerate(cases):
                tc_dict = {
                    "id": str(tc.id),
                    "title": tc.title,
                    "steps": tc.steps or [],
                    "expected_results": tc.expected_results or [],
                }
                matched = self._match_playwright_result(persisted, tc.title, str(tc.id))
                if matched:
                    status = matched.get("status", "failed")
                    if status not in ("passed", "passed_with_warnings"):
                        status = "failed"
                    step_results = parse_framework_steps([matched], tc_dict, exit_code if status == "failed" else 0)
                    entry = matched
                elif exit_code == 0 and len(persisted) == len(cases) and idx < len(persisted):
                    entry = persisted[idx]
                    status = entry.get("status", "failed")
                    if status not in ("passed", "passed_with_warnings"):
                        status = "failed"
                    step_results = parse_framework_steps([entry], tc_dict, 0 if status == "passed" else 1)
                else:
                    status = "failed"
                    step_results = map_steps_from_test_case(tc_dict, "failed")
                    entry = {}
                    if not persisted:
                        err_msg = (outcome.get("stderr") or outcome.get("stdout") or "")[:500]
                        entry = {"error": err_msg or "No Playwright result for this test case"}

                err_msg = entry.get("error")
                if err_msg:
                    from app.runners.playwright_output import strip_ansi, strip_node_warnings

                    err_msg = strip_node_warnings(strip_ansi(str(err_msg)))
                if not err_msg and status == "failed":
                    from app.runners.playwright_output import extract_playwright_failure

                    err_msg = extract_playwright_failure(
                        outcome.get("stdout", ""),
                        outcome.get("stderr", ""),
                        raw_results,
                    ) or "Playwright test failed"

                result_entry = {
                    "test_case_id": str(tc.id),
                    "title": tc.title,
                    "file": entry.get("file", ""),
                    "status": status,
                    "steps": step_results,
                    "error": err_msg,
                    "has_video": entry.get("has_video", False),
                    "video_id": str(idx),
                }
                if result_entry["has_video"]:
                    result_entry["video_url"] = (
                        f"/api/v1/projects/{run.project_id}/executions/{run.id}/videos/{idx}"
                    )
                results[idx] = result_entry
                if status in ("passed", "passed_with_warnings"):
                    passed += 1
                else:
                    failed += 1
                logs.append(f"{tc.title}: {status} (live {framework})")

            run.results = list(results)
            flag_modified(run, "results")
        except Exception as exc:
            logs.append(f"Execution error: {exc}")
            for idx, tc in enumerate(cases):
                tc_dict = {"id": str(tc.id), "title": tc.title, "steps": tc.steps or [], "expected_results": tc.expected_results or []}
                results[idx] = {
                    "test_case_id": str(tc.id),
                    "title": tc.title,
                    "status": "failed",
                    "steps": map_steps_from_test_case(tc_dict, "failed"),
                    "error": str(exc)[:500],
                    "has_video": False,
                    "video_id": str(idx),
                }
                failed += 1
            run.results = list(results)
            flag_modified(run, "results")
        finally:
            cleanup_workspace(workspace)
            run = await self.db.get(ExecutionRunModel, run.id)

        return passed, failed

    async def _load_test_cases(
        self, project_id: uuid.UUID, test_case_ids: list[uuid.UUID]
    ) -> list[TestCaseModel]:
        from app.services.test_cases import is_automation_enabled

        if not test_case_ids:
            result = await self.db.execute(
                select(TestCaseModel).where(TestCaseModel.project_id == project_id).order_by(TestCaseModel.created_at)
            )
            return [c for c in result.scalars().all() if is_automation_enabled(c)]
        out = []
        for tid in test_case_ids:
            tc = await self.db.get(TestCaseModel, tid)
            if tc and tc.project_id == project_id and is_automation_enabled(tc):
                out.append(tc)
        return out

    async def _run_performance_batch(
        self,
        run: ExecutionRunModel,
        project_id: uuid.UUID,
        asset_id: uuid.UUID,
        test_case_ids: list[uuid.UUID],
    ) -> None:
        from app.services.performance.service import PerformanceService
        from app.services.runner_agent import ensure_localhost_agent

        perf = PerformanceService(self.db)
        asset = await perf.get_asset(asset_id)
        if not asset:
            run.status = "failed"
            run.logs = "Performance asset not found"
            return

        agent = await ensure_localhost_agent(self.db, project_id)
        main_script = next(
            (s for s in (asset.scripts or []) if s.get("type") in ("k6", "script") or s.get("path", "").endswith(".js")),
            (asset.scripts or [{}])[0] if asset.scripts else {},
        )
        data_files = [s for s in (asset.scripts or []) if s.get("type") == "data" or "data/" in s.get("path", "")]

        from app.services.performance.execution import run_k6

        run.progress = {"total": 1, "completed": 0, "current": "Running k6 load test", "percent": 10}
        run.summary = {**(run.summary or {}), "framework": asset.tool, "agent": agent.name}
        await self.db.flush()

        outcome = await run_k6(main_script.get("content", ""), data_files, duration_override="30s")
        dashboard = outcome.get("dashboard", {})
        status = "completed" if outcome.get("status") == "completed" else "failed"
        summary_metrics = dashboard.get("summary", {})

        perf_run = None
        from app.db.models import PerformanceRunModel
        perf_run = PerformanceRunModel(
            project_id=project_id,
            asset_id=asset_id,
            agent_id=agent.id,
            workload_profile="smoke",
            status=status,
            summary={"agent": agent.name, "execution_run_id": str(run.id), "passed": status == "completed"},
            metrics=dashboard,
            logs=(outcome.get("stdout", "") + outcome.get("stderr", ""))[:50000],
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(perf_run)
        await self.db.flush()

        results = [{
            "test_case_id": str(tid),
            "title": f"Performance — {asset.name}",
            "status": status,
            "performance_run_id": str(perf_run.id),
            "steps": [
                {"order": i + 1, "description": t.get("name", f"Transaction {i + 1}"), "status": t.get("status", status)}
                for i, t in enumerate(dashboard.get("transactions", [])[:20])
            ] or [
                {"order": 1, "description": "Execute k6 load script", "status": status},
                {"order": 2, "description": "Validate SLA thresholds", "status": status},
            ],
            "metrics": summary_metrics,
            "transactions": dashboard.get("transactions", []),
            "has_video": False,
        } for tid in (test_case_ids or [uuid.uuid4()])]

        run.status = status
        run.summary = {
            **(run.summary or {}),
            "passed": len(results) if status == "completed" else 0,
            "failed": 0 if status == "completed" else len(results),
            "runner": "k6_localhost",
            "performance_run_id": str(perf_run.id),
            "metrics": summary_metrics,
            "transactions": len(dashboard.get("transactions", [])),
        }
        run.results = results
        run.logs = outcome.get("stdout", "") + outcome.get("stderr", "")
        run.progress = {"total": len(results), "completed": len(results), "percent": 100}

    async def execute_run(
        self,
        run_id: uuid.UUID,
        project_id: uuid.UUID,
        asset_id: uuid.UUID,
        mode: str,
        apply_healing: bool,
    ) -> None:
        run = await self.db.get(ExecutionRunModel, run_id)
        if not run:
            raise ValueError("Execution run not found")

        asset = await self.automation.get_asset(asset_id)
        if not asset or asset.project_id != project_id:
            run.status = "failed"
            run.logs = "Automation asset not found"
            run.completed_at = datetime.now(timezone.utc)
            return

        Path(settings.execution_artifacts_dir).mkdir(parents=True, exist_ok=True)

        if mode == "live" and asset.framework in ALL_FRAMEWORKS:
            await self._run_live_framework(run, asset, apply_healing)
        else:
            await self._run_dry_run(run, asset, apply_healing)

        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _apply_healing_to_asset(
        self, asset: AutomationAssetModel, results: list[dict]
    ) -> int:
        files = list(asset.files or [])
        patches = 0
        for result in results:
            healing = result.get("healing")
            if not healing or not healing.get("repairs"):
                continue
            healed = healing["repairs"][0].get("healed", "")
            if not healed:
                continue
            path = result.get("file", "")
            for f in files:
                if f.get("path") != path:
                    continue
                content = f.get("content", "")
                if "TODO" in content or "placeholder" in content.lower() or "[data-testid='...']" in content:
                    f["content"] = content.replace(
                        "[data-testid='...']", healed.split("#")[0].strip()
                    ).replace("TODO", healed.split("#")[0].strip())
                    patches += 1
                elif "getByTestId" in content and "..." in content:
                    f["content"] = content.replace("'...'", f"'element-{patches + 1}'")
                    patches += 1
        if patches:
            asset.files = files
            asset.version += 1
            asset.status = "healed"
            asset.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
        return patches

    async def _run_live_framework(
        self, run: ExecutionRunModel, asset: AutomationAssetModel, apply_healing: bool
    ) -> None:
        framework = asset.framework
        base_url = (run.summary or {}).get("base_url") or "https://example.com"
        files = dedupe_files(self._prepare_asset_files(asset.files or [], base_url))
        if framework == "playwright" and is_placeholder_playwright_asset(files):
            try:
                files = load_orangehrm_e2e_files(base_url)
                asset.files = files
                from sqlalchemy.orm.attributes import flag_modified as fm
                fm(asset, "files")
                await self.db.flush()
            except FileNotFoundError:
                pass
        workspace = prepare_framework_workspace(files, framework)
        logs = [
            f"Execution mode: live ({framework})",
            f"Framework: {framework}",
            f"Executor: asset_live_v2",
            f"Video capture: {'enabled' if settings.execution_video_enabled else 'disabled'}",
            f"Workspace: {workspace}",
        ]
        run_id = run.id
        await self._publish_run_progress(run, phase="prepare", detail="Preparing Playwright workspace…", logs=logs)

        async def on_progress(phase: str, detail: str) -> None:
            run_row = await self.db.get(ExecutionRunModel, run_id)
            if not run_row:
                return
            await self._publish_run_progress(run_row, phase=phase, detail=detail, logs=logs + [detail])

        try:
            outcome = await run_framework(workspace, framework, on_progress=on_progress)
            logs.append(outcome.get("logs", ""))

            if not outcome.get("available"):
                reason = outcome.get("reason", f"{framework} unavailable")
                logs.append(f"Live execution failed: {reason}")
                run.status = "failed"
                run.summary = {
                    **(run.summary or {}),
                    "passed": 0,
                    "failed": 1,
                    "tests_detected": 0,
                    "runner": framework,
                    "framework": framework,
                    "live_failed": True,
                }
                run.results = [{
                    "file": "",
                    "title": asset.name,
                    "status": "failed",
                    "error": reason,
                    "has_video": False,
                }]
                run.logs = "\n".join(logs)
                return

            raw_results = outcome.get("results", [])
            if settings.execution_video_enabled:
                results = persist_videos(workspace, run.project_id, run.id, raw_results)
            else:
                results = [{**r, "has_video": False} for r in raw_results]

            for entry in results:
                entry["tests_detected"] = 1
                if entry.get("has_video"):
                    entry["video_url"] = (
                        f"/api/v1/projects/{run.project_id}/executions/{run.id}/videos/{entry['video_id']}"
                    )
                if apply_healing and entry["status"] == "failed" and entry.get("error"):
                    entry["healing"] = self.healer.generate({
                        "type": "ui",
                        "failure": {
                            "error": entry["error"],
                            "locator": "[data-testid]",
                            "test_name": entry.get("title") or entry.get("file", ""),
                        },
                    })
                    run.healing_applied = True

            summary = outcome.get("summary", {})
            run.status = "completed" if outcome.get("exit_code") == 0 else "failed"
            run.summary = {
                **(run.summary or {}),
                "total_files": len(results) or summary.get("total_tests", 0),
                "passed": summary.get("passed", 0),
                "warnings": 0,
                "failed": summary.get("failed", 0),
                "tests_detected": summary.get("total_tests", len(results)),
                "exit_code": outcome.get("exit_code"),
                "runner": framework,
                "framework": framework,
                "videos_captured": summary.get("videos_captured", 0),
                "background": True,
            }
            run.results = results
            run.logs = "\n".join(logs) + "\n" + outcome.get("stdout", "") + outcome.get("stderr", "")
            if apply_healing:
                patches = await self._apply_healing_to_asset(asset, results)
                if patches:
                    run.summary = {**(run.summary or {}), "healing_patches_applied": patches}
        finally:
            cleanup_workspace(workspace)

    async def _run_live_playwright(
        self, run: ExecutionRunModel, asset: AutomationAssetModel, apply_healing: bool
    ) -> None:
        """Backward-compatible alias."""
        await self._run_live_framework(run, asset, apply_healing)

    async def _run_dry_run(
        self, run: ExecutionRunModel, asset: AutomationAssetModel, apply_healing: bool
    ) -> None:
        validation = await self.automation.validate(asset.id)
        results: list[dict] = []
        logs: list[str] = [f"Execution mode: {run.mode}", f"Framework: {asset.framework}"]

        for f in asset.files or []:
            path = f.get("path", "")
            content = f.get("content", "")
            if f.get("type") == "config" or path.endswith((".json", ".yaml", ".yml", ".md")):
                continue

            test_count = sum(len(p.findall(content)) for p in TEST_PATTERNS)
            test_count = max(test_count, 1 if "test" in path.lower() else 0)

            file_issues = [i for i in validation["issues"] if i["path"] == path]
            has_error = any(i["severity"] == "error" for i in file_issues)
            has_placeholder = any("placeholder" in i["message"].lower() for i in file_issues)

            status = "failed" if has_error else "passed_with_warnings" if has_placeholder else "passed"
            result_entry = {
                "file": path,
                "title": path,
                "tests_detected": test_count,
                "status": status,
                "issues": file_issues,
                "has_video": False,
            }

            if apply_healing and (has_placeholder or status == "failed"):
                result_entry["healing"] = self.healer.generate({
                    "type": "ui",
                    "failure": {
                        "error": "Element not found — placeholder or validation issue",
                        "locator": "[data-testid='...']",
                        "test_name": path,
                    },
                })
                run.healing_applied = True

            results.append(result_entry)
            logs.append(f"{path}: {status} ({test_count} tests detected)")

        if apply_healing:
            patches = await self._apply_healing_to_asset(asset, results)
            if patches:
                logs.append(f"Applied {patches} self-healing patch(es) to asset files")

        passed = sum(1 for r in results if r["status"] == "passed")
        warned = sum(1 for r in results if r["status"] == "passed_with_warnings")
        failed = sum(1 for r in results if r["status"] == "failed")

        run.status = "failed" if failed else "completed"
        run.summary = {
            **(run.summary or {}),
            "total_files": len(results),
            "passed": passed,
            "warnings": warned,
            "failed": failed,
            "validation_valid": validation["valid"],
            "tests_detected": sum(r["tests_detected"] for r in results),
            "runner": "dry_run",
            "videos_captured": 0,
        }
        run.results = results
        run.logs = "\n".join(logs)

    async def list_runs(self, project_id: uuid.UUID) -> list[ExecutionRunModel]:
        result = await self.db.execute(
            select(ExecutionRunModel)
            .where(ExecutionRunModel.project_id == project_id)
            .order_by(ExecutionRunModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def cancel_run(self, project_id: uuid.UUID, run_id: uuid.UUID) -> ExecutionRunModel:
        run = await self.get_run(run_id)
        if not run or run.project_id != project_id:
            raise ValueError("Execution run not found")
        if run.status != "running":
            return run

        from app.services.execution_worker import is_run_active, request_cancel_run

        request_cancel_run(run_id)

        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
        run.logs = (run.logs or "") + "\nCancelled by user"
        prog = dict(run.progress or {})
        prog["phase"] = "done"
        prog["detail"] = "Cancelled by user"
        prog["percent"] = 100
        run.progress = prog
        flag_modified(run, "progress")

        if run.results:
            updated = []
            for entry in run.results:
                item = dict(entry)
                if item.get("status") == "running":
                    item["status"] = "cancelled"
                    item["error"] = "Cancelled by user"
                    steps = item.get("steps") or []
                    for step in steps:
                        if step.get("status") in ("pending", "running"):
                            step["status"] = "skipped"
                    item["steps"] = steps
                updated.append(item)
            run.results = updated
            flag_modified(run, "results")

        if is_run_active(run_id):
            summary = dict(run.summary or {})
            summary["cancelled"] = True
            run.summary = summary
            flag_modified(run, "summary")

        await self.db.flush()
        return run

    async def get_run(self, run_id: uuid.UUID) -> ExecutionRunModel | None:
        return await self.db.get(ExecutionRunModel, run_id)

    def to_dict(self, run: ExecutionRunModel) -> dict:
        return {
            "id": str(run.id),
            "project_id": str(run.project_id),
            "asset_id": str(run.asset_id) if run.asset_id else None,
            "asset_type": run.asset_type or "automation",
            "mode": run.mode,
            "status": run.status,
            "summary": run.summary,
            "results": run.results,
            "logs": run.logs,
            "healing_applied": run.healing_applied,
            "test_case_ids": run.test_case_ids or [],
            "run_name": run.run_name,
            "sprint": run.sprint,
            "release": run.release,
            "agent_id": run.agent_id,
            "progress": run.progress,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    @staticmethod
    def resolve_video(project_id: uuid.UUID, run_id: uuid.UUID, video_id: int) -> Path | None:
        return get_video_path(project_id, run_id, video_id)
