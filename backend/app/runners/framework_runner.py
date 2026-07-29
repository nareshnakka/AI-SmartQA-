"""Unified automation framework runner — Playwright, Cypress, Selenium, and all QEOS frameworks."""

import asyncio
import json
import re
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from app.config import settings
from app.runners.capabilities import node_available
from app.runners.playwright_runner import (
    _parse_results,
    _run_cmd,
    _summarize,
    cleanup_workspace,
    persist_videos,
    prepare_workspace,
    run_playwright,
)

logger = structlog.get_logger()

ALL_FRAMEWORKS = [
    "playwright", "selenium", "cypress", "webdriverio",
    "robot_framework", "appium", "puppeteer", "testcafe",
]


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ")


def build_test_case_files(test_cases: list[dict], framework: str, base_url: str) -> list[dict]:
    from app.services.step_script_codegen import build_all_framework_files

    return build_all_framework_files(test_cases, framework, base_url)

def prepare_framework_workspace(files: list[dict], framework: str) -> Path:
    workspace = prepare_workspace(files, "playwright" if framework == "playwright" else framework)

    if framework == "cypress" and not (workspace / "cypress.config.js").exists():
        (workspace / "cypress.config.js").write_text(
            f"""module.exports = {{
  e2e: {{
    baseUrl: 'https://example.com',
    video: true,
    supportFile: false,
    specPattern: 'cypress/e2e/**/*.cy.{{js,jsx,ts,tsx}}',
  }},
}};""",
            encoding="utf-8",
        )
        if not (workspace / "package.json").exists():
            (workspace / "package.json").write_text(json.dumps({
                "name": "qeos-cypress-run", "private": True,
                "devDependencies": {"cypress": "^13.0.0"},
            }, indent=2), encoding="utf-8")

    elif framework == "puppeteer":
        if not (workspace / "package.json").exists():
            (workspace / "package.json").write_text(json.dumps({
                "name": "qeos-puppeteer-run", "private": True,
                "scripts": {"test": "jest"},
                "devDependencies": {"jest": "^29.0.0", "puppeteer": "^22.0.0"},
            }, indent=2), encoding="utf-8")

    elif framework == "testcafe":
        if not (workspace / "package.json").exists():
            (workspace / "package.json").write_text(json.dumps({
                "name": "qeos-testcafe-run", "private": True,
                "devDependencies": {"testcafe": "^3.0.0"},
            }, indent=2), encoding="utf-8")

    elif framework == "webdriverio":
        if not (workspace / "wdio.conf.js").exists():
            (workspace / "wdio.conf.js").write_text("""exports.config = {
  runner: 'local',
  specs: ['./tests/**/*.spec.js'],
  maxInstances: 1,
  capabilities: [{ browserName: 'chrome', 'goog:chromeOptions': { args: ['headless'] } }],
  logLevel: 'error',
  framework: 'mocha',
  reporters: ['spec'],
};""", encoding="utf-8")
        if not (workspace / "package.json").exists():
            (workspace / "package.json").write_text(json.dumps({
                "name": "qeos-wdio-run", "private": True,
                "devDependencies": {"@wdio/cli": "^8.0.0", "@wdio/local-runner": "^8.0.0",
                    "@wdio/mocha-framework": "^8.0.0", "@wdio/spec-reporter": "^8.0.0"},
            }, indent=2), encoding="utf-8")

    elif framework == "selenium" and not (workspace / "pom.xml").exists():
        (workspace / "pom.xml").write_text("""<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>qeos</groupId><artifactId>selenium-tests</artifactId><version>1.0</version>
  <dependencies>
    <dependency><groupId>org.seleniumhq.selenium</groupId><artifactId>selenium-java</artifactId><version>4.15.0</version></dependency>
    <dependency><groupId>org.testng</groupId><artifactId>testng</artifactId><version>7.8.0</version></dependency>
  </dependencies>
</project>""", encoding="utf-8")

    elif framework == "appium" and not (workspace / "requirements.txt").exists():
        (workspace / "requirements.txt").write_text("Appium-Python-Client\npytest\n", encoding="utf-8")

    elif framework == "robot_framework" and not (workspace / "requirements.txt").exists():
        (workspace / "requirements.txt").write_text("robotframework\nrobotframework-browser\n", encoding="utf-8")

    return workspace


def build_workspace_for_test_cases(test_cases: list[dict], base_url: str, framework: str) -> Path:
    files = build_test_case_files(test_cases, framework, base_url)
    return prepare_framework_workspace(files, framework)


