"""Materialize automation assets and run Playwright tests via Node with video capture."""

import json
import re
import shutil
import sys
import tempfile
import uuid
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

ProgressCallback = Callable[[str, str], Awaitable[None]]
StepProgressCallback = Callable[[dict], Awaitable[None]]

import structlog

from app.config import settings
from app.runners.capabilities import node_available
from app.runners.subprocess_runner import playwright_cli, run_subprocess
from app.runners.setup_status import _playwright_browsers_on_disk

logger = structlog.get_logger()

RUNNERS_TOOLS = Path(__file__).resolve().parents[3] / "runners-tools"

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
            timeout=settings.playwright_test_timeout_ms,
            headless="true" if settings.playwright_headless else "false",
        )
        (workspace / "playwright.config.ts").write_text(config, encoding="utf-8")
    elif framework == "playwright" and has_config:
        _ensure_video_in_config(workspace, files)
        _bump_playwright_test_timeout(workspace, files)

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

    _bootstrap_runners_node_modules(workspace)
    return workspace


def _configure_playwright_workspace(workspace: Path, *, headed: bool = False) -> None:
    """Force video recording and optionally open a visible browser for debug runs."""
    for path in workspace.glob("playwright.config.*"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"video:\s*['\"]", text):
            text = re.sub(r"video:\s*['\"][^'\"]*['\"]", "video: 'on'", text, count=1)
        elif "use:" in text:
            text = text.replace("use: {", "use: { video: 'on',", 1)
        if headed:
            if re.search(r"headless:\s*\w+", text):
                text = re.sub(r"headless:\s*\w+", "headless: false", text, count=1)
            elif "use:" in text:
                text = text.replace("use: {", "use: { headless: false,", 1)
        if "viewport:" not in text and "use:" in text:
            text = text.replace(
                "use: {",
                "use: { viewport: { width: 1280, height: 720 },",
                1,
            )
        path.write_text(text, encoding="utf-8")


