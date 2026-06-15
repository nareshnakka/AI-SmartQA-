"""QEOS platform integration tests."""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

# Use isolated test database
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_qeos.db")
os.environ.setdefault("QEOS_AUTH_ENABLED", "false")

from app.main import app  # noqa: E402
from app.db.session import init_db  # noqa: E402


@pytest.fixture(scope="session")
async def setup_db():
    if os.path.exists("test_qeos.db"):
        os.remove("test_qeos.db")
    await init_db()


@pytest.fixture
async def client(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_phase_statuses(client: AsyncClient):
    for phase in range(1, 6):
        r = await client.get(f"/api/v1/phase{phase}/status")
        assert r.status_code == 200
        data = r.json()
        assert data["phase"] == phase
    p5 = (await client.get("/api/v1/phase5/status")).json()
    assert p5["status"] == "complete"


@pytest.mark.asyncio
async def test_full_workflow(client: AsyncClient):
    """Phase 1 → 2 → 3 → 4 → 5 end-to-end."""
    # Create project
    r = await client.post("/api/v1/projects", json={"name": "E2E Test Project", "description": "Integration test"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    # Phase 1: Generate tests
    r = await client.post(
        f"/api/v1/projects/{project_id}/generate",
        json={
            "content": "As a user, I want to login and checkout, so that I can purchase items.",
            "source_type": "user_story",
        },
    )
    assert r.status_code == 200
    assert len(r.json().get("test_cases", [])) > 0

    # Phase 2: Automation
    r = await client.post(
        f"/api/v1/projects/{project_id}/automation/generate",
        json={"framework": "playwright"},
    )
    assert r.status_code == 200
    asset_id = r.json()["id"]

    # Phase 3: Performance
    r = await client.post(
        f"/api/v1/projects/{project_id}/performance/generate",
        json={"tool": "k6"},
    )
    assert r.status_code == 200
    perf_id = r.json()["id"]

    # Performance update
    scripts = r.json()["scripts"]
    r = await client.get(f"/api/v1/projects/{project_id}/performance/workload-profiles")
    assert r.status_code == 200
    assert "smoke" in [p["id"] for p in r.json()["profiles"]]

    r = await client.post(
        f"/api/v1/projects/{project_id}/performance/assets/{perf_id}/execute",
        json={"workload_profile": "smoke", "background": False},
    )
    assert r.status_code == 200

    # Phase 2B: automation from OpenAPI source
    openapi_sample = {
        "openapi": "3.0.0",
        "paths": {
            "/api/users": {
                "get": {"summary": "List users", "responses": {"200": {"description": "OK"}}}
            }
        },
    }
    r = await client.post(
        f"/api/v1/projects/{project_id}/automation/generate-from-source",
        json={"source_type": "openapi", "content": openapi_sample, "framework": "playwright"},
    )
    assert r.status_code == 200
    assert len(r.json().get("files", [])) > 0
    scripts[0]["content"] = scripts[0]["content"] + "\n// updated"
    r = await client.put(
        f"/api/v1/projects/{project_id}/performance/assets/{perf_id}",
        json={"scripts": scripts},
    )
    assert r.status_code == 200
    assert r.json()["version"] >= 2

    # Phase 4: Pipeline
    r = await client.post(
        f"/api/v1/projects/{project_id}/pipelines/run",
        json={
            "pipeline_key": "test_to_automation",
            "content": "As a user, I want to search products, so that I can find items quickly.",
        },
    )
    assert r.status_code == 200

    # Phase 5: Discovery
    r = await client.post(
        f"/api/v1/projects/{project_id}/discovery/run",
        json={"base_url": "https://shop.example.com", "mode": "static", "requirements": "login checkout payment", "background": False},
    )
    assert r.status_code == 200
    session_id = r.json()["id"]

    # Discovery → generate tests
    r = await client.post(
        f"/api/v1/projects/{project_id}/discovery/sessions/{session_id}/generate-tests",
        json={"generate_automation": False},
    )
    assert r.status_code == 200
    assert r.json()["test_cases_created"] >= 0

    # Execution dry-run with healing
    r = await client.post(
        f"/api/v1/projects/{project_id}/executions/run",
        json={"asset_id": asset_id, "mode": "dry_run", "apply_healing": True},
    )
    assert r.status_code == 200
    assert r.json()["status"] in ("completed", "failed")

    # Reports
    r = await client.get("/api/v1/reports/overview")
    assert r.status_code == 200
    assert "quality_score" in r.json()

    r = await client.get(f"/api/v1/reports/projects/{project_id}")
    assert r.status_code == 200

    # Search
    r = await client.get("/api/v1/platform/search?q=E2E")
    assert r.status_code == 200
    assert len(r.json()["results"]) >= 1

    # Environments
    r = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        json={"name": "DEV", "env_type": "dev", "base_url": "https://dev.example.com", "is_default": True},
    )
    assert r.status_code == 201

    r = await client.get(f"/api/v1/projects/{project_id}/environments")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # Agent run persistence
    r = await client.post(
        "/api/v1/agents/run",
        json={
            "agent_type": "requirements",
            "project_id": project_id,
            "input_data": {"content": "Quick agent test", "source_type": "user_story"},
        },
    )
    assert r.status_code == 200
    run_id = r.json()["id"]

    r = await client.get(f"/api/v1/agents/runs?project_id={project_id}")
    assert r.status_code == 200
    assert any(str(x["id"]) == str(run_id) for x in r.json())


@pytest.mark.asyncio
async def test_auth_status(client: AsyncClient):
    r = await client.get("/api/v1/auth/status")
    assert r.status_code == 200
    assert "user" in r.json()
