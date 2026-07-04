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


def test_sanitize_prompt_strips_base_url_line():
    from app.runners.discovery_prompt import parse_discovery_prompt, sanitize_prompt_text

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
