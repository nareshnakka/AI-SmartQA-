"""Runtime capability detection for runners."""

import asyncio
import shutil

from app.runners.setup_status import (
    _check_playwright_python,
    _playwright_browsers_on_disk,
    check_playwright_async,
    collect_runner_status,
)


def node_available() -> bool:
    return shutil.which("npx") is not None or shutil.which("node") is not None


def playwright_python_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def playwright_browsers_installed() -> bool:
    ok, _ = _playwright_browsers_on_disk()
    return ok


async def check_playwright_ready_async() -> tuple[bool, str]:
    """Playwright readiness for API routes — disk check first, then async launch."""
    return await check_playwright_async()


def check_playwright_ready() -> tuple[bool, str]:
    """Sync readiness probe; avoids sync Playwright inside a running event loop."""
    try:
        asyncio.get_running_loop()
        return _playwright_browsers_on_disk()
    except RuntimeError:
        return _check_playwright_python()


def get_runner_capabilities() -> dict:
    return collect_runner_status()


def get_framework_capabilities() -> dict[str, dict]:
    status = collect_runner_status()
    return status.get("frameworks", {})
