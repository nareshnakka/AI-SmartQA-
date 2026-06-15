"""Localhost runner agent — default execution agent for automation and performance."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LoadAgentModel
from app.runners.capabilities import get_framework_capabilities, get_runner_capabilities, node_available

LOCALHOST_AGENT_NAME = "QEOS Localhost Agent"


async def ensure_localhost_agent(db: AsyncSession, project_id=None) -> LoadAgentModel:
    result = await db.execute(
        select(LoadAgentModel).where(
            LoadAgentModel.name == LOCALHOST_AGENT_NAME,
            LoadAgentModel.host == "localhost",
        )
    )
    agent = result.scalar_one_or_none()
    caps = get_runner_capabilities()
    fw_caps = get_framework_capabilities()
    capabilities = {
        "automation": True,
        "performance": True,
        "playwright": fw_caps.get("playwright", {}).get("live", False),
        "k6": caps.get("k6_available", False),
        "node": node_available(),
        "frameworks": {k: v.get("live", False) for k, v in fw_caps.items()},
    }
    now = datetime.now(timezone.utc)
    if agent:
        agent.status = "online"
        agent.last_heartbeat = now
        agent.capabilities = capabilities
        await db.flush()
        return agent
    agent = LoadAgentModel(
        project_id=project_id,
        name=LOCALHOST_AGENT_NAME,
        host="localhost",
        port=0,
        agent_type="localhost",
        max_vus=500,
        status="online",
        capabilities=capabilities,
        last_heartbeat=now,
    )
    db.add(agent)
    await db.flush()
    return agent


async def agent_status(db: AsyncSession) -> dict:
    agent = await ensure_localhost_agent(db)
    caps = agent.capabilities or {}
    return {
        "id": str(agent.id),
        "name": agent.name,
        "host": agent.host,
        "status": agent.status,
        "agent_type": agent.agent_type,
        "capabilities": caps,
        "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        "install_hint": "Install Node.js for Playwright, Cypress, Puppeteer, TestCafe, and WebdriverIO. Maven for Selenium. pip for Robot Framework and Appium.",
        "ready": caps.get("node", False) or any((caps.get("frameworks") or {}).values()),
        "framework_capabilities": get_framework_capabilities(),
    }