def _bootstrap_runners_node_modules(workspace: Path) -> bool:
    """Use pre-installed runners-tools/node_modules to avoid npm install failures on fresh machines."""
    src = RUNNERS_TOOLS / "node_modules"
    if not src.is_dir() or not (src / "@playwright").is_dir():
        return False
    dst = workspace / "node_modules"
    if dst.exists():
        return True
    pkg_src = RUNNERS_TOOLS / "package.json"
    if pkg_src.exists() and not (workspace / "package.json").exists():
        (workspace / "package.json").write_text(pkg_src.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        if sys.platform == "win32":
            import subprocess

            r = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                logger.info("bootstrap_node_modules_junction", workspace=str(workspace))
                return True
        dst.symlink_to(src, target_is_directory=True)
        return True
    except Exception as exc:
        logger.warning("bootstrap_node_modules_link_failed", error=str(exc))
    try:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return True
    except Exception as exc:
        logger.warning("bootstrap_node_modules_copy_failed", error=str(exc))
        return False


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


def _bump_playwright_test_timeout(workspace: Path, files: list[dict]) -> None:
    """Raise per-test timeout so full navigation walkthroughs can finish."""
    min_ms = settings.playwright_test_timeout_ms
    for f in files:
        if "playwright.config" not in f.get("path", ""):
            continue
        path = workspace / f["path"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(r"timeout:\s*([\d_]+)", text)
        if not match:
            continue
        current = int(match.group(1).replace("_", ""))
        if current >= min_ms:
            continue
        text = re.sub(r"timeout:\s*[\d_]+", f"timeout: {min_ms}", text, count=1)
        path.write_text(text, encoding="utf-8")


async def run_playwright(
    workspace: Path,
    timeout_sec: int | None = None,
    on_progress: ProgressCallback | None = None,
    *,
    test_glob: str | None = None,
    headed: bool = False,
    embed_live: bool = False,
    progress_path: Path | None = None,
    live_frame_path: Path | None = None,
    total_steps: int = 15,
    on_step_progress: StepProgressCallback | None = None,
    cancel_run_id: str | None = None,
) -> dict:
    timeout_sec = timeout_sec or settings.execution_timeout_sec

    async def progress(phase: str, detail: str) -> None:
        if on_progress:
            await on_progress(phase, detail)

    use_headed = headed and not embed_live
    _configure_playwright_workspace(workspace, headed=use_headed)

    if cancel_run_id:
        from app.services.execution_worker import is_run_cancel_requested

        if is_run_cancel_requested(cancel_run_id):
            return {
                "available": True,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Cancelled by user",
                "logs": "Cancelled before Playwright run",
                "results": [],
                "cancelled": True,
            }

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
    npm = shutil.which("npm") or "npm"
    pw_cli = playwright_cli(workspace)
    has_modules = (workspace / "node_modules" / "@playwright").is_dir()

    if not has_modules:
        await progress("npm_install", "Installing npm dependencies…")
        deps = await run_subprocess(
            [npm, "install", "--no-audit", "--no-fund"],
            workspace,
            min(timeout_sec, 240),
            cancel_run_id=cancel_run_id,
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
    else:
        logs.append("Using pre-installed runners-tools node_modules (skipped npm install)")

    browsers_ready, _ = _playwright_browsers_on_disk()
    if not browsers_ready:
        await progress("playwright_install", "Installing Playwright Chromium browser…")
        install = await run_subprocess(
            [*pw_cli, "install", "chromium"],
            workspace,
            min(timeout_sec, 240),
            cancel_run_id=cancel_run_id,
        )
        logs.append(f"playwright install: exit {install['exit_code']}")
        if install["exit_code"] != 0:
            logs.append((install["stderr"] or install["stdout"] or "playwright install failed")[:400])
    else:
        logs.append("Playwright Chromium already installed (skipped browser download)")

    test_args = [*pw_cli, "test", "--reporter=line,json"]
    if test_glob:
        test_args.append(test_glob)
    if use_headed:
        test_args.append("--headed")

    extra_env: dict[str, str] = {}
    if progress_path:
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        extra_env["QEOS_PROGRESS_FILE"] = str(progress_path)
    if live_frame_path:
        live_frame_path.parent.mkdir(parents=True, exist_ok=True)
        extra_env["QEOS_LIVE_FRAME"] = str(live_frame_path.resolve())
    if total_steps:
        extra_env["QEOS_TOTAL_STEPS"] = str(total_steps)

    if embed_live:
        await progress("playwright_test", "Running Playwright — live view in Studio…")
    elif use_headed:
        await progress("playwright_test", "Running Playwright in visible browser…")
    else:
        await progress("playwright_test", "Running Playwright tests in browser…")

    stop_poll = asyncio.Event()

    async def _poll_step_progress() -> None:
        last_ts = 0.0
        while not stop_poll.is_set():
            if progress_path and progress_path.exists() and on_step_progress:
                try:
                    data = json.loads(progress_path.read_text(encoding="utf-8"))
                    ts = float(data.get("ts") or 0)
                    if ts > last_ts:
                        last_ts = ts
                        await on_step_progress(data)
                except Exception:
                    pass
            await asyncio.sleep(0.35)

    poll_task = asyncio.create_task(_poll_step_progress()) if on_step_progress and progress_path else None
    try:
        test = await run_subprocess(test_args, workspace, timeout_sec, extra_env or None, cancel_run_id=cancel_run_id)
    finally:
        stop_poll.set()
        if poll_task:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

    cancelled = bool(test.get("cancelled"))
    if not cancelled and cancel_run_id:
        from app.services.execution_worker import is_run_cancel_requested

        cancelled = is_run_cancel_requested(cancel_run_id)
    logs.extend([test["stdout"], test["stderr"]])

    parsed = _parse_results(workspace, test["stdout"], test["stderr"])
    _assign_videos_to_results(workspace, parsed)

    return {
        "available": True,
        "exit_code": test["exit_code"],
        "stdout": test["stdout"],
        "stderr": test["stderr"],
        "logs": "\n".join(logs),
        "results": parsed,
        "summary": _summarize(parsed, test["exit_code"]),
        "workspace": str(workspace),
        "cancelled": cancelled,
    }


def persist_videos(
    workspace: Path,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    results: list[dict],
) -> list[dict]:
    base = Path(settings.execution_artifacts_dir) / str(project_id) / str(run_id)
    base.mkdir(parents=True, exist_ok=True)
    discovered = _discover_videos(workspace)

    enriched: list[dict] = []
    for idx, result in enumerate(results):
        entry = dict(result)
        src = result.get("video_path")
        if (not src or not Path(src).exists()) and discovered:
            file_slug = Path(result.get("file", "")).stem.lower()
            matching = [v for v in discovered if file_slug and file_slug in str(v).lower()]
            pick = matching[-1] if matching else (discovered[idx] if idx < len(discovered) else discovered[-1])
            src = str(pick)
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


def get_live_frame_path(project_id: uuid.UUID, run_id: uuid.UUID) -> Path | None:
    path = Path(settings.execution_artifacts_dir) / str(project_id) / str(run_id) / "live.jpg"
    return path if path.exists() else None


def run_artifact_dir(project_id: uuid.UUID, run_id: uuid.UUID) -> Path:
    base = Path(settings.execution_artifacts_dir) / str(project_id) / str(run_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_video_path(project_id: uuid.UUID, run_id: uuid.UUID, video_id: int) -> Path | None:
    base = Path(settings.execution_artifacts_dir) / str(project_id) / str(run_id)
    for ext in (".webm", ".mp4"):
        path = base / f"test_{video_id}{ext}"
        if path.exists():
            return path
    return None


async def _run_cmd(cmd: list[str], cwd: Path, timeout_sec: int) -> dict:
    return await run_subprocess(cmd, cwd, timeout_sec)


def _discover_videos(workspace: Path) -> list[Path]:
    test_results = workspace / "test-results"
    if not test_results.exists():
        return []
    return sorted(test_results.rglob("video.webm"), key=lambda p: p.stat().st_mtime)


def _assign_videos_to_results(workspace: Path, parsed: list[dict]) -> None:
    videos = _discover_videos(workspace)
    for i, result in enumerate(parsed):
        if result.get("video_path"):
            result["video_path"] = str(Path(result["video_path"]).resolve())
            continue
        file_slug = Path(result.get("file", "")).stem.lower()
        matching = [v for v in videos if file_slug and file_slug in str(v).lower()]
        if matching:
            result["video_path"] = str(matching[-1].resolve())
        elif len(parsed) == 1 and videos:
            result["video_path"] = str(videos[-1].resolve())
        elif i < len(videos):
            result["video_path"] = str(videos[i].resolve())


def _parse_results(workspace: Path, stdout: str, stderr: str) -> list[dict]:
    json_path = workspace / "results.json"
    if not json_path.exists():
        json_path = workspace / "test-results" / "results.json"
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
                "status": "passed" if status in ("expected", "passed", "flaky") else "failed",
                "error": _first_error(test),
                "video_path": video_path,
            })
    return out


def _first_error(test: dict) -> str | None:
    from app.runners.playwright_output import strip_ansi

    for result in reversed(test.get("results", [])):
        err = result.get("error")
        if err:
            msg = strip_ansi(err.get("message", str(err)) if isinstance(err, dict) else str(err))
            if msg and "NO_COLOR" not in msg:
                return msg[:800]
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
