"""Install all QEOS automation and performance runner dependencies."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RUNNERS_TOOLS = ROOT / "runners-tools"


def _venv_python() -> Path:
    win = BACKEND / ".venv" / "Scripts" / "python.exe"
    if win.exists():
        return win
    posix = BACKEND / ".venv" / "bin" / "python"
    if posix.exists():
        return posix
    print("ERROR: backend .venv not found. Run setup-and-run.bat step 4 first.")
    sys.exit(1)


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 900,
    label: str = "",
) -> tuple[bool, str]:
    name = label or " ".join(cmd[:3])
    print(f"\n>> {name}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            print(f"   WARN/FAIL (exit {proc.returncode})")
            if out.strip():
                print("   ", out.strip()[:400].replace("\n", "\n    "))
            return False, out[:500]
        print("   OK")
        return True, out[:200]
    except subprocess.TimeoutExpired:
        print(f"   TIMEOUT after {timeout}s")
        return False, "timeout"
    except Exception as exc:
        print(f"   ERROR: {exc}")
        return False, str(exc)


def _try_winget(package_id: str, label: str) -> bool:
    if not shutil.which("winget"):
        print(f"   skip {label}: winget not available")
        return False
    ok, _ = _run(
        [
            "winget", "install", "-e", "--id", package_id,
            "--accept-package-agreements", "--accept-source-agreements",
        ],
        timeout=1200,
        label=f"winget {label}",
    )
    return ok


def install_all(*, skip_winget: bool = False) -> int:
    py = _venv_python()
    py_s = str(py)
    failures: list[str] = []

    print("=" * 60)
    print("QEOS — Installing automation & performance runners")
    print("=" * 60)

    ok, _ = _run([py_s, "-m", "pip", "install", "--upgrade", "pip"], label="pip upgrade")
    if not ok:
        failures.append("pip upgrade")

    ok, _ = _run(
        [py_s, "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=BACKEND,
        label="Python requirements.txt",
    )
    if not ok:
        failures.append("requirements.txt")

    req_runners = BACKEND / "requirements-runners.txt"
    if req_runners.exists():
        ok, _ = _run(
            [py_s, "-m", "pip", "install", "-r", "requirements-runners.txt"],
            cwd=BACKEND,
            label="Python automation/performance runners (Robot, Appium, Locust)",
        )
        if not ok:
            failures.append("requirements-runners.txt")

    ok, out = _run([py_s, "-m", "playwright", "install", "chromium"], cwd=BACKEND, label="Playwright Chromium (Python)", timeout=1800)
    if not ok:
        failures.append("playwright chromium (python)")
        if "Executable doesn't exist" in out or "download" in out.lower():
            print("   TIP: Playwright needs TWO steps: pip install playwright AND python -m playwright install chromium")

    ok, _ = _run([py_s, str(BACKEND / "scripts" / "verify_playwright.py")], label="Verify Playwright")
    if not ok:
        failures.append("playwright verify")

    _run([py_s, "-m", "rfbrowser", "init"], cwd=BACKEND, timeout=1200, label="Robot Framework Browser init")

    npm = shutil.which("npm")
    npx = shutil.which("npx") or npm
    if npm and RUNNERS_TOOLS.exists():
        ok, _ = _run(
            [npm, "install"],
            cwd=RUNNERS_TOOLS,
            timeout=1200,
            label="Node runners-tools (Playwright, Cypress, Puppeteer, TestCafe, WebdriverIO)",
        )
        if not ok:
            failures.append("runners-tools npm install")
        elif npx:
            _run([npx, "playwright", "install", "chromium"], cwd=RUNNERS_TOOLS, label="Playwright Chromium (Node)")
            _run([npx, "cypress", "install"], cwd=RUNNERS_TOOLS, timeout=600, label="Cypress binary")
    else:
        print("\n>> Node runners-tools: SKIP (npm or runners-tools/ missing)")
        if not npm:
            failures.append("node/npm for runners-tools")

    if not skip_winget:
        if not shutil.which("k6"):
            if not _try_winget("GrafanaLabs.k6", "k6 load testing"):
                failures.append("k6 (optional winget)")
        if not shutil.which("java"):
            _try_winget("Microsoft.OpenJDK.17", "OpenJDK 17")
        if not shutil.which("mvn"):
            _try_winget("Apache.Maven", "Apache Maven")
        if not shutil.which("jmeter"):
            _try_winget("Apache.JMeter", "Apache JMeter")

    print("\n" + "=" * 60)
    print("Verification summary")
    print("=" * 60)
    verify_proc = subprocess.run([py_s, str(BACKEND / "scripts" / "verify_all_runners.py")])
    verify_code = verify_proc.returncode

    critical = [f for f in failures if f in ("playwright verify", "playwright chromium (python)", "requirements.txt")]
    if critical or verify_code != 0:
        print("\nSetup completed with critical issues. Retry: scripts\\install-all-runners.bat")
        return 1
    if failures:
        print("\nNon-critical items (optional tools):")
        for f in failures:
            print(f"  - {f}")
    else:
        print("\nAll runners installed successfully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-winget", action="store_true")
    args = parser.parse_args()
    return install_all(skip_winget=args.skip_winget)


if __name__ == "__main__":
    sys.exit(main())
