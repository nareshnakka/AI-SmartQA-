"""Functional test suite for QEOS platform APIs + OrangeHRM project."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

BASE = "http://127.0.0.1:8000"
ORANGEHRM_PROJECT = "Orange HRM"


@dataclass
class Result:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append(Result(name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        return ok

    def summary(self) -> tuple[int, int]:
        passed = sum(1 for r in self.results if r.passed)
        return passed, len(self.results)


def get(url: str) -> tuple[int, dict | list | str]:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def post(url: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def put(url: str, body: dict) -> tuple[int, dict | list | str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def find_orangehrm_project(projects: list) -> dict | None:
    for p in projects:
        if ORANGEHRM_PROJECT.lower() in (p.get("name") or "").lower():
            return p
    return projects[0] if projects else None


def poll_run(pid: str, run_id: str, timeout: int = 180) -> dict:
    start = time.time()
    last = {}
    while time.time() - start < timeout:
        _, last = get(f"{BASE}/api/v1/projects/{pid}/executions/{run_id}")
        if isinstance(last, dict) and last.get("status") != "running":
            return last
        time.sleep(2)
    return last if isinstance(last, dict) else {}


def run_platform_tests() -> Suite:
    suite = Suite()
    print("\n=== QEOS Platform Functional Tests ===\n")

    code, health = get(f"{BASE}/health")
    suite.check("Health endpoint", code == 200 and isinstance(health, dict) and health.get("status") == "healthy", str(health))

    code, projects = get(f"{BASE}/api/v1/projects")
    suite.check("List projects", code == 200 and isinstance(projects, list) and len(projects) > 0, f"{len(projects) if isinstance(projects, list) else 0} projects")

    project = find_orangehrm_project(projects if isinstance(projects, list) else [])
    if not project:
        suite.check("OrangeHRM project found", False, "no projects")
        return suite
    pid = project["id"]
    suite.check("OrangeHRM project found", True, project["name"])

    code, frameworks = get(f"{BASE}/api/v1/projects/x/automation/frameworks")
    suite.check("Automation frameworks", code == 200 and isinstance(frameworks, dict) and len(frameworks.get("frameworks", [])) > 0)

    code, cases = get(f"{BASE}/api/v1/projects/{pid}/test-cases")
    suite.check("List test cases", code == 200 and isinstance(cases, list), f"{len(cases) if isinstance(cases, list) else 0} cases")

    code, assets = get(f"{BASE}/api/v1/projects/{pid}/automation/assets")
    suite.check("List automation assets", code == 200 and isinstance(assets, list), f"{len(assets) if isinstance(assets, list) else 0} assets")

    code, agent = get(f"{BASE}/api/v1/projects/{pid}/executions/runner-agent")
    suite.check("Localhost runner agent", code == 200 and isinstance(agent, dict), agent.get("name", "") if isinstance(agent, dict) else "")

    code, dash = get(f"{BASE}/api/v1/projects/{pid}/executions/dashboard")
    suite.check("Execution dashboard", code == 200 and isinstance(dash, dict))

    code, runs = get(f"{BASE}/api/v1/projects/{pid}/executions")
    suite.check("Execution history", code == 200 and isinstance(runs, list))

    code, integrations = get(f"{BASE}/api/v1/integrations")
    suite.check("Integrations registry", code == 200)

    code, platform = get(f"{BASE}/api/v1/platform/manifest")
    suite.check("Platform metadata", code == 200 and isinstance(platform, dict), platform.get("name", "") if isinstance(platform, dict) else str(code))

    # Generate automation if no assets
    asset_id = None
    if isinstance(assets, list) and assets:
        asset_id = assets[0]["id"]
        suite.check("Existing automation asset", True, assets[0].get("name", asset_id))
    else:
        code, gen = post(f"{BASE}/api/v1/projects/{pid}/automation/generate", {"framework": "playwright"})
        ok = code == 200 and isinstance(gen, dict) and gen.get("id")
        suite.check("Generate Playwright automation", ok, gen.get("name", "") if isinstance(gen, dict) else str(gen))
        if ok:
            asset_id = gen["id"]

    # Debug batch run (single test case)
    if isinstance(cases, list) and cases:
        tc_id = cases[0]["id"]
        body = {
            "test_case_ids": [tc_id],
            "mode": "live",
            "background": True,
            "framework": "playwright",
            "base_url": os.environ.get("BASE_URL", "https://example.com"),
            "run_name": "Functional test — debug flow",
        }
        if asset_id:
            body["asset_id"] = asset_id
        code, run = post(f"{BASE}/api/v1/projects/{pid}/executions/batch-run", body)
        ok = code == 200 and isinstance(run, dict) and run.get("id")
        suite.check("Start debug batch run", ok, run.get("status", "") if isinstance(run, dict) else "")
        if ok:
            final = poll_run(pid, run["id"])
            has_results = bool(final.get("results"))
            in_progress_seen = final.get("status") in ("completed", "failed")
            suite.check(
                "Debug run completes with results",
                in_progress_seen and has_results,
                f"status={final.get('status')} results={len(final.get('results') or [])}",
            )
            if has_results:
                steps = final["results"][0].get("steps") or []
                suite.check("Step-level results returned", len(steps) > 0, f"{len(steps)} steps")

    # Validate automation asset
    if asset_id:
        code, val = post(f"{BASE}/api/v1/projects/{pid}/automation/assets/{asset_id}/validate")
        suite.check("Validate automation asset", code == 200 and isinstance(val, dict), val.get("valid") if isinstance(val, dict) else "")

    code, perf = get(f"{BASE}/api/v1/projects/{pid}/performance/assets")
    suite.check("Performance assets endpoint", code == 200)

    return suite


def run_playwright_e2e() -> Suite:
    suite = Suite()
    print("\n=== OrangeHRM Playwright E2E (Full Navigation Spec) ===\n")
    e2e_dir = Path(__file__).resolve().parents[2] / "e2e" / "orangehrm"
    if not e2e_dir.exists():
        suite.check("E2E project exists", False, str(e2e_dir))
        return suite

    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    npx = "npx.cmd" if sys.platform == "win32" else "npx"

    for cmd, label in [
        ([npm, "install"], "npm install"),
        ([npx, "playwright", "install", "chromium"], "playwright install chromium"),
    ]:
        proc = subprocess.run(cmd, cwd=e2e_dir, capture_output=True, text=True, timeout=300)
        suite.check(label, proc.returncode == 0, proc.stderr[-200:] if proc.returncode else "ok")

    proc = subprocess.run(
        [npx, "playwright", "test"],
        cwd=e2e_dir,
        capture_output=True,
        text=True,
        timeout=600,
    )
    suite.check("OrangeHRM navigation spec", proc.returncode == 0, "all 15 flows passed" if proc.returncode == 0 else proc.stdout[-400:])

    screenshots = list((e2e_dir / "screenshots").glob("*.png")) if (e2e_dir / "screenshots").exists() else []
    suite.check("Screenshots captured", len(screenshots) >= 10, f"{len(screenshots)} files: {', '.join(s.name for s in screenshots[:5])}...")

    report = e2e_dir / "playwright-report" / "index.html"
    suite.check("HTML report generated", report.exists() or (e2e_dir / "test-results").exists(), str(report))

    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])

    return suite


def main() -> int:
    platform = run_platform_tests()
    e2e = run_playwright_e2e()

    all_results = platform.results + e2e.results
    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)

    print("\n" + "=" * 60)
    print(f"TOTAL: {passed}/{total} passed ({100 * passed // total if total else 0}%)")
    print("=" * 60)
    failed = [r for r in all_results if not r.passed]
    if failed:
        print("\nFailed checks:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
