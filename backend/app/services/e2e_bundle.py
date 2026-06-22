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
    ("src/utils/qeosProgress.ts", "utils/qeosProgress.ts", "util"),
]


def normalize_base_url(base_url: str | None) -> str:
    url = (base_url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    return url.rstrip("/")


def inject_playwright_base_url(content: str, base_url: str) -> str:
    """Inject a literal baseURL into Playwright config / asset files."""
    url = normalize_base_url(base_url)
    if not url or not content:
        return content
    content = content.replace("https://example.com", url)
    content = content.replace("http://example.com", url)
    content = re.sub(
        r"baseURL:\s*process\.env\.BASE_URL\s*\|\|\s*process\.env\.PLAYWRIGHT_BASE_URL\s*\|\|\s*['\"]?['\"]?",
        f"baseURL: '{url}'",
        content,
    )
    content = re.sub(
        r"baseURL:\s*['\"]https?://[^'\"]*['\"]",
        f"baseURL: '{url}'",
        content,
    )
    return content


def inject_orangehrm_login_url(content: str, base_url: str) -> str:
    url = normalize_base_url(base_url)
    if not url or not content:
        return content
    abs_login = f"{url}/web/index.php/auth/login"
    return content.replace("loginUrl: '/web/index.php/auth/login'", f"loginUrl: '{abs_login}'")


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
        if base_url and dest == "fixtures/testData.ts":
            content = inject_orangehrm_login_url(content, base_url)
        files.append({"path": dest, "content": content, "type": ftype})

    config_path = E2E_ROOT / "playwright.config.ts"
    config = config_path.read_text(encoding="utf-8")
    config = config.replace("testDir: './src/tests'", "testDir: './tests'")
    if base_url:
        config = inject_playwright_base_url(config, base_url)
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


_ORANGEHRM_MENUS: list[tuple[str, str, str, str]] = [
    ("Admin", "/admin", "Admin", "admin"),
    ("PIM", "/pim", "PIM", "pim"),
    ("Leave", "/leave", "Leave", "leave"),
    ("Time", "/time", "Time", "time"),
    ("Recruitment", "/recruitment", "Recruitment", "recruitment"),
    ("My Info", "/pim/viewPersonalDetails", "PIM", "myinfo"),
    ("Performance", "/performance", "Performance", "performance"),
    ("Dashboard", "/dashboard", "Dashboard", "dashboard"),
    ("Directory", "/directory", "Directory", "directory"),
    ("Maintenance", "/maintenance", "Maintenance", "maintenance"),
    ("Claim", "/claim", "Claim", "claim"),
    ("Buzz", "/buzz", "Buzz", "buzz"),
]


def _escape_ts(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")


def _is_walkthrough_title(title: str) -> bool:
    lower = title.lower()
    return any(
        k in lower
        for k in ("walkthrough", "end-to-end", "end to end", "full navigation", "all menus", "session")
    )


def _walkthrough_spec_content(base_url: str) -> str:
    """Full OrangeHRM navigation flow for E2E / walkthrough test cases."""
    nav_path = E2E_ROOT / "src/tests/orangehrm-navigation.spec.ts"
    if nav_path.exists():
        content = nav_path.read_text(encoding="utf-8")
        return content.replace("../pages/", "../../pages/").replace("../fixtures/", "../../fixtures/").replace(
            "../utils/", "../../utils/"
        )
    return f"""import {{ test, expect }} from '@playwright/test';
import {{ LoginPage }} from '../../pages/LoginPage';
import {{ NavigationPage }} from '../../pages/NavigationPage';

test('End-to-end walkthrough', async ({{ page }}) => {{
  const login = new LoginPage(page);
  const nav = new NavigationPage(page);
  await login.goto();
  await login.login();
  await login.assertDashboardLoaded();
  await nav.validateDashboard();
  await expect(page).toHaveURL(/.+/);
}});
"""


def _menu_from_title(title: str) -> tuple[str, str, str, str] | None:
    lower = title.lower()
    for name, url_part, header, shot in _ORANGEHRM_MENUS:
        if name.lower() in lower:
            return name, url_part, header, shot
    return None


def is_orangehrm_target(base_url: str | None) -> bool:
    """True when the target app is OrangeHRM (bundled LoginPage / menu flows apply)."""
    url = normalize_base_url(base_url).lower()
    if not url:
        return False
    return "orangehrm" in url or "orangehrmlive.com" in url


def load_generic_e2e_files(base_url: str | None = None) -> list[dict]:
    """Minimal Playwright bundle for discovery-imported / generic web apps (not OrangeHRM)."""
    if not E2E_ROOT.exists():
        raise FileNotFoundError(f"E2E bundle root not found at {E2E_ROOT}")

    support = [
        ("src/pages/GenericSteps.ts", "pages/GenericSteps.ts", "page_object"),
        ("src/utils/qeosProgress.ts", "utils/qeosProgress.ts", "util"),
        ("src/utils/logger.ts", "utils/logger.ts", "util"),
        ("src/utils/helpers.ts", "utils/helpers.ts", "util"),
    ]
    files: list[dict] = []
    for src_rel, dest, ftype in support:
        src = E2E_ROOT / src_rel
        files.append({"path": dest, "content": src.read_text(encoding="utf-8"), "type": ftype})

    config = (E2E_ROOT / "playwright.config.ts").read_text(encoding="utf-8")
    config = config.replace("testDir: './src/tests'", "testDir: './tests'")
    if base_url:
        config = inject_playwright_base_url(config, base_url)
    files.append({"path": "playwright.config.ts", "content": config, "type": "config"})
    files.append({
        "path": "package.json",
        "content": (E2E_ROOT / "package.json").read_text(encoding="utf-8"),
        "type": "config",
    })
    return files


def _ensure_generic_support(files: list[dict]) -> list[dict]:
    """Add GenericSteps + progress helpers if missing."""
    paths = {f.get("path", "").replace("\\", "/") for f in files}
    if "pages/GenericSteps.ts" in paths:
        return files
    try:
        extra = load_generic_e2e_files()
        return dedupe_files(files + extra)
    except FileNotFoundError:
        return files


def _generic_step_spec_content(title: str, steps: list[dict], base_url: str) -> str:
    import json

    payload = [
        {k: step[k] for k in ("description", "action", "url", "element", "target") if step.get(k)}
        for step in steps
    ]
    if not payload:
        payload = [{"description": "Open application", "action": "navigate", "url": base_url}]
    steps_literal = json.dumps(payload, ensure_ascii=False)
    url = normalize_base_url(base_url) or "https://example.com"
    return f"""import {{ test }} from '@playwright/test';
import {{ runDiscoverySteps }} from '../../pages/GenericSteps';

const STEPS = {steps_literal} as const;
const BASE = process.env.PLAYWRIGHT_BASE_URL || process.env.BASE_URL || '{_escape_ts(url)}';

test('{_escape_ts(title)}', async ({{ page }}) => {{
  await runDiscoverySteps(page, [...STEPS], BASE);
}});
"""


def materialize_batch_playwright_specs(
    files: list[dict],
    cases: list,
    base_url: str,
) -> list[dict]:
    """
    One executable Playwright spec per test case.
    OrangeHRM targets use bundled LoginPage; other apps use discovery step replay.
    """
    orangehrm = is_orangehrm_target(base_url)
    has_pages = any("NavigationPage.ts" in f.get("path", "") for f in files)
    has_generic = any("GenericSteps.ts" in f.get("path", "") for f in files)

    if is_placeholder_playwright_asset(files) or (orangehrm and not has_pages) or (not orangehrm and not has_generic):
        try:
            files = load_orangehrm_e2e_files(base_url) if orangehrm else load_generic_e2e_files(base_url)
        except FileNotFoundError:
            pass

    files = dedupe_files(files)
    files = [f for f in files if not f.get("path", "").replace("\\", "/").startswith("tests/batch/")]

    from app.services.test_steps import normalize_test_steps

    for tc in cases:
        tc_id = str(getattr(tc, "id", None) or tc.get("id", ""))
        title = getattr(tc, "title", None) or tc.get("title", "Test")
        short_id = tc_id.replace("-", "")[:8]
        raw_steps = getattr(tc, "steps", None) if hasattr(tc, "steps") else tc.get("steps")
        steps = normalize_test_steps(raw_steps or [])

        if not orangehrm:
            files = _ensure_generic_support(files)
            content = _generic_step_spec_content(title, steps, base_url)
            files.append({
                "path": f"tests/batch/tc_{short_id}.spec.ts",
                "content": content,
                "type": "test",
            })
            continue

        if _is_walkthrough_title(title):
            content = _walkthrough_spec_content(base_url)
            files.append({
                "path": f"tests/batch/tc_{short_id}.spec.ts",
                "content": content,
                "type": "test",
            })
            continue

        menu = _menu_from_title(title)

        if menu:
            name, url_part, header, shot = menu
            content = f"""import {{ test }} from '@playwright/test';
import {{ LoginPage }} from '../../pages/LoginPage';
import {{ NavigationPage }} from '../../pages/NavigationPage';

test('{_escape_ts(title)}', async ({{ page }}) => {{
  const login = new LoginPage(page);
  const nav = new NavigationPage(page);
  await login.goto();
  await login.login();
  await login.assertDashboardLoaded();
  await nav.navigateAndValidate('{name}', '{url_part}', '{header}', '{shot}');
}});
"""
        else:
            content = f"""import {{ test, expect }} from '@playwright/test';
import {{ LoginPage }} from '../../pages/LoginPage';

test('{_escape_ts(title)}', async ({{ page }}) => {{
  const login = new LoginPage(page);
  await login.goto();
  await login.login();
  await login.assertDashboardLoaded();
  await expect(page).toHaveURL(/.+/);
}});
"""
        files.append({
            "path": f"tests/batch/tc_{short_id}.spec.ts",
            "content": content,
            "type": "test",
        })

    return files
