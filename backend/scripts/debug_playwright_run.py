"""Debug script for Playwright execution failures."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runners.framework_runner import build_workspace_for_test_cases
from app.runners.playwright_runner import run_playwright, cleanup_workspace


async def main() -> None:
    tc = [{
        "title": "Login test",
        "steps": ["Open login page", "Enter credentials"],
        "expected_results": ["User logged in"],
    }]
    base_url = os.environ.get("BASE_URL", "https://example.com")
    ws = build_workspace_for_test_cases(tc, base_url, "playwright")
    print("Workspace:", ws)
    try:
        outcome = await run_playwright(ws, timeout_sec=180)
        print("available:", outcome.get("available"))
        print("exit_code:", outcome.get("exit_code"))
        print("results:", outcome.get("results"))
        print("summary:", outcome.get("summary"))
        err = outcome.get("stderr") or ""
        out = outcome.get("stdout") or ""
        print("--- stderr (last 2500) ---")
        print(err[-2500:])
        print("--- stdout (last 2500) ---")
        print(out[-2500:])
    finally:
        cleanup_workspace(ws)


if __name__ == "__main__":
    asyncio.run(main())
