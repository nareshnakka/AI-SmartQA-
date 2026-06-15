"""Materialize automation assets and run Playwright tests via Node with video capture."""

import asyncio
import json
import re
import shutil
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

ProgressCallback = Callable[[str, str], Awaitable[None]]

import structlog

from app.config import settings
from app.runners.capabilities import node_available

logger = structlog.get_logger()

DEFAULT_CONFIG = """import {{ defineConfig }} from '@playwright/test';
export default defineConfig({{
  testDir: './tests',
  testMatch: '**/*.@(spec|test).?(c|m)[jt]s?(x)',
  timeout: {timeout},
  retries: 0,
  outputDir: 'test-results',
  use: {{
    headless: {headless},
    video: 'on',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  }},
  reporter: [['json', {{ outputFile: 'results.json' }}], ['line']],
}});
"""


def prepare_workspace(files: list[dict], framework: str) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="qeos-exec-"))
    has_config = any("playwright.config" in f.get("path", "") for f in files)

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        if not path:
            continue
        dest = workspace / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    if framework == "playwright" and not has_config:
        config = DEFAULT_CONFIG.format(
            timeout=settings.playwright_timeout_ms,
            headless="true" if settings.playwright_headless else "false",
        )
        (workspace / "playwright.config.ts").write_text(config, encoding="utf-8")
    elif framework == "playwright" and has_config:
        _ensure_video_in_config(workspace, files)

    if not (workspace / "package.json").exists():
        (workspace / "package.json").write_text(
            json.dumps({
                "name": "qeos-automation-run",
                "private": True,
                "scripts": {"test": "playwright test"},
                "devDependencies": {"@playwright/test": "^1.49.0"},
            }, indent=2),
            encoding="utf-8",
        )

    return workspace


def _ensure_video_in_config(workspace: Path, files: list[dict]) -> None:
    for f in files:
        if "playwright.config" not in f.get("path", ""):
            continue
        content = f.get("content", "")
        if "video" in content:
            return
        path = workspace / f["path"]
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "use:" in text and "video" not in text:
                text = text.replace("use: {", "use: { video: 'on',", 1)
                path.write_text(text, encoding="utf-8")


