"""Discovery prompt parsing — strict vs broad exploration."""

from app.runners.discovery_prompt import extract_explicit_targets, extract_form_fields, parse_discovery_prompt


def test_strict_by_default_for_specific_instructions():
    intent = parse_discovery_prompt("Login as admin/admin123, open Payroll and verify employee list")
    assert intent.strict_follow is True
    assert intent.broad_exploration is False
    assert intent.username == "admin"
    assert intent.password == "admin123"
    assert "payroll" in intent.goals.lower()
    assert any("payroll" in t.lower() for t in intent.explicit_targets)


def test_broad_exploration_when_explicitly_requested():
    intent = parse_discovery_prompt("Login as admin/admin123, explore all main menus and workflows")
    assert intent.broad_exploration is True
    assert intent.strict_follow is False


def test_login_only_no_broad_explore():
    intent = parse_discovery_prompt("Login as admin/admin123")
    assert intent.strict_follow is True
    assert intent.broad_exploration is False
    assert "only" in intent.summary.lower() or "login" in intent.summary.lower()


def test_extract_quoted_and_module_targets():
    targets = extract_explicit_targets('Open "Employee List" and go to Reports module')
    assert any("employee list" in t.lower() for t in targets)
    assert any("reports" in t.lower() for t in targets)


def test_strict_hint_overrides_broad():
    intent = parse_discovery_prompt("Explore all modules but only focus on Payroll")
    assert intent.strict_follow is True
    assert intent.broad_exploration is False


def test_extract_form_fields_multiline():
    text = """Submit enquiry form:
Name: Jane Doe
Email: jane@example.com
Message: Need a demo"""
    fields = extract_form_fields(text)
    labels = {f.label.lower() for f in fields}
    assert "name" in labels
    assert "email" in labels
    assert "message" in labels


def test_form_submit_intent():
    intent = parse_discovery_prompt(
        "Submit enquiry form with Name: John, Email: john@test.com, Message: Hello"
    )
    assert intent.wants_form_submit is True
    assert len(intent.form_fields) >= 3


def test_open_contact_and_submit_extracts_contact():
    intent = parse_discovery_prompt(
        "Open Contact page and submit enquiry form:\nName: Jane Doe\nEmail: jane@example.com"
    )
    assert intent.wants_form_submit is True
    assert any("contact" in t.lower() for t in intent.explicit_targets)
    from app.runners.discovery_prompt import navigation_targets

    nav = navigation_targets(intent)
    assert any("contact" in t.lower() for t in nav)


def test_instruction_mode_no_broad_explore_on_form_only():
    intent = parse_discovery_prompt(
        "Submit enquiry form:\nName: Jane\nEmail: j@test.com\nMessage: Hi"
    )
    assert intent.strict_follow is True
    assert intent.broad_exploration is False
    assert intent.wants_form_submit is True


def test_contact_us_tab_normalizes_target():
    from app.runners.discovery_prompt import navigation_targets, normalize_nav_target

    prompt = (
        "no login\n\nOpen Contact Us tab and view the contact page, then submit the enquiry form:\n"
        "Your Name: Jane Doe\nEmail: jane@example.com"
    )
    intent = parse_discovery_prompt(prompt)
    nav = navigation_targets(intent)
    assert any(normalize_nav_target(t).lower() == "contact us" for t in nav)
    assert not any("view the contact" in t.lower() for t in nav)


def test_flipkart_menu_list_targets():
    prompt = """no login

Navigate each of the below menus:
For You
Fashion
Mobiles
Beauty
Electronics
Home
Appliances
Toys, Baby & Kids
Food & Health
Auto Accessories
2 Wheelers
Sports & Fitness
Books & Media
Furniture

For each menu, open the category and verify the page loads.
Stay on flipkart.com only — do not open external links."""
    intent = parse_discovery_prompt(prompt)
    from app.runners.discovery_prompt import navigation_targets

    nav = navigation_targets(intent)
    assert intent.strict_follow is True
    assert intent.broad_exploration is False
    assert intent.menu_list_navigation is True
    assert intent.split_test_cases is False
    assert "for you" in {t.lower() for t in nav}
    assert "fashion" in {t.lower() for t in nav}
    assert "mobiles" in {t.lower() for t in nav}
    assert "furniture" in {t.lower() for t in nav}
    assert "category" not in {t.lower() for t in nav}
    assert "external links" not in {t.lower() for t in nav}
    assert "stay on flipkart.com only" not in {t.lower() for t in nav}
    assert len(nav) == 14


