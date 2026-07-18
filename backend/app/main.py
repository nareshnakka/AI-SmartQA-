from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, audit, auth, automation, copilot, cursor, discovery, environments, executions, integrations, intelligence, llm, modules, monitoring, naming_patterns, performance, pipelines, platform, projects, quality_studio, reports, support, test_generation, updates
from app.config import settings
from app.core.security import AuthMiddleware
from app.db.session import init_db
from app.models.schemas import HealthResponse
from app.version import version_info, version_label
from app.plugins.loader import discover_plugins
from app.services.integration_store import hydrate_integration_manager
from app.services.log_buffer import structlog_buffer_processor

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog_buffer_processor,
        structlog.processors.JSONRenderer(),
    ],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.runners.setup_status import configure_playwright_browsers_env

    pw_ok, pw_hint = configure_playwright_browsers_env()
    if not pw_ok:
        structlog.get_logger().warning("playwright_browsers_not_ready", hint=pw_hint)
    else:
        import os
        structlog.get_logger().info(
            "playwright_browsers_configured",
            path=os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
        )

    await init_db()
    count = discover_plugins()
    integrations_loaded = await hydrate_integration_manager()
    structlog.get_logger().info(
        "platform_started",
        plugins_discovered=count,
        integrations_loaded=integrations_loaded,
        phase="5-started",
    )
    yield


