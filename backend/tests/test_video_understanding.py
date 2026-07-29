from app.services.video_understanding import _case_from_notes_only, _parse_case_json


def test_parse_case_json_strips_fences():
    raw = """```json
{"title": "Cart flow", "steps": [{"order": 1, "action": "search", "description": "Search for \\"Galaxy\\""}], "expected_results": ["ok"]}
```"""
    data = _parse_case_json(raw)
    assert data["title"] == "Cart flow"
    assert data["steps"][0]["action"] == "search"


def test_notes_only_builds_search_and_result_steps():
    notes = """
Automation steps:
1. Open https://www.flipkart.com
2. Search for "Samsung Galaxy"
3. Click the second product in the search results
4. Click Add to cart
"""
    case = _case_from_notes_only(notes, "https://www.flipkart.com")
    assert len(case["steps"]) >= 3
    actions = [s.get("action") for s in case["steps"]]
    assert "search" in actions
    assert any((s.get("interaction") or "") == "result" for s in case["steps"])
