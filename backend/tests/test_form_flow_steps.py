"""Form flow test case step generation."""

from app.runners.discovery_prompt import FormFieldSpec, parse_discovery_prompt
from app.runners.qa_agent import _build_form_flow_test_case
from app.services.test_steps import steps_for_storage


def test_build_form_flow_steps_vivilex_shape():
    intent = parse_discovery_prompt(
        "no login\nOpen Contact Us tab and submit contact form:\n"
        "Your Name: Jane Doe\nE-mail: jane@example.com\nMobile Number: 9876543210\n"
        "Organization Name: Acme\nMessage: Hello"
    )
    log = [
        {"type": "click", "message": 'Click "Send Message"', "url": "https://www.vivilextech.com/contact-us.html"},
    ]
    case = _build_form_flow_test_case(
        "https://www.vivilextech.com/",
        intent,
        "https://www.vivilextech.com/contact-us.html",
        True,
        log,
    )
    assert case["flow_kind"] == "form_submit"
    actions = [s["action"] for s in case["steps"]]
    assert actions[0] == "navigate"
    assert "click" in actions
    assert actions.count("fill") == 5
    assert actions[-2] == "click"
    assert actions[-1] == "verify"
    assert any("Send Message" in s.get("element", "") for s in case["steps"] if s["action"] == "click" and "Send" in s.get("element", ""))


def test_steps_for_storage_keeps_field_and_element():
    stored = steps_for_storage([
        {"order": 1, "action": "fill", "description": "Enter Name: Jane", "field": "Your Name"},
        {"order": 2, "action": "click", "description": "Click Send Message", "element": "Send Message"},
    ])
    assert stored[0]["field"] == "Your Name"
    assert stored[1]["element"] == "Send Message"
