"""Run shell commands off the uvicorn event loop (Windows subprocess fix)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

_active_procs: dict[str, subprocess.Popen] = {}


def playwright_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Avoid Node NO_COLOR/FORCE_COLOR warnings polluting Playwright stderr."""
    env = os.environ.copy()
    env.pop("FORCE_COLOR", None)
    env.pop("NO_COLOR", None)
    env["CI"] = "1"
    if extra:
        env.update(extra)
    return env


def run_subprocess_sync(
    cmd: list[str],
    cwd: Path,
    timeout_sec: int,
    extra_env: dict[str, str] | None = None,
    cancel_run_id: str | None = None,
) -> dict:
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=playwright_subprocess_env(extra_env),
        )
        if cancel_run_id:
            _active_procs[cancel_run_id] = proc
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        return {
            "exit_code": proc.returncode if proc.returncode is not None else -1,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "cancelled": False,
        }
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
            proc.communicate()
        return {"exit_code": -2, "stdout": "", "stderr": f"Command timed out after {timeout_sec}s", "cancelled": False}
    except Exception as exc:
        return {"exit_code": -1, "stdout": "", "stderr": str(exc), "cancelled": False}
    finally:
        if cancel_run_id:
            _active_procs.pop(cancel_run_id, None)


def kill_run_subprocess(cancel_run_id: str) -> bool:
    proc = _active_procs.get(cancel_run_id)
    if not proc or proc.poll() is not None:
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        return True
    except Exception:
        try:
            proc.kill()
            return True
        except Exception:
            return False


async def run_subprocess(
    cmd: list[str],
    cwd: Path,
    timeout_sec: int,
    extra_env: dict[str, str] | None = None,
    cancel_run_id: str | None = None,
) -> dict:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_subprocess_sync(cmd, cwd, timeout_sec, extra_env, cancel_run_id),
    )
    if cancel_run_id:
        from app.services.execution_worker import is_run_cancel_requested

        if is_run_cancel_requested(cancel_run_id):
            result["cancelled"] = True
    return result


def playwright_cli(workspace: Path) -> list[str]:
    """Resolve Playwright CLI without npx when possible."""
    for name in ("playwright.cmd", "playwright"):
        shim = workspace / "node_modules" / ".bin" / name
        if shim.exists():
            return [str(shim)]
    import shutil

    npx = shutil.which("npx") or "npx"
    return [npx, "playwright"]
