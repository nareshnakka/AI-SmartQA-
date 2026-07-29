"""Tests for live debug step status merging."""

from app.runners.test_case_runner import map_steps_from_test_case, merge_live_step_statuses


def _tc(steps: list[str]) -> dict:
    return {
        "id": "tc-1",
        "title": "Sample",
        "steps": [{"order": i + 1, "description": s} for i, s in enumerate(steps)],
        "expected_results": [],
    }


def test_merge_preserves_passed_before_failure():
    tc = _tc(["Open", "Search", "Add to cart"])
    live = [
        {"order": 1, "description": "Open", "status": "passed"},
        {"order": 2, "description": "Search", "status": "failed"},
        {"order": 3, "description": "Add to cart", "status": "pending"},
    ]
    merged = merge_live_step_statuses(live, "failed", tc)
    assert [s["status"] for s in merged] == ["passed", "failed", "skipped"]


def test_merge_marks_running_as_failed():
    tc = _tc(["Open", "Search"])
    live = [
        {"order": 1, "description": "Open", "status": "passed"},
        {"order": 2, "description": "Search", "status": "running"},
    ]
    merged = merge_live_step_statuses(live, "failed", tc)
    assert [s["status"] for s in merged] == ["passed", "failed"]


def test_merge_falls_back_when_no_live_progress():
    tc = _tc(["Open", "Search"])
    live = [
        {"order": 1, "description": "Open", "status": "pending"},
        {"order": 2, "description": "Search", "status": "pending"},
    ]
    merged = merge_live_step_statuses(live, "failed", tc)
    assert all(s["status"] == "failed" for s in merged)
    assert merged == map_steps_from_test_case(tc, "failed")


def test_merge_all_passed_on_success():
    tc = _tc(["Open", "Search"])
    live = [
        {"order": 1, "description": "Open", "status": "passed"},
        {"order": 2, "description": "Search", "status": "running"},
    ]
    merged = merge_live_step_statuses(live, "passed", tc)
    assert all(s["status"] == "passed" for s in merged)
