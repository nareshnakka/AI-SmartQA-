from app.runners.discovery_prompt import extract_planned_steps, parse_discovery_prompt


AIRPODS_PROMPT = """no login

Automation steps:
1. Open https://www.flipkart.com
2. Assert the Flipkart homepage is loaded (page title or logo is visible, no error page)
3. Dismiss any login, location, cookie, or overlay popups if visible
4. Search for "Airpods"
5. Assert search results for Airpods are displayed (product cards or result list is visible)
6. Click a random product from the search results
7. Assert the product detail page is loaded (product title and price are visible)
8. Change the buying quantity to 2
9. Assert the quantity shows 2
10. Click Add to cart
11. Assert the item was added to cart (cart confirmation or cart count updates)
12. Go to Cart
13. Assert the cart page is loaded and cart items are listed
14. Remove 1 item from the cart (or reduce quantity by 1 / remove one line item)
15. Assert the cart no longer shows that removed item (or quantity/count decreased)
"""


def test_airpods_flow_planned_steps():
    steps = extract_planned_steps(AIRPODS_PROMPT)
    assert len(steps) >= 12

    by_action = {}
    for s in steps:
        by_action.setdefault(s.action, []).append(s)

    assert any(s.action == "navigate" or (s.url and "flipkart" in (s.url or "")) for s in steps)
    assert "verify" in by_action and len(by_action["verify"]) >= 6
    # Homepage assert must be verify — never "click home"
    home_assert = next(s for s in steps if "homepage" in (s.description or "").lower())
    assert home_assert.action == "verify"
    assert home_assert.interaction != "home"

    assert "search" in by_action
    search = by_action["search"][0]
    assert "airpods" in (search.value or search.description).lower()

    result = next(s for s in steps if (s.interaction or "") == "result")
    assert result.element == "random"
    assert "random" in result.description.lower()

    qty = next(s for s in steps if (s.interaction or "") == "quantity")
    assert qty.value == "2" or qty.element == "2"

    assert any((s.interaction or "") == "cart" for s in steps)
    assert any((s.interaction or "") == "cart_remove" for s in steps)
    assert any("add to cart" in (s.description or "").lower() for s in steps)

    intent = parse_discovery_prompt(AIRPODS_PROMPT)
    assert intent.case_mode == "as_written"
    assert len(intent.planned_steps) >= 12