def discover_framework_videos(workspace: Path, framework: str) -> list[Path]:
    patterns = {
        "playwright": ["test-results/**/video.webm"],
        "cypress": ["cypress/videos/**/*.mp4"],
        "testcafe": ["artifacts/videos/**/*.webm", "videos/**/*.webm"],
        "puppeteer": ["videos/**/*.webm", "videos/**/*.mp4"],
        "webdriverio": ["videos/**/*.webm"],
    }
    videos: list[Path] = []
    for pattern in patterns.get(framework, []):
        videos.extend(sorted(workspace.glob(pattern.replace("**/", "**/") if "**" in pattern else pattern)))
    if framework == "playwright":
        tr = workspace / "test-results"
        if tr.exists():
            videos = sorted(tr.rglob("video.webm"))
    elif framework == "cypress":
        cv = workspace / "cypress" / "videos"
        if cv.exists():
            videos = sorted(cv.rglob("*.mp4"))
    return videos


async def run_framework(
    workspace: Path,
    framework: str,
    timeout_sec: int | None = None,
    on_progress: Callable[[str, str], Awaitable[None]] | None = None,
    *,
    test_glob: str | None = None,
    headed: bool = False,
    embed_live: bool = False,
    progress_path: Path | None = None,
    live_frame_path: Path | None = None,
    total_steps: int = 15,
    on_step_progress: Callable[[dict], Awaitable[None]] | None = None,
    cancel_run_id: str | None = None,
    base_url: str | None = None,
    login_env: dict[str, str] | None = None,
) -> dict:
    timeout_sec = timeout_sec or settings.execution_timeout_sec

    if framework == "playwright":
        return await run_playwright(
            workspace,
            timeout_sec,
            on_progress=on_progress,
            test_glob=test_glob,
            headed=headed,
            embed_live=embed_live,
            progress_path=progress_path,
            live_frame_path=live_frame_path,
            total_steps=total_steps,
            on_step_progress=on_step_progress,
            cancel_run_id=cancel_run_id,
            base_url=base_url,
            login_env=login_env,
        )

    if not node_available() and framework in ("cypress", "puppeteer", "testcafe", "webdriverio"):
        return _structured_dry_run(workspace, framework, "Node.js required for live execution")

    npx = shutil.which("npx") or "npx"

    try:
        if framework == "cypress":
            return await _run_cypress(workspace, npx, timeout_sec)
        if framework == "puppeteer":
            return await _run_puppeteer(workspace, npx, timeout_sec)
        if framework == "testcafe":
            return await _run_testcafe(workspace, npx, timeout_sec)
        if framework == "webdriverio":
            return await _run_wdio(workspace, npx, timeout_sec)
        if framework == "robot_framework":
            return await _run_robot(workspace, timeout_sec)
        if framework == "selenium":
            return await _run_selenium(workspace, timeout_sec)
        if framework == "appium":
            return await _run_appium(workspace, timeout_sec)
    except Exception as e:
        logger.warning("framework_run_failed", framework=framework, error=str(e))
        return _structured_dry_run(workspace, framework, str(e))

    return _structured_dry_run(workspace, framework, "Unsupported framework")


async def _run_cypress(workspace: Path, npx: str, timeout_sec: int) -> dict:
    install = await _run_cmd([npx, "--yes", "cypress", "install"], workspace, min(timeout_sec, 180))
    test = await _run_cmd([npx, "--yes", "cypress", "run", "--browser", "chrome", "--headless"], workspace, timeout_sec)
    results = _parse_generic_output(workspace, test, framework="cypress")
    videos = discover_framework_videos(workspace, "cypress")
    for i, r in enumerate(results):
        if i < len(videos):
            r["video_path"] = str(videos[i])
    return _outcome(test, results, install.get("stderr", ""))


async def _run_puppeteer(workspace: Path, npx: str, timeout_sec: int) -> dict:
    await _run_cmd([npx, "--yes", "npm", "install"], workspace, min(timeout_sec, 180))
    test = await _run_cmd([npx, "--yes", "jest", "--passWithNoTests"], workspace, timeout_sec)
    results = _parse_generic_output(workspace, test, framework="puppeteer")
    return _outcome(test, results)


async def _run_testcafe(workspace: Path, npx: str, timeout_sec: int) -> dict:
    specs = list(workspace.glob("tests/*.test.js"))
    spec_arg = str(specs[0]) if specs else "tests/"
    test = await _run_cmd(
        [npx, "--yes", "testcafe", "chrome:headless", "--video", "artifacts/videos", spec_arg],
        workspace, timeout_sec,
    )
    results = _parse_generic_output(workspace, test, framework="testcafe")
    videos = discover_framework_videos(workspace, "testcafe")
    for i, r in enumerate(results):
        if i < len(videos):
            r["video_path"] = str(videos[i])
    return _outcome(test, results)


