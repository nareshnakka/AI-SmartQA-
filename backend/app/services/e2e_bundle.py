"""Bundled OrangeHRM Playwright E2E — real executable tests (not generator placeholders)."""

import re
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parents[3] / "e2e" / "orangehrm"

_BUNDLE_MAP = [
    ("src/tests/orangehrm-navigation.spec.ts", "tests/orangehrm-navigation.spec.ts", "test"),
    ("src/pages/LoginPage.ts", "pages/LoginPage.ts", "page_object"),
    ("src/pages/NavigationPage.ts", "pages/NavigationPage.ts", "page_object"),
    ("src/pages/LogoutPage.ts", "pages/LogoutPage.ts", "page_object"),
    ("src/fixtures/testData.ts", "fixtures/testData.ts", "data"),
    ("src/utils/helpers.ts", "utils/helpers.ts", "util"),
    ("src/utils/logger.ts", "utils/logger.ts", "util"),
    ("src/utils/screenshotHelper.ts", "utils/screenshotHelper.ts", "util"),
]


def is_placeholder_playwright_asset(files: list[dict]) -> bool:
    """Detect generator stubs that call performStepN but AppPage has no implementations."""
    specs = [f for f in files if f.get("path", "").endswith(".spec.ts")]
    app = next((f for f in files if f.get("path", "").replace("\\", "/").endswith("pages/AppPage.ts")), None)
    if not specs:
        return True
    for spec in specs:
        content = spec.get("content", "")
        if re.search(r"performStep\d+\(\)", content) and app:
            app_content = app.get("content", "")
            called = {int(m) for m in re.findall(r"performStep(\d+)\(\)", content)}
            defined = {int(m) for m in re.findall(r"async performStep(\d+)", app_content)}
            if called - defined:
                return True
    if app and "async performStep1()" in app.get("content", "") and "page.goto" not in app.get("content", ""):
        if any("performStep" in s.get("content", "") for s in specs):
            return True
    return False


def load_orangehrm_e2e_files(base_url: str | None = None) -> list[dict]:
    if not E2E_ROOT.exists():
        raise FileNotFoundError(f"OrangeHRM E2E bundle not found at {E2E_ROOT}")

    files: list[dict] = []
    for src_rel, dest, ftype in _BUNDLE_MAP:
        src = E2E_ROOT / src_rel
        content = src.read_text(encoding="utf-8")
        files.append({"path": dest, "content": content, "type": ftype})

    config_path = E2E_ROOT / "playwright.config.ts"
    config = config_path.read_text(encoding="utf-8")
    config = config.replace("testDir: './src/tests'", "testDir: './tests'")
    if base_url:
        config = re.sub(r"baseURL:\s*'[^']+'", f"baseURL: '{base_url}'", config)
    files.append({"path": "playwright.config.ts", "content": config, "type": "config"})

    pkg = (E2E_ROOT / "package.json").read_text(encoding="utf-8")
    files.append({"path": "package.json", "content": pkg, "type": "config"})
    return files


def dedupe_files(files: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for f in files:
        path = f.get("path", "").replace("\\", "/")
        if path:
            seen[path] = f
    return list(seen.values())