async def run_playwright(
    workspace: Path,
    timeout_sec: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict:
    timeout_sec = timeout_sec or settings.execution_timeout_sec

    async def progress(phase: str, detail: str) -> None:
        if on_progress:
            await on_progress(phase, detail)

    if not node_available():
        return {
            "available": False,
            "reason": "Node.js/npx not found — install Node.js to run live Playwright tests",
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "results": [],
        }

    logs: list[str] = []
    npx = shutil.which("npx") or "npx"
    npm = shutil.which("npm") or "npm"

    await progress("npm_install", "Installing npm dependencies…")
    deps = await _run_cmd(
        [npm, "install", "--no-audit", "--no-fund"],
        workspace,
        min(timeout_sec, 240),
    )
    logs.append(f"npm install: exit {deps['exit_code']}")
    if deps["exit_code"] != 0:
        return {
            "available": True,
            "exit_code": deps["exit_code"],
            "stdout": deps["stdout"],
            "stderr": deps["stderr"],
            "logs": "\n".join(logs),
            "results": [{
                "file": "",
                "title": "Dependency install",
                "status": "failed",
                "error": (deps["stderr"] or deps["stdout"] or "npm install failed")[:500],
            }],
            "summary": _summarize([], deps["exit_code"]),
            "workspace": str(workspace),
        }

    await progress("playwright_install", "Installing Playwright Chromium browser…")
    install = await _run_cmd(
        [npx, "playwright", "install", "chromium"],
        workspace,
        min(timeout_sec, 240),
    )
    logs.append(f"playwright install: exit {install['exit_code']}")

    await progress("playwright_test", "Running Playwright tests in browser…")
    test = await _run_cmd(
        [npx, "playwright", "test"],
        workspace,
        timeout_sec,
    )
    logs.extend([test["stdout"], test["stderr"]])

    parsed = _parse_results(workspace, test["stdout"], test["stderr"])
    video_paths = _discover_videos(workspace)
    for i, result in enumerate(parsed):
        if not result.get("video_path") and i < len(video_paths):
            result["video_path"] = str(video_paths[i])
        elif result.get("video_path"):
            result["video_path"] = str(Path(result["video_path"]).resolve())

    return {
        "available": True,
        "exit_code": test["exit_code"],
        "stdout": test["stdout"],
        "stderr": test["stderr"],
        "logs": "\n".join(logs),
        "results": parsed,
        "summary": _summarize(parsed, test["exit_code"]),
        "workspace": str(workspace),
    }


def persist_videos(
    workspace: Path,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    results: list[dict],
) -> list[dict]:
    base = Path(settings.execution_artifacts_dir) / str(project_id) / str(run_id)
    base.mkdir(parents=True, exist_ok=True)

    enriched: list[dict] = []
    for idx, result in enumerate(results):
        entry = dict(result)
        src = result.get("video_path")
        if src and Path(src).exists():
            ext = Path(src).suffix or ".webm"
            dest = base / f"test_{idx}{ext}"
            shutil.copy2(src, dest)
            entry["video_id"] = str(idx)
            entry["video_file"] = str(dest)
            entry["has_video"] = True
        else:
            entry["has_video"] = False
        entry.pop("video_path", None)
        enriched.append(entry)
    return enriched


def get_video_path(project_id: uuid.UUID, run_id: uuid.UUID, video_id: int) -> Path | None:
    base = Path(settings.execution_artifacts_dir) / str(project_id) / str(run_id)
    for ext in (".webm", ".mp4"):
        path = base / f"test_{video_id}{ext}"
        if path.exists():
            return path
    return None


async def _run_cmd(cmd: list[str], cwd: Path, timeout_sec: int) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        rc = proc.returncode
        if rc is None:
            rc = -1
        return {
            "exit_code": rc,
            "stdout": stdout_b.decode(errors="replace"),
            "stderr": stderr_b.decode(errors="replace"),
        }
    except asyncio.TimeoutError:
        return {"exit_code": -2, "stdout": "", "stderr": f"Command timed out after {timeout_sec}s"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def _discover_videos(workspace: Path) -> list[Path]:
    test_results = workspace / "test-results"
    if not test_results.exists():
        return []
    return sorted(test_results.rglob("video.webm"))


def _parse_results(workspace: Path, stdout: str, stderr: str) -> list[dict]:
    json_path = workspace / "results.json"
    payloads: list[dict] = []

    if json_path.exists():
        try:
            payloads.append(json.loads(json_path.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("playwright_json_parse_failed", error=str(e))

    # Playwright may emit JSON report on stdout when file reporter is overridden
    blob = _extract_json_blob(stdout) or _extract_json_blob(stderr)
    if blob:
        payloads.append(blob)

    for data in payloads:
        out: list[dict] = []
        for suite in data.get("suites", []):
            out.extend(_flatten_suite(suite, workspace))
        if out:
            return out

    results = []
    for line in (stdout + stderr).splitlines():
        m = re.search(r"\[(passed|failed|skipped)\]\s+(.+)", line, re.I)
        if m:
            results.append({
                "file": "",
                "title": m.group(2).strip(),
                "status": "passed" if m.group(1).lower() == "passed" else "failed",
                "error": None,
            })
    return results


def _extract_json_blob(text: str) -> dict | None:
    """Find Playwright JSON report object in mixed stdout."""
    if not text or "{" not in text:
        return None
    start = text.find('{\n  "config"')
    if start < 0:
        start = text.find('{"config"')
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _flatten_suite(suite: dict, workspace: Path, parent_title: str = "") -> list[dict]:
    out: list[dict] = []
    for nested in suite.get("suites", []):
        out.extend(_flatten_suite(nested, workspace, parent_title))
    for spec in suite.get("specs", []):
        title = spec.get("title", "")
        full_title = f"{parent_title} > {title}".strip(" >") if parent_title else title
        for test in spec.get("tests", []):
            status = test.get("status", "unknown")
            video_path = None
            for result in test.get("results", []):
                for att in result.get("attachments", []):
                    if att.get("contentType", "").startswith("video/") or att.get("name") == "video":
                        p = att.get("path")
                        if p:
                            video_path = str((workspace / p).resolve()) if not Path(p).is_absolute() else p
            out.append({
                "file": spec.get("file", ""),
                "title": full_title or spec.get("file", ""),
                "status": "passed" if status in ("expected", "passed") else "failed",
                "error": _first_error(test),
                "video_path": video_path,
            })
    return out


def _first_error(test: dict) -> str | None:
    for result in test.get("results", []):
        err = result.get("error")
        if err:
            return err.get("message", str(err))[:500]
    return None


def _summarize(results: list[dict], exit_code: int) -> dict:
    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    return {
        "total_tests": len(results) or (1 if exit_code == 0 else 0),
        "passed": passed,
        "failed": failed,
        "exit_code": exit_code,
        "videos_captured": sum(1 for r in results if r.get("video_path") or r.get("has_video")),
    }


def cleanup_workspace(workspace: Path) -> None:
    try:
        shutil.rmtree(workspace, ignore_errors=True)
    except Exception:
        pass
