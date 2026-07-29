"""Generate and run tests from test case definitions with step-level results (all frameworks)."""

from app.config import settings
from app.runners.framework_runner import (
    build_workspace_for_test_cases,
    run_framework,
)
from app.runners.playwright_runner import cleanup_workspace, persist_videos


def map_steps_from_test_case(tc: dict, overall_status: str) -> list[dict]:
    """Map test case steps to statuses. Without real Playwright step data, do not fake passes."""
    from app.services.test_steps import normalize_test_steps

    steps = normalize_test_steps(tc.get("steps") or [])
    expected = tc.get("expected_results") or []
    mapped = []
    for i, step in enumerate(steps):
        desc = step.get("description") or str(step)
        if step.get("disabled"):
            mapped.append({
                "order": i + 1,
                "description": desc,
                "status": "skipped",
                "expected": expected[i] if i < len(expected) else None,
            })
            continue
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


def merge_live_step_statuses(live_steps: list[dict] | None, overall_status: str, tc: dict) -> list[dict]:
    """
    Prefer per-step statuses collected during live debug progress over all-pass / all-fail.
    Falls back to flat mapping when no live step data was recorded.
    """
    if not live_steps:
        return map_steps_from_test_case(tc, overall_status)

    has_progress = any(s.get("status") in ("passed", "failed", "running") for s in live_steps)
    if not has_progress:
        return map_steps_from_test_case(tc, overall_status)

    out: list[dict] = []
    seen_fail = False
    for step in live_steps:
        st = step.get("status") or "pending"
        if st == "skipped":
            out.append(dict(step))
            continue
        if overall_status in ("passed", "passed_with_warnings"):
            out.append({**step, "status": "passed" if overall_status == "passed" else overall_status})
            continue
        if st in ("passed", "passed_with_warnings"):
            out.append(dict(step))
        elif st == "failed":
            seen_fail = True
            out.append(dict(step))
        elif st == "running":
            seen_fail = True
            out.append({**step, "status": "failed"})
        else:
            # pending after a failure → skipped; first pending when nothing failed yet → failed
            if seen_fail:
                out.append({**step, "status": "skipped"})
            else:
                seen_fail = True
                out.append({**step, "status": "failed"})
    if overall_status == "failed" and not any(s.get("status") == "failed" for s in out):
        return map_steps_from_test_case(tc, "failed")
    return out


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