def test_flipkart_full_prompt_ignores_instruction_paragraphs():
    prompt = """no login

Navigate each of the below menus:
For You
Fashion
Mobiles
Beauty
Electronics
Home
Appliances
Toys, Baby & Kids
Food & Health
Auto Accessories
2 Wheelers
Sports & Fitness
Books & Media
Furniture

Create one end-to-end navigation journey starting from the Flipkart homepage.

For each menu in the list above:
1. Start from the homepage (https://www.flipkart.com).
2. Click the menu item in the top navigation bar (do not use direct category URLs).

Rules:
- Stay on flipkart.com only — do not open external links or third-party sites.
- Do not log in or create an account.

Expected outcome:
- One combined test case: Main menu navigation journey covering all menus above in a single flow.
- Each step should use click + verify (not deep-link navigation).
"""
    intent = parse_discovery_prompt(prompt)
    from app.runners.discovery_prompt import navigation_targets

    nav = navigation_targets(intent)
    assert intent.menu_list_navigation is True
    assert intent.wants_form_submit is False
    assert intent.form_fields == []
    assert len(nav) == 14
    assert not any("journey" in t.lower() for t in nav)
    assert not any("create one" in t.lower() for t in nav)


def test_split_test_cases_when_explicitly_requested():
    intent = parse_discovery_prompt(
        "Explore Flipkart and create possible test cases for each main menu"
    )
    assert intent.split_test_cases is True


def test_combined_menu_journey_test_case():
    from app.runners.qa_agent import _build_combined_navigation_test_case

    case = _build_combined_navigation_test_case(
        "https://www.flipkart.com",
        [
            ("For You", "https://www.flipkart.com/x", "For You Page"),
            ("Fashion", "https://www.flipkart.com/fashion", "Fashion Page"),
        ],
    )
    assert case["flow_kind"] == "menu_journey"
    assert len(case["steps"]) == 10  # nav, dismiss, click, verify, dismiss, home, dismiss, click, verify, dismiss
    assert case["steps"][0]["url"] == "https://www.flipkart.com"
    assert case["steps"][0]["action"] == "navigate"
    assert case["steps"][1]["action"] == "dismiss"
    assert case["steps"][2]["action"] == "click"
    assert case["steps"][2]["element"] == "For You"
    assert case["steps"][3]["action"] == "verify"
    assert case["steps"][4]["action"] == "dismiss"
    assert case["steps"][5]["action"] == "click"
    assert case["steps"][5]["interaction"] == "home"
    assert case["steps"][6]["action"] == "dismiss"
    assert case["steps"][7]["element"] == "Fashion"
    assert case["steps"][7]["interaction"] == "menu"


def test_consolidate_module_flow_into_journey():
    from app.runners.discovery_prompt import parse_discovery_prompt
    from app.runners.qa_agent import _consolidate_menu_list_cases, _menu_module_test

    intent = parse_discovery_prompt(
        "Navigate each of the below menus:\nFor You\nFashion\nMobiles"
    )
    cases = [
        _menu_module_test("For You", "https://www.flipkart.com", "For You Page", home_url="https://www.flipkart.com"),
        _menu_module_test("Fashion", "https://www.flipkart.com/fashion", "Fashion Page", home_url="https://www.flipkart.com"),
        _menu_module_test("Mobiles", "https://www.flipkart.com/mobiles", "Mobiles Page", home_url="https://www.flipkart.com"),
    ]
    merged = _consolidate_menu_list_cases(cases, "https://www.flipkart.com", intent)
    assert len(merged) == 1
    assert merged[0]["flow_kind"] == "menu_journey"
    assert merged[0]["title"].startswith("Main menu navigation journey")
    assert len(merged[0]["steps"]) >= 7


def test_sanitize_prompt_strips_base_url_line():
    from app.runners.discovery_prompt import sanitize_prompt_text

    raw = """Base URL: https://www.vivilextech.com/contact-us.html
Prompt:
Submit contact form:
Your Name: Jane Doe
E-mail: jane@example.com
Message: Hello"""
    cleaned = sanitize_prompt_text(raw)
    assert "Base URL" not in cleaned.split("\n")[0]
    intent = parse_discovery_prompt(raw)
    labels = {f.label.lower() for f in intent.form_fields}
    assert "base url" not in labels
    assert "your name" in labels
    assert not any("debug" in t.lower() for t in intent.explicit_targets)
