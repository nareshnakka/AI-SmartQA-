"""Runner readiness checks for automation and performance tools."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
RUNNERS_TOOLS = ROOT / "runners-tools"


def _ascii(s: str) -> str:
    return s.encode("ascii", errors="replace").decode("ascii")


def _venv_bin(name: str) -> bool:
    for sub in ("Scripts", "bin"):
        base = BACKEND / ".venv" / sub
        if (base / f"{name}.exe").exists() or (base / name).exists():
            return True
    return shutil.which(name) is not None


def _is_stale_browser_path(path: Path) -> bool:
    s = str(path).lower()
    return "cursor-sandbox-cache" in s or "sandbox-cache" in s


def _playwright_browser_roots() -> list[Path]:
    roots: list[Path] = []
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.exists() and _chromium_tree_ready(p) and not _is_stale_browser_path(p):
            roots.append(p)
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        roots.append(Path(local_app) / "ms-playwright")
    roots.append(Path.home() / ".cache" / "ms-playwright")
    roots.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def configure_playwright_browsers_env() -> tuple[bool, str]:
    """
    Point PLAYWRIGHT_BROWSERS_PATH at installed Chromium.
    Ignores stale Cursor/sandbox paths that break Discovery and live runs.
    """
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if _is_stale_browser_path(p) or not p.exists() or not _chromium_tree_ready(p):
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)

    for root in _playwright_browser_roots():
        if root.exists() and _chromium_tree_ready(root):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(root)
            return True, ""

    return False, "python -m playwright install chromium (or scripts\\install-playwright.bat)"


def _playwright_browsers_on_disk() -> tuple[bool, str]:
    """Check pip package + downloaded Chromium without launching a browser."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, "pip install playwright && python -m playwright install chromium"

    ok, hint = configure_playwright_browsers_env()
    return ok, hint


def _chromium_tree_ready(root: Path) -> bool:
    for pattern in ("chromium_headless_shell-*", "chromium-*"):
        for folder in root.glob(pattern):
            if not folder.is_dir():
                continue
            for exe in (
                folder / "chrome-win64" / "chrome.exe",
                folder / "chrome-win" / "chrome.exe",
                folder / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
                folder / "chrome-linux" / "chrome",
                folder / "chrome-headless-shell-linux64" / "chrome-headless-shell",
                folder / "chrome-mac" / "Chromium.app",
            ):
                if exe.exists():
                    return True
    return False


def _check_playwright_python() -> tuple[bool, str]:
    """Launch Chromium — use only outside a running asyncio loop (scripts, thread pool)."""
    configure_playwright_browsers_env()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True, ""
    except ImportError:
        return False, "pip install playwright && python -m playwright install chromium"
    except Exception as exc:
        msg = _ascii(str(exc))
        if "Executable doesn't exist" in msg or "browser" in msg.lower():
            return False, "python -m playwright install chromium"
        if "asyncio loop" in msg.lower() or "async api" in msg.lower():
            return _playwright_browsers_on_disk()
        return False, msg[:200]


async def check_playwright_async() -> tuple[bool, str]:
    """Launch Chromium with async API (safe on uvicorn / FastAPI event loop)."""
    ok, hint = _playwright_browsers_on_disk()
    if not ok:
        return ok, hint
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
        return True, ""
    except ImportError:
        return False, "pip install playwright && python -m playwright install chromium"
    except Exception as exc:
        msg = _ascii(str(exc))
        if "Executable doesn't exist" in msg or "browser" in msg.lower():
            return False, "python -m playwright install chromium (or scripts\\install-playwright.bat)"
        return False, msg[:200]


def _node_module(pkg: str) -> bool:
    return (RUNNERS_TOOLS / "node_modules" / pkg).exists()


def collect_runner_status() -> dict:
    pw_ok, pw_hint = _playwright_browsers_on_disk()
    node = shutil.which("node") is not None or shutil.which("npm") is not None

    automation = {
        "playwright": {
            "ready": pw_ok and node,
            "hint": pw_hint or ("Node.js required" if not node else ""),
            "live": pw_ok and node,
        },
        "cypress": {
            "ready": node and _node_module("cypress"),
            "hint": "" if _node_module("cypress") else "run scripts/install-all-runners.bat",
            "live": node and _node_module("cypress"),
        },
        "puppeteer": {
            "ready": node and _node_module("puppeteer"),
            "hint": "" if _node_module("puppeteer") else "run scripts/install-all-runners.bat",
            "live": node and _node_module("puppeteer"),
        },
        "testcafe": {
            "ready": node and _node_module("testcafe"),
            "hint": "" if _node_module("testcafe") else "run scripts/install-all-runners.bat",
            "live": node and _node_module("testcafe"),
        },
        "webdriverio": {
            "ready": node and _node_module("@wdio/cli"),
            "hint": "" if _node_module("@wdio/cli") else "run scripts/install-all-runners.bat",
            "live": node and _node_module("@wdio/cli"),
        },
        "selenium": {
            "ready": shutil.which("mvn") is not None and shutil.which("java") is not None,
            "hint": "" if shutil.which("mvn") else "Install Java 17 + Maven (winget)",
            "live": shutil.which("mvn") is not None,
        },
        "robot_framework": {
            "ready": _venv_bin("robot") and pw_ok,
            "hint": "" if _venv_bin("robot") else "pip install robotframework robotframework-browser",
            "live": _venv_bin("robot") and pw_ok,
        },
        "appium": {
            "ready": _venv_bin("pytest"),
            "hint": "Appium server must be running separately for mobile execution",
            "live": _venv_bin("pytest"),
        },
    }

    performance = {
        "k6": {
            "ready": shutil.which("k6") is not None,
            "hint": "" if shutil.which("k6") else "winget install GrafanaLabs.k6",
            "live": True,
        },
        "locust": {
            "ready": _venv_bin("locust"),
            "hint": "" if _venv_bin("locust") else "pip install locust (backend venv)",
            "live": False,
        },
        "jmeter": {
            "ready": shutil.which("jmeter") is not None,
            "hint": "" if shutil.which("jmeter") else "winget install Apache.JMeter (optional)",
            "live": False,
        },
        "gatling": {
            "ready": shutil.which("java") is not None,
            "hint": "Scripts generated for export; run with Gatling CLI",
            "live": False,
        },
    }

    frameworks = {
        name: {
            "live": info["live"],
            "video": name in ("playwright", "cypress", "testcafe"),
            "ready": info["ready"],
            "hint": info.get("hint") or "",
        }
        for name, info in automation.items()
    }

    return {
        "node_available": node,
        "playwright_python": pw_ok or _venv_bin("playwright"),
        "playwright_browsers": pw_ok,
        "playwright_hint": pw_hint if not pw_ok else None,
        "k6_available": performance["k6"]["ready"],
        "live_execution": any(v["live"] for v in automation.values()),
        "browser_discovery": pw_ok,
        "automation": automation,
        "performance": performance,
        "frameworks": frameworks,
    }
