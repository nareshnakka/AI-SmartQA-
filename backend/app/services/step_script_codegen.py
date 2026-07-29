"""Emit framework-specific automation code from normalized Discovery / Studio steps."""

from __future__ import annotations

import re
from typing import Any


def _escape(s: str) -> str:
    return (
        (s or "")
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", " ")
    )


def _safe_name(title: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", title or "Test")[:max_len] or "Test"


def _step_dicts(steps: list[Any]) -> list[dict]:
    out: list[dict] = []
    for i, raw in enumerate(steps or [], start=1):
        if isinstance(raw, dict):
            out.append(raw)
        elif isinstance(raw, str):
            out.append({"order": i, "action": "click", "description": raw})
        else:
            out.append({"order": i, "action": "click", "description": str(raw)})
    return out


def emit_playwright_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or f"Step {step.get('order', '')}")
    url = step.get("url") or ""
    element = _escape(step.get("element") or "")
    value = _escape(step.get("value") or "")
    field = _escape(step.get("field") or "")
    interaction = (step.get("interaction") or "").lower()
    expected = _escape(step.get("expected") or desc)

    if action == "navigate":
        target = url or base_url
        return f"await page.goto('{_escape(target)}'); await page.waitForLoadState('domcontentloaded');"
    if action == "dismiss" or interaction == "popup":
        return (
            "// Dismiss overlays if present\n"
            "    await page.keyboard.press('Escape').catch(() => {});"
        )
    if action == "search" or interaction == "search":
        q = value or field or desc
        return (
            f"await page.getByRole('textbox', {{ name: /search/i }}).first().fill('{q}');\n"
            f"    await page.keyboard.press('Enter');\n"
            f"    await page.waitForLoadState('domcontentloaded');"
        )
    if interaction == "result":
        idx = element or "1"
        return (
            f"// Open search result #{idx}\n"
            f"    await page.locator('div[data-id], a[href*=\"/p/\"]').first().click({{ timeout: 20000 }});"
        )
    if interaction == "quantity":
        n = value or element or "2"
        return (
            f"// Set quantity to {n}\n"
            f"    const qty = page.locator('select[name*=qty i], input[name*=qty i]').first();\n"
            f"    if (await qty.count()) {{ await qty.selectOption('{n}').catch(async () => {{ await qty.fill('{n}'); }}); }}"
        )
    if interaction == "cart":
        return "await page.getByRole('link', { name: /cart/i }).first().click();"
    if interaction == "cart_remove":
        return "await page.getByRole('button', { name: /remove|delete/i }).first().click();"
    if action in ("fill", "type"):
        sel = field or element or "input"
        val = value or ""
        return (
            f"await page.getByLabel(/{_escape(sel)}/i).first().fill('{val}').catch(async () => {{\n"
            f"      await page.locator('input, textarea').first().fill('{val}');\n"
            f"    }});"
        )
    if action == "verify":
        return f"await expect(page.locator('body')).toBeVisible(); // {expected}"
    if action == "click" or element:
        label = element or desc
        return (
            f"await page.getByRole('button', {{ name: /{_escape(label)}/i }}).first().click({{ timeout: 15000 }}).catch(async () => {{\n"
            f"      await page.getByRole('link', {{ name: /{_escape(label)}/i }}).first().click();\n"
            f"    }});"
        )
    return f"// {desc}\n    await expect(page.locator('body')).toBeVisible();"


def emit_cypress_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or "")
    url = step.get("url") or base_url
    element = _escape(step.get("element") or "")
    value = _escape(step.get("value") or "")
    interaction = (step.get("interaction") or "").lower()

    if action == "navigate":
        return f"cy.visit('{_escape(url or base_url)}');"
    if action == "search" or interaction == "search":
        q = value or desc
        return f"cy.get('input[type=search], input[placeholder*=Search i]').first().type('{q}{{enter}}');"
    if interaction == "cart":
        return "cy.contains('a,button', /cart/i).first().click();"
    if interaction == "cart_remove":
        return "cy.contains('button,a', /remove|delete/i).first().click();"
    if action in ("fill", "type"):
        return f"cy.get('input,textarea').first().type('{value}');"
    if action == "verify":
        return f"cy.get('body').should('be.visible'); // {desc}"
    if action == "click" or element:
        label = element or desc
        return f"cy.contains('button,a,span', /{_escape(label)}/i).first().click();"
    return f"cy.log('{desc}');"


