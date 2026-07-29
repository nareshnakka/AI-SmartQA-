from app.services.llm_discovery_advisor import _planned_from_llm_steps, _row_to_planned


def test_llm_steps_reject_search_for_results():
    planned = _planned_from_llm_steps(
        [
            {"order": 1, "action": "navigate", "description": "Open Flipkart", "url": "https://www.flipkart.com"},
            {"order": 2, "action": "search", "description": 'Search for "Samsung Galaxy"', "value": "Samsung Galaxy"},
            {"order": 3, "action": "search", "description": 'Search for "results"', "value": "results"},
            {"order": 4, "action": "navigate", "description": "Go to Cart", "url": "https://www.flipkart.com"},
        ],
        "https://www.flipkart.com",
    )
    actions = [(s.action, s.interaction, s.description) for s in planned]
    assert any(a == "search" and "Samsung" in d for a, _, d in actions)
    assert not any(a == "search" and "result" in d.lower() for a, _, d in actions)
    assert any(i == "result" for _, i, _ in actions)
    assert any(i == "cart" for _, i, _ in actions)


def test_row_to_planned_hardens_go_to_cart():
    step = _row_to_planned(1, {"action": "navigate", "description": "Go to Cart", "url": "https://www.flipkart.com"})
    assert step.action == "click"
    assert step.interaction == "cart"
    assert step.url is None