app = FastAPI(
    title=settings.app_name,
    description="Enterprise AI Quality Engineering Operating System",
    version=version_label(),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

app.include_router(projects.router, prefix="/api/v1")
app.include_router(quality_studio.router, prefix="/api/v1")
app.include_router(test_generation.router, prefix="/api/v1")
app.include_router(modules.router, prefix="/api/v1")
app.include_router(naming_patterns.router, prefix="/api/v1")
app.include_router(automation.router, prefix="/api/v1")
app.include_router(performance.router, prefix="/api/v1")
app.include_router(pipelines.router, prefix="/api/v1")
app.include_router(discovery.router, prefix="/api/v1")
app.include_router(cursor.router, prefix="/api/v1")
app.include_router(executions.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(environments.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(monitoring.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(copilot.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(llm.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")
app.include_router(platform.router, prefix="/api/v1")
app.include_router(updates.router, prefix="/api/v1")
app.include_router(support.router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    from app.runners.capabilities import get_runner_capabilities, playwright_python_available
    from app.runners.setup_status import _playwright_browsers_on_disk

    # Fast on-disk check — never use sync Playwright on the uvicorn event loop.
    pw_ok, pw_hint = _playwright_browsers_on_disk()
    caps = get_runner_capabilities()
    info = version_info()
    return HealthResponse(
        status="healthy",
        version=info["feature_version"],
        version_label=info["label"],
        build=info["build"],
        timestamp=datetime.now(timezone.utc),
        execution_executor="asset_live_v2",
        playwright_python=playwright_python_available(),
        playwright_browsers=pw_ok,
        playwright_hint=pw_hint if not pw_ok else None,
        runners_ready={
            "automation": {k: v["ready"] for k, v in caps.get("automation", {}).items()},
            "performance": {k: v["ready"] for k, v in caps.get("performance", {}).items()},
        },
    )


@app.get("/api/v1/phase1/status", tags=["Phase 1"])
async def phase1_status():
    from sqlalchemy import func, select
    from app.db.session import AsyncSessionLocal
    from app.db.models import ProjectModel, TestCaseModel, RequirementModel

    async with AsyncSessionLocal() as db:
        projects = await db.scalar(select(func.count()).select_from(ProjectModel)) or 0
        cases = await db.scalar(select(func.count()).select_from(TestCaseModel)) or 0
        reqs = await db.scalar(select(func.count()).select_from(RequirementModel)) or 0

    return {
        "phase": 1,
        "name": "AI Test Generation",
        "status": "complete",
        "capabilities": [
            "Requirement ingestion (text, file upload, user stories, BDD)",
            "AI test scenario and test case generation",
            "Risk analysis and coverage matrix",
            "Test design (regression/smoke packs)",
            "Project persistence (SQLite/PostgreSQL)",
            "Export JSON and CSV",
            "Agent run history",
        ],
        "stats": {"projects": projects, "requirements": reqs, "test_cases": cases},
    }


@app.get("/api/v1/phase2/status", tags=["Phase 2"])
async def phase2_status():
    from sqlalchemy import func, select
    from app.db.session import AsyncSessionLocal
    from app.db.models import AutomationAssetModel

    async with AsyncSessionLocal() as db:
        assets = await db.scalar(select(func.count()).select_from(AutomationAssetModel)) or 0

    return {
        "phase": 2,
        "name": "AI Automation Generation",
        "status": "complete",
        "frameworks": ["playwright", "selenium", "cypress", "webdriverio", "robot_framework", "appium", "puppeteer", "testcafe"],
        "capabilities": [
            "Generate automation from test cases",
            "8 framework support with page objects",
            "QA Studio IDE with file editor",
            "Version history and diff",
            "Script validation",
            "CI pipeline snippet generation",
        ],
        "stats": {"automation_assets": assets},
    }


@app.get("/api/v1/phase3/status", tags=["Phase 3"])
async def phase3_status():
    from sqlalchemy import func, select
    from app.db.session import AsyncSessionLocal
    from app.db.models import PerformanceAssetModel

    async with AsyncSessionLocal() as db:
        assets = await db.scalar(select(func.count()).select_from(PerformanceAssetModel)) or 0

    return {
        "phase": 3,
        "name": "AI Performance Engineering",
        "status": "complete",
        "tools": ["k6", "jmeter", "gatling", "locust"],
        "capabilities": [
            "Generate load scripts from functional test cases",
            "Workload models and flow distribution",
            "Correlation rules and parameterization",
            "Functional-to-performance conversion",
        ],
        "stats": {"performance_assets": assets},
    }


@app.get("/api/v1/phase4/status", tags=["Phase 4"])
async def phase4_status():
    from sqlalchemy import func, select
    from app.db.session import AsyncSessionLocal
    from app.db.models import PipelineRunModel

    async with AsyncSessionLocal() as db:
        runs = await db.scalar(select(func.count()).select_from(PipelineRunModel)) or 0

    return {
        "phase": 4,
        "name": "Multi-Agent Autonomous Quality System",
        "status": "complete",
        "pipelines": list(__import__("app.services.pipeline", fromlist=["DEFAULT_PIPELINES"]).DEFAULT_PIPELINES.keys()),
        "capabilities": [
            "Orchestrated multi-agent pipelines",
            "Requirements → Test Design → Automation → Performance",
            "Pipeline run history and step tracking",
            "Configurable pipeline templates",
        ],
        "stats": {"pipeline_runs": runs},
    }


@app.get("/api/v1/phase5/status", tags=["Phase 5"])
async def phase5_status():
    from sqlalchemy import func, select
    from app.db.session import AsyncSessionLocal
    from app.db.models import DiscoverySessionModel, ExecutionRunModel, IntegrationModel, MonitoringEventModel, UserModel

    async with AsyncSessionLocal() as db:
        discoveries = await db.scalar(select(func.count()).select_from(DiscoverySessionModel)) or 0
        executions = await db.scalar(select(func.count()).select_from(ExecutionRunModel)) or 0
        integrations = await db.scalar(select(func.count()).select_from(IntegrationModel)) or 0
        events = await db.scalar(select(func.count()).select_from(MonitoringEventModel)) or 0
        users = await db.scalar(select(func.count()).select_from(UserModel)) or 0

    from app.runners.capabilities import get_runner_capabilities
    caps = get_runner_capabilities()

    return {
        "phase": 5,
        "name": "Fully Autonomous Quality System",
        "status": "complete",
        "capabilities": [
            "Application discovery (static + live browser crawl)",
            "Discovery → auto-generate tests and automation",
            "Live Playwright test execution via Node.js",
            "Dry-run execution with self-healing patches applied",
            "Live quality reports (tester, engineering, executive)",
            "Persistent integrations (survive restart)",
            "Automation zip export and GitHub push",
            "Production monitoring event ingestion",
            "Datadog and Sentry webhook connectors",
            "RBAC with JWT auth and project-scoped access",
            "OIDC SSO (Azure AD, Okta, Google)",
            "Environment profiles and audit logging",
            "Global platform search",
        ],
        "runners": caps,
        "stats": {
            "discovery_sessions": discoveries,
            "execution_runs": executions,
            "persisted_integrations": integrations,
            "monitoring_events": events,
            "users": users,
        },
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.app_name,
        "description": "Quality Engineering Operating System",
        "docs": "/docs",
        "phase": "Phase 5 — Autonomous Quality (Complete)",
        "intelligence": "QEOS Native (no external LLM required)",
    }