def emit_selenium_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or "")
    url = step.get("url") or base_url
    element = _escape(step.get("element") or "")
    value = _escape(step.get("value") or "")
    interaction = (step.get("interaction") or "").lower()

    if action == "navigate":
        return f'driver.get("{_escape(url or base_url)}");'
    if action == "search" or interaction == "search":
        q = value or desc
        return (
            f'WebElement search = driver.findElement(By.cssSelector("input[type=search], input[name*=q]"));\n'
            f'        search.clear(); search.sendKeys("{q}"); search.sendKeys(Keys.ENTER);'
        )
    if action in ("fill", "type"):
        return (
            f'WebElement field = driver.findElement(By.cssSelector("input, textarea"));\n'
            f'        field.clear(); field.sendKeys("{value}");'
        )
    if action == "verify":
        return f'Assert.assertTrue(driver.findElement(By.tagName("body")).isDisplayed()); // {desc}'
    if action == "click" or element:
        label = element or desc
        low = _escape(label.lower())
        return (
            f'driver.findElement(By.xpath("//*[contains(translate(normalize-space(.),'
            f" 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{low}')]\")).click();"
        )
    return f'// {desc}'


def emit_webdriverio_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or "")
    url = step.get("url") or base_url
    element = _escape(step.get("element") or "")
    value = _escape(step.get("value") or "")
    interaction = (step.get("interaction") or "").lower()

    if action == "navigate":
        return f"await browser.url('{_escape(url or base_url)}');"
    if action == "search" or interaction == "search":
        q = value or desc
        return (
            f"const box = await $('input[type=search], input[placeholder*=Search]');\n"
            f"        await box.setValue('{q}');\n"
            f"        await browser.keys('Enter');"
        )
    if action in ("fill", "type"):
        return f"await $('input, textarea').setValue('{value}');"
    if action == "verify":
        return f"await expect($('body')).toBeDisplayed(); // {desc}"
    if action == "click" or element:
        label = element or desc
        return f"await $(`*={_escape(label)}`).click();"
    return f"console.log('{desc}');"


def emit_robot_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = step.get("description") or ""
    url = step.get("url") or base_url
    element = step.get("element") or ""
    value = step.get("value") or ""
    interaction = (step.get("interaction") or "").lower()

    if action == "navigate":
        return f"    Go To    {url or base_url}"
    if action == "search" or interaction == "search":
        q = value or desc
        return (
            f"    Fill Text    css=input[type=search]    {q}\n"
            f"    Press Keys    css=input[type=search]    Enter"
        )
    if action in ("fill", "type"):
        return f"    Fill Text    css=input,textarea    {value}"
    if action == "verify":
        return f"    Get Text    body    # {desc}"
    if action == "click" or element:
        label = element or desc
        return f"    Click    text={label}"
    return f"    Log    {desc}"


def emit_puppeteer_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or "")
    url = step.get("url") or base_url
    element = _escape(step.get("element") or "")
    value = _escape(step.get("value") or "")
    interaction = (step.get("interaction") or "").lower()

    if action == "navigate":
        return f"await page.goto('{_escape(url or base_url)}', {{ waitUntil: 'domcontentloaded' }});"
    if action == "search" or interaction == "search":
        q = value or desc
        return (
            f"await page.type('input[type=search], input[name*=q]', '{q}');\n"
            f"    await page.keyboard.press('Enter');"
        )
    if action in ("fill", "type"):
        return f"await page.type('input, textarea', '{value}');"
    if action == "verify":
        return f"await page.waitForSelector('body'); // {desc}"
    if action == "click" or element:
        label = element or desc
        return f"await page.click('text/{_escape(label)}');"
    return f"console.log('{desc}');"


def emit_testcafe_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or "")
    url = step.get("url") or base_url
    element = _escape(step.get("element") or "")
    value = _escape(step.get("value") or "")
    interaction = (step.get("interaction") or "").lower()

    if action == "navigate":
        return f"await t.navigateTo('{_escape(url or base_url)}');"
    if action == "search" or interaction == "search":
        q = value or desc
        return (
            f"await t.typeText(Selector('input').withAttribute('type', 'search'), '{q}')\n"
            f"    .pressKey('enter');"
        )
    if action in ("fill", "type"):
        return f"await t.typeText(Selector('input'), '{value}');"
    if action == "verify":
        return f"await t.expect(Selector('body').exists).ok(); // {desc}"
    if action == "click" or element:
        label = element or desc
        return f"await t.click(Selector('button,a').withText(/{_escape(label)}/i));"
    return f"await t.expect(true).ok(); // {desc}"


def emit_appium_step(step: dict, base_url: str) -> str:
    action = (step.get("action") or "click").lower()
    desc = _escape(step.get("description") or "")
    url = step.get("url") or base_url
    value = _escape(step.get("value") or "")
    if action == "navigate":
        return f'    driver.get("{_escape(url or base_url)}")'
    if action in ("search", "fill", "type"):
        return f'    driver.find_element("css selector", "input").send_keys("{value}")'
    if action == "verify":
        return f'    assert driver.find_element("tag name", "body").is_displayed()  # {desc}'
    return f"    # {desc}"


_EMITTERS = {
    "playwright": emit_playwright_step,
    "cypress": emit_cypress_step,
    "selenium": emit_selenium_step,
    "webdriverio": emit_webdriverio_step,
    "robot_framework": emit_robot_step,
    "puppeteer": emit_puppeteer_step,
    "testcafe": emit_testcafe_step,
    "appium": emit_appium_step,
}


