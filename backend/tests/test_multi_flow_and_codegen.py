from app.runners.discovery_prompt import extract_planned_flows, parse_discovery_prompt
from app.services.step_script_codegen import build_framework_test_file, emit_playwright_step


MULTI_FLOW_PROMPT = """
no login

Flow 1: Search Airpods
1. Open https://www.flipkart.com
2. Search for "Airpods"
3. Click a random product
4. Click Add to cart

Flow 2: Empty cart
1. Go to Cart
2. Remove 1 item from the cart
3. Assert the cart no longer shows that removed item
"""


def test_multi_flow_extraction():
    flows = extract_planned_flows(MULTI_FLOW_PROMPT)
    assert len(flows) == 2
    assert "Airpods" in flows[0].name or "1" in flows[0].name
    assert any(s.action == "search" for s in flows[0].steps)
    assert any((s.interaction or "") == "result" for s in flows[0].steps)
    assert any((s.interaction or "") == "cart" for s in flows[1].steps)
    assert any((s.interaction or "") == "cart_remove" for s in flows[1].steps)
    assert any(s.action == "verify" for s in flows[1].steps)


def test_multi_flow_parse_intent():
    intent = parse_discovery_prompt(MULTI_FLOW_PROMPT)
    assert intent.case_mode == "as_written"
    assert intent.split_test_cases is True
    assert len(intent.planned_flows) == 2
    assert len(intent.planned_steps) >= 2


def test_playwright_codegen_uses_actions():
    steps = [
        {"order": 1, "action": "navigate", "description": "Open site", "url": "https://example.com"},
        {"order": 2, "action": "search", "description": 'Search for "Airpods"', "value": "Airpods", "interaction": "search"},
        {"order": 3, "action": "verify", "description": "Assert results", "expected": "results visible"},
    ]
    line = emit_playwright_step(steps[1], "https://example.com")
    assert "fill" in line.lower() or "search" in line.lower()
    file = build_framework_test_file(
        framework="cypress",
        title="Airpods flow",
        steps=steps,
        base_url="https://example.com",
        expected=["ok"],
        index=0,
    )
    assert "cy." in file["content"]
    assert file["path"].endswith(".cy.js")


def test_selenium_codegen_emits_driver_calls():
    steps = [
        {"order": 1, "action": "navigate", "description": "Open", "url": "https://example.com"},
        {"order": 2, "action": "click", "description": "Click Cart", "element": "Cart", "interaction": "cart"},
    ]
    file = build_framework_test_file(
        framework="selenium",
        title="Cart",
        steps=steps,
        base_url="https://example.com",
        index=0,
    )
    assert "driver.get" in file["content"]
    assert file["path"].endswith(".java")
