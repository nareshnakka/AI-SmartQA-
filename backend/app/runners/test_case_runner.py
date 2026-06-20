"""Generate and run tests from test case definitions with step-level results (all frameworks)."""

from app.config import settings
from app.runners.framework_runner import (
    build_workspace_for_test_cases,
    run_framework,
)
from app.runners.playwright_runner import cleanup_workspace, persist_videos


def map_steps_from_test_case(tc: dict, overall_status: str) -> list[dict]:
    """Map test case steps to statuses. Without real Playwright step data, do not fake passes."""
    steps = tc.get("steps") or []
    expected = tc.get("expected_results") or []
    mapped = []
    for i, step in enumerate(steps):
        if isinstance(step, dict):
            desc = step.get("description") or str(step)
            if step.get("disabled"):
                mapped.append({
                    "order": i + 1,
                    "description": desc,
                    "status": "skipped",
                    "expected": expected[i] if i < len(expected) else None,
                })
                continue
        else:
            desc = step if isinstance(step, str) else step.get("description", str(step))
        if overall_status == "passed":
            st = "passed"
        elif overall_status in ("failed", "passed_with_warnings"):
            st = "failed" if overall_status == "failed" else "passed_with_warnings"
        elif overall_status in ("pending", "running"):
            st = "pending"
        else:
            st = overall_status
        mapped.append({
            "order": i + 1,
            "description": desc,
            "status": st,
            "expected": expected[i] if i < len(expected) else None,
        })
    return mapped


async def run_single_test_case_workspace(workspace, framework: str = "playwright") -> dict:
    return await run_framework(workspace, framework, timeout_sec=settings.execution_timeout_sec)


def parse_framework_steps(raw_results: list[dict], tc: dict, exit_code: int | None = None) -> list[dict]:
    """Prefer runner step data; fall back to test case step mapping."""
    if raw_results:
        r = raw_results[0]
        status = r.get("status", "failed")
        return map_steps_from_test_case(tc, status)
    overall = "passed" if exit_code == 0 else "failed"
    return map_steps_from_test_case(tc, overall)


# Backward-compatible alias
parse_playwright_steps = parse_framework_steps