def emit_step_line(framework: str, step: dict, base_url: str) -> str:
    fn = _EMITTERS.get(framework, emit_playwright_step)
    return fn(step, base_url)


def build_framework_test_file(
    *,
    framework: str,
    title: str,
    steps: list[Any],
    base_url: str,
    expected: list[str] | None = None,
    index: int = 0,
) -> dict:
    """Build one test file dict {path, content, type} for the selected framework."""
    from app.services.test_steps import normalize_test_steps

    steps_n = normalize_test_steps(steps) if steps else []
    if not steps_n:
        steps_n = _step_dicts(steps)
    safe = _safe_name(title)
    exp = "; ".join((expected or [])[:3]) or "Steps complete successfully"
    lines = [emit_step_line(framework, s, base_url) for s in steps_n]

    if framework == "playwright":
        body = "\n".join(
            f"  await test.step('{_escape(s.get('description') or f'Step {i}')}', async () => {{\n"
            f"    {line}\n"
            f"  }});"
            for i, (s, line) in enumerate(zip(steps_n, lines), start=1)
        )
        content = f"""import {{ test, expect }} from '@playwright/test';

test('{_escape(title)}', async ({{ page }}) => {{
  // Expected: {_escape(exp)}
{body}
}});
"""
        return {"path": f"tests/{safe}_{index}.spec.ts", "content": content, "type": "test"}

    if framework == "cypress":
        body = "\n".join(f"    {ln}" for ln in lines)
        content = f"""describe('{_escape(title)}', () => {{
  it('executes verified Discovery steps', () => {{
    // Expected: {_escape(exp)}
{body}
  }});
}});
"""
        return {"path": f"cypress/e2e/{safe}_{index}.cy.js", "content": content, "type": "test"}

    if framework == "selenium":
        body = "\n".join(f"        {ln}" for ln in lines)
        content = f"""import org.testng.annotations.Test;
import org.testng.Assert;
import org.openqa.selenium.By;
import org.openqa.selenium.Keys;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.chrome.ChromeDriver;

public class {safe}_{index} {{
    @Test(description = "{_escape(title)}")
    public void {safe}Test() {{
        WebDriver driver = new ChromeDriver();
        try {{
            // Expected: {_escape(exp)}
{body}
        }} finally {{
            driver.quit();
        }}
    }}
}}
"""
        return {"path": f"src/test/java/{safe}_{index}.java", "content": content, "type": "test"}

    if framework == "webdriverio":
        body = "\n".join(f"        {ln}" for ln in lines)
        content = f"""describe('{_escape(title)}', () => {{
    it('executes verified Discovery steps', async () => {{
        // Expected: {_escape(exp)}
{body}
    }});
}});
"""
        return {"path": f"tests/{safe}_{index}.spec.js", "content": content, "type": "test"}

    if framework == "robot_framework":
        body = "\n".join(lines)
        content = f"""*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=true
Suite Teardown    Close Browser

*** Test Cases ***
{_escape(title)}
    New Page    {base_url}
{body}
    Close Page
"""
        return {"path": f"tests/{safe}_{index}.robot", "content": content, "type": "test"}

    if framework == "puppeteer":
        body = "\n".join(f"    {ln}" for ln in lines)
        content = f"""const puppeteer = require('puppeteer');

describe('{_escape(title)}', () => {{
  it('executes verified Discovery steps', async () => {{
    const browser = await puppeteer.launch({{ headless: true }});
    const page = await browser.newPage();
    // Expected: {_escape(exp)}
{body}
    await browser.close();
  }});
}});
"""
        return {"path": f"tests/{safe}_{index}.test.js", "content": content, "type": "test"}

    if framework == "testcafe":
        body = "\n".join(f"  {ln}" for ln in lines)
        content = f"""import {{ Selector }} from 'testcafe';

fixture `{_escape(title)}`.page `{base_url}`;

test('Execute verified Discovery steps', async t => {{
  // Expected: {_escape(exp)}
{body}
}});
"""
        return {"path": f"tests/{safe}_{index}.test.js", "content": content, "type": "test"}

    body = "\n".join(lines)
    content = f'''import pytest

class Test{safe}_{index}:
    def test_{safe.lower()}(self, driver):
        """{_escape(title)} — Expected: {_escape(exp)}"""
{body}
'''
    return {"path": f"tests/test_{safe}_{index}.py", "content": content, "type": "test"}


def build_all_framework_files(
    test_cases: list[dict],
    framework: str,
    base_url: str,
) -> list[dict]:
    files: list[dict] = []
    for i, tc in enumerate(test_cases):
        files.append(
            build_framework_test_file(
                framework=framework,
                title=tc.get("title") or f"Test {i + 1}",
                steps=tc.get("steps") or [],
                base_url=base_url or "https://example.com",
                expected=tc.get("expected_results") or [],
                index=i,
            )
        )
    return files