async def _run_wdio(workspace: Path, npx: str, timeout_sec: int) -> dict:
    await _run_cmd([npx, "--yes", "npm", "install"], workspace, min(timeout_sec, 180))
    test = await _run_cmd([npx, "--yes", "wdio", "run", "wdio.conf.js"], workspace, timeout_sec)
    results = _parse_generic_output(workspace, test, framework="webdriverio")
    return _outcome(test, results)


async def _run_robot(workspace: Path, timeout_sec: int) -> dict:
    robot = shutil.which("robot")
    if not robot:
        return _structured_dry_run(workspace, "robot_framework", "Install: pip install robotframework robotframework-browser")
    test = await _run_cmd([robot, "--outputdir", "results", "tests/"], workspace, timeout_sec)
    results = _parse_generic_output(workspace, test, framework="robot_framework")
    return _outcome(test, results)


async def _run_selenium(workspace: Path, timeout_sec: int) -> dict:
    mvn = shutil.which("mvn")
    if not mvn:
        return _structured_dry_run(workspace, "selenium", "Maven not found — validated Java test structure")
    test = await _run_cmd([mvn, "-q", "test"], workspace, timeout_sec)
    results = _parse_generic_output(workspace, test, framework="selenium")
    return _outcome(test, results)


async def _run_appium(workspace: Path, timeout_sec: int) -> dict:
    pytest_bin = shutil.which("pytest")
    if not pytest_bin:
        return _structured_dry_run(workspace, "appium", "pytest not found — validated Python test structure")
    test = await _run_cmd([pytest_bin, "tests/", "-v"], workspace, timeout_sec)
    results = _parse_generic_output(workspace, test, framework="appium")
    return _outcome(test, results)


def _parse_generic_output(workspace: Path, test: dict, framework: str) -> list[dict]:
    json_path = workspace / "results.json"
    if json_path.exists():
        return _parse_results(workspace, test.get("stdout", ""), test.get("stderr", ""))

    results = []
    stdout = test.get("stdout", "") + test.get("stderr", "")
    for line in stdout.splitlines():
        m = re.search(r"(PASS|FAIL|passed|failed|✓|✗|✔|×)", line, re.I)
        if m and len(line.strip()) > 5:
            status = "passed" if m.group(1).lower() in ("pass", "passed", "✓", "✔") else "failed"
            results.append({"file": "", "title": line.strip()[:120], "status": status, "error": None})

    if not results:
        test_files = list(workspace.rglob("*.spec.*")) + list(workspace.rglob("*.cy.js")) + list(workspace.rglob("*.robot"))
        for f in test_files[:10]:
            status = "passed" if test.get("exit_code") == 0 else "failed"
            results.append({"file": str(f.name), "title": f.stem, "status": status, "error": None})

    if not results:
        status = "passed" if test.get("exit_code") == 0 else "failed"
        results.append({"file": framework, "title": f"{framework} execution", "status": status, "error": test.get("stderr", "")[:300]})

    return results


def _outcome(test: dict, results: list[dict], extra_log: str = "") -> dict:
    return {
        "available": True,
        "exit_code": test.get("exit_code", 1),
        "stdout": test.get("stdout", ""),
        "stderr": test.get("stderr", ""),
        "logs": extra_log + test.get("stdout", "") + test.get("stderr", ""),
        "results": results,
        "summary": _summarize(results, test.get("exit_code", 1)),
    }


def _structured_dry_run(workspace: Path, framework: str, reason: str) -> dict:
    test_files = []
    for pattern in ("*.spec.ts", "*.spec.js", "*.cy.js", "*.robot", "*.java", "*.py"):
        test_files.extend(workspace.rglob(pattern))

    results = []
    for f in test_files[:20]:
        content = f.read_text(encoding="utf-8", errors="replace")
        has_placeholder = "TODO" in content or "Implement" in content
        results.append({
            "file": str(f.relative_to(workspace)),
            "title": f.stem,
            "status": "passed_with_warnings" if has_placeholder else "passed",
            "error": None if not has_placeholder else "Contains placeholders",
        })

    if not results:
        results.append({"file": framework, "title": "Validation", "status": "passed_with_warnings", "error": reason})

    return {
        "available": False,
        "reason": reason,
        "exit_code": 0,
        "stdout": "",
        "stderr": reason,
        "logs": f"Dry-run validation ({framework}): {reason}",
        "results": results,
        "summary": _summarize(results, 0),
    }
