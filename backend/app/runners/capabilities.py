"""Runtime capability detection for runners."""

import shutil
import subprocess
import sys


def node_available() -> bool:
    return shutil.which("npx") is not None or shutil.which("node") is not None


def playwright_python_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def playwright_browsers_installed() -> bool:
    if not playwright_python_available():
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def get_runner_capabilities() -> dict:
    fw = get_framework_capabilities()
    any_live = any(c.get("live") for c in fw.values())
    return {
        "node_available": node_available(),
        "playwright_python": playwright_python_available(),
        "playwright_browsers": playwright_browsers_installed(),
        "k6_available": shutil.which("k6") is not None,
        "live_execution": any_live,
        "browser_discovery": playwright_python_available(),
        "frameworks": fw,
    }


def get_framework_capabilities() -> dict[str, dict]:
    node = node_available()
    return {
        "playwright": {"live": node, "video": True, "hint": "Node.js + npx playwright"},
        "cypress": {"live": node, "video": True, "hint": "Node.js + npx cypress"},
        "puppeteer": {"live": node, "video": False, "hint": "Node.js + puppeteer"},
        "testcafe": {"live": node, "video": True, "hint": "Node.js + testcafe"},
        "webdriverio": {"live": node, "video": False, "hint": "Node.js + WebdriverIO"},
        "selenium": {"live": shutil.which("mvn") is not None, "video": False, "hint": "Java + Maven for live runs"},
        "robot_framework": {"live": shutil.which("robot") is not None, "video": False, "hint": "pip install robotframework robotframework-browser"},
        "appium": {"live": shutil.which("pytest") is not None, "video": False, "hint": "pip install Appium-Python-Client pytest"},
    }
