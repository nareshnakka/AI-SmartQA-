"""Platform tools the copilot can invoke."""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AutomationAssetModel,
    DiscoverySessionModel,
    ExecutionRunModel,
    PerformanceAssetModel,
    PerformanceRunModel,
    ProjectModel,
    TestCaseModel,
)
from app.runners.capabilities import get_runner_capabilities
from app.services.execution_worker import is_run_active


TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_projects",
        "description": "List all projects in QEOS",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_project_summary",
        "description": "Get counts of test cases, assets, runs for a project",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "Project UUID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "list_test_cases",
        "description": "List test cases for a project",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, default 20"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_discovery_sessions",
        "description": "List QA discovery / browser replay sessions",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "start_discovery",
        "description": "Start QA agent browser discovery on a URL (background)",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "base_url": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["project_id", "base_url"],
        },
    },
    {
        "name": "list_automation_assets",
        "description": "List automation framework assets (Playwright, Cypress, etc.)",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "generate_automation",
        "description": "Generate automation scripts for a framework from test cases",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "framework": {"type": "string", "description": "playwright, cypress, selenium, etc."},
            },
            "required": ["project_id", "framework"],
        },
    },
    {
        "name": "run_automation_asset",
        "description": "Execute an automation asset (live when supported)",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "asset_id": {"type": "string"},
                "mode": {"type": "string", "description": "live or dry_run", "default": "live"},
            },
            "required": ["project_id", "asset_id"],
        },
    },
    {
        "name": "run_batch_tests",
        "description": "Run selected test cases in batch (automation or performance)",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "test_case_ids": {"type": "array", "items": {"type": "string"}},
                "framework": {"type": "string", "default": "playwright"},
                "run_type": {"type": "string", "description": "automation or performance", "default": "automation"},
                "performance_asset_id": {"type": "string"},
                "base_url": {"type": "string"},
            },
            "required": ["project_id", "test_case_ids"],
        },
    },
    {
        "name": "list_performance_assets",
        "description": "List performance / load test scripts",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "generate_performance",
        "description": "Generate performance script from browser replay / test cases",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "tool": {"type": "string", "default": "k6"},
                "discovery_session_id": {"type": "string"},
                "base_url": {"type": "string"},
                "workload_profile": {"type": "string", "default": "load"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "run_performance_test",
        "description": "Execute a performance load test on localhost agent",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "asset_id": {"type": "string"},
                "workload_profile": {"type": "string", "default": "smoke"},
            },
            "required": ["project_id", "asset_id"],
        },
    },
    {
        "name": "list_executions",
        "description": "List automation execution runs",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "get_execution",
        "description": "Get details of a specific execution run",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}, "run_id": {"type": "string"}},
            "required": ["project_id", "run_id"],
        },
    },
    {
        "name": "list_performance_runs",
        "description": "List performance test runs",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "get_performance_run",
        "description": "Get performance run metrics dashboard summary",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}, "run_id": {"type": "string"}},
            "required": ["project_id", "run_id"],
        },
    },
    {
        "name": "get_execution_dashboard",
        "description": "Get execution dashboard stats (pass/fail, timeline)",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "get_platform_capabilities",
        "description": "Get runner capabilities (node, playwright, k6, frameworks)",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_run_status",
        "description": "Check if a background execution is still running",
        "parameters": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
    {
        "name": "list_llm_providers",
        "description": "List available LLM providers for AI features",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


async def execute_tool(db: AsyncSession, tool: str, arguments: dict) -> dict[str, Any]:
    try:
        handler = _TOOL_HANDLERS.get(tool)
        if not handler:
            return {"ok": False, "error": f"Unknown tool: {tool}"}
        return await handler(db, arguments)
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _list_projects(db: AsyncSession, _: dict) -> dict:
    result = await db.execute(select(ProjectModel).order_by(ProjectModel.created_at.desc()))
    projects = result.scalars().all()
    return {
        "ok": True,
        "projects": [{"id": str(p.id), "name": p.name, "description": p.description} for p in projects],
    }


async def _get_project_summary(db: AsyncSession, args: dict) -> dict:
    pid = uuid.UUID(args["project_id"])
    project = await db.get(ProjectModel, pid)
    if not project:
        return {"ok": False, "error": "Project not found"}
    tc = await db.execute(select(TestCaseModel).where(TestCaseModel.project_id == pid))
    aa = await db.execute(select(AutomationAssetModel).where(AutomationAssetModel.project_id == pid))
    pa = await db.execute(select(PerformanceAssetModel).where(PerformanceAssetModel.project_id == pid))
    ex = await db.execute(select(ExecutionRunModel).where(ExecutionRunModel.project_id == pid))
    pr = await db.execute(select(PerformanceRunModel).where(PerformanceRunModel.project_id == pid))
    return {
        "ok": True,
        "project": {"id": str(project.id), "name": project.name},
        "counts": {
            "test_cases": len(list(tc.scalars().all())),
            "automation_assets": len(list(aa.scalars().all())),
            "performance_assets": len(list(pa.scalars().all())),
            "executions": len(list(ex.scalars().all())),
            "performance_runs": len(list(pr.scalars().all())),
        },
    }


async def _list_test_cases(db: AsyncSession, args: dict) -> dict:
    pid = uuid.UUID(args["project_id"])
    limit = int(args.get("limit", 20))
    result = await db.execute(
        select(TestCaseModel).where(TestCaseModel.project_id == pid).limit(limit)
    )
    cases = result.scalars().all()
    return {
        "ok": True,
        "test_cases": [
            {"id": str(c.id), "title": c.title, "priority": c.priority, "status": c.status, "steps": len(c.steps or [])}
            for c in cases
        ],
    }


async def _list_discovery_sessions(db: AsyncSession, args: dict) -> dict:
    pid = uuid.UUID(args["project_id"])
    result = await db.execute(
        select(DiscoverySessionModel).where(DiscoverySessionModel.project_id == pid).order_by(DiscoverySessionModel.created_at.desc())
    )
    sessions = result.scalars().all()
    return {
        "ok": True,
        "sessions": [
            {
                "id": str(s.id), "name": s.name, "base_url": s.base_url, "status": s.status,
                "proposed_tests": len(s.proposed_test_cases or []),
                "navigation_events": len(s.navigation_log or []),
            }
            for s in sessions
        ],
    }


async def _start_discovery(db: AsyncSession, args: dict) -> dict:
    from app.services.discovery import DiscoveryService

    pid = uuid.UUID(args["project_id"])
    svc = DiscoveryService(db)
    session = await svc.start_discovery(
        pid, args["base_url"], name=args.get("name", "Copilot Discovery"), background=True,
    )
    await db.commit()
    return {"ok": True, "session_id": str(session.id), "status": session.status, "message": "Discovery started in background"}


async def _list_automation_assets(db: AsyncSession, args: dict) -> dict:
    from app.services.automation import AutomationService

    pid = uuid.UUID(args["project_id"])
    svc = AutomationService(db)
    assets = await svc.list_assets(pid)
    return {
        "ok": True,
        "assets": [{"id": str(a.id), "name": a.name, "framework": a.framework, "status": a.status} for a in assets],
    }


async def _generate_automation(db: AsyncSession, args: dict) -> dict:
    from app.services.automation import AutomationService

    pid = uuid.UUID(args["project_id"])
    svc = AutomationService(db)
    asset = await svc.generate(pid, framework=args.get("framework", "playwright"))
    await db.commit()
    return {"ok": True, "asset_id": str(asset.id), "name": asset.name, "framework": asset.framework}


async def _run_automation_asset(db: AsyncSession, args: dict) -> dict:
    from app.services.execution import ExecutionService

    pid = uuid.UUID(args["project_id"])
    aid = uuid.UUID(args["asset_id"])
    svc = ExecutionService(db)
    run = await svc.start_automation(pid, aid, mode=args.get("mode", "live"), background=True)
    await db.commit()
    return {"ok": True, "run_id": str(run.id), "status": run.status, "mode": run.mode}


async def _run_batch_tests(db: AsyncSession, args: dict) -> dict:
    from app.services.execution import ExecutionService

    pid = uuid.UUID(args["project_id"])
    tc_ids = [uuid.UUID(t) for t in args["test_case_ids"]]
    perf_id = uuid.UUID(args["performance_asset_id"]) if args.get("performance_asset_id") else None
    svc = ExecutionService(db)
    run = await svc.start_batch_run(
        pid, tc_ids,
        mode="live",
        background=True,
        framework=args.get("framework", "playwright"),
        run_type=args.get("run_type", "automation"),
        performance_asset_id=perf_id,
        base_url=args.get("base_url", "https://example.com"),
        run_name="Copilot batch run",
    )
    await db.commit()
    return {"ok": True, "run_id": str(run.id), "status": run.status}


async def _list_performance_assets(db: AsyncSession, args: dict) -> dict:
    from app.services.performance.service import PerformanceService

    pid = uuid.UUID(args["project_id"])
    svc = PerformanceService(db)
    assets = await svc.list_assets(pid)
    return {
        "ok": True,
        "assets": [{"id": str(a.id), "name": a.name, "tool": a.tool} for a in assets],
    }


async def _generate_performance(db: AsyncSession, args: dict) -> dict:
    from app.services.performance.service import PerformanceService

    pid = uuid.UUID(args["project_id"])
    svc = PerformanceService(db)
    ds_id = uuid.UUID(args["discovery_session_id"]) if args.get("discovery_session_id") else None
    asset = await svc.generate(
        pid,
        tool=args.get("tool", "k6"),
        workload_profile=args.get("workload_profile", "load"),
        base_url=args.get("base_url", "https://example.com"),
        discovery_session_id=ds_id,
    )
    await db.commit()
    return {"ok": True, "asset_id": str(asset.id), "name": asset.name, "scenarios": len(asset.scenarios or [])}


async def _run_performance_test(db: AsyncSession, args: dict) -> dict:
    from app.services.performance.service import PerformanceService

    pid = uuid.UUID(args["project_id"])
    aid = uuid.UUID(args["asset_id"])
    svc = PerformanceService(db)
    run = await svc.execute(pid, aid, workload_profile=args.get("workload_profile", "smoke"), background=True)
    await db.commit()
    return {"ok": True, "run_id": str(run.id), "status": run.status}


async def _list_executions(db: AsyncSession, args: dict) -> dict:
    from app.services.execution import ExecutionService

    pid = uuid.UUID(args["project_id"])
    limit = int(args.get("limit", 10))
    svc = ExecutionService(db)
    runs = (await svc.list_runs(pid))[:limit]
    return {
        "ok": True,
        "runs": [
            {
                "id": str(r.id), "status": r.status, "mode": r.mode,
                "summary": r.summary, "run_name": r.run_name,
            }
            for r in runs
        ],
    }


async def _get_execution(db: AsyncSession, args: dict) -> dict:
    from app.services.execution import ExecutionService

    pid = uuid.UUID(args["project_id"])
    rid = uuid.UUID(args["run_id"])
    svc = ExecutionService(db)
    run = await svc.get_run(rid)
    if not run or run.project_id != pid:
        return {"ok": False, "error": "Run not found"}
    return {"ok": True, "run": svc.to_dict(run)}


async def _list_performance_runs(db: AsyncSession, args: dict) -> dict:
    from app.services.performance.service import PerformanceService

    pid = uuid.UUID(args["project_id"])
    svc = PerformanceService(db)
    runs = await svc.list_runs(pid)
    return {
        "ok": True,
        "runs": [svc.run_to_dict(r) for r in runs[:15]],
    }


async def _get_performance_run(db: AsyncSession, args: dict) -> dict:
    from app.services.performance.performance_dashboard import PerformanceDashboardService

    pid = uuid.UUID(args["project_id"])
    rid = uuid.UUID(args["run_id"])
    svc = PerformanceDashboardService(db)
    detail = await svc.run_detail(pid, rid)
    if not detail:
        return {"ok": False, "error": "Run not found"}
    return {"ok": True, "summary": detail.get("summary"), "transactions": detail.get("transactions", [])[:10], "run": detail.get("run")}


async def _get_execution_dashboard(db: AsyncSession, args: dict) -> dict:
    from app.services.execution_dashboard import ExecutionDashboardService

    pid = uuid.UUID(args["project_id"])
    svc = ExecutionDashboardService(db)
    return {"ok": True, "dashboard": await svc.dashboard(pid)}


async def _get_platform_capabilities(db: AsyncSession, _: dict) -> dict:
    return {"ok": True, "capabilities": get_runner_capabilities()}


async def _check_run_status(db: AsyncSession, args: dict) -> dict:
    rid = uuid.UUID(args["run_id"])
    active = is_run_active(rid)
    from app.services.performance.performance_worker import is_perf_run_active
    perf_active = is_perf_run_active(rid)
    run = await db.get(ExecutionRunModel, rid)
    status = run.status if run else None
    return {"ok": True, "run_id": str(rid), "active": active or perf_active, "status": status}


async def _list_llm_providers(db: AsyncSession, _: dict) -> dict:
    from app.llm.router import get_llm_router
    return {"ok": True, "providers": get_llm_router().list_providers()}


_TOOL_HANDLERS = {
    "list_projects": _list_projects,
    "get_project_summary": _get_project_summary,
    "list_test_cases": _list_test_cases,
    "list_discovery_sessions": _list_discovery_sessions,
    "start_discovery": _start_discovery,
    "list_automation_assets": _list_automation_assets,
    "generate_automation": _generate_automation,
    "run_automation_asset": _run_automation_asset,
    "run_batch_tests": _run_batch_tests,
    "list_performance_assets": _list_performance_assets,
    "generate_performance": _generate_performance,
    "run_performance_test": _run_performance_test,
    "list_executions": _list_executions,
    "get_execution": _get_execution,
    "list_performance_runs": _list_performance_runs,
    "get_performance_run": _get_performance_run,
    "get_execution_dashboard": _get_execution_dashboard,
    "get_platform_capabilities": _get_platform_capabilities,
    "check_run_status": _check_run_status,
    "list_llm_providers": _list_llm_providers,
}


def tools_prompt_json() -> str:
    return json.dumps([{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in TOOL_DEFINITIONS], indent=2)
