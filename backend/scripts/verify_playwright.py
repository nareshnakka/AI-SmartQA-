"""Verify Playwright Python package and Chromium browser for QA Discovery."""
import sys


def main() -> int:
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("FAIL: playwright package not installed.")
        print("Fix: cd backend && .venv\\Scripts\\pip install playwright")
        return 1

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        msg = (str(exc) or type(exc).__name__).encode("ascii", errors="replace").decode("ascii")
        print(f"FAIL: {msg}")
        if "Executable doesn't exist" in msg or "browser" in msg.lower():
            print("Fix: cd backend && .venv\\Scripts\\python.exe -m playwright install chromium")
            print("Or from project root: scripts\\install-playwright.bat")
        return 1

    print("OK: Playwright Chromium is ready for QA Discovery and live debug runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
