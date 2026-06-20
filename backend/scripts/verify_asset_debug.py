"""Verify debug batch-run uses automation asset scripts."""
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
PID = "be157118-6293-48b2-a3c4-5a982d833b27"


def main() -> None:
    assets = json.loads(urllib.request.urlopen(f"{BASE}/api/v1/projects/{PID}/automation/assets").read())
    asset = assets[0]
    cases = json.loads(urllib.request.urlopen(f"{BASE}/api/v1/projects/{PID}/test-cases").read())
    tc = cases[0]

    body = json.dumps({
        "test_case_ids": [tc["id"]],
        "mode": "live",
        "background": False,
        "framework": asset["framework"],
        "base_url": os.environ.get("BASE_URL", "https://example.com"),
        "asset_id": asset["id"],
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/projects/{PID}/executions/batch-run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    run = json.loads(urllib.request.urlopen(req).read())
    run_id = run["id"]
    print("asset", asset["name"], "files", len(asset.get("files", [])))
    print("started", run_id)

    for i in range(120):
        time.sleep(2)
        r = json.loads(urllib.request.urlopen(f"{BASE}/api/v1/projects/{PID}/executions/{run_id}").read())
        if r["status"] != "running":
            print("status", r["status"])
            logs = r.get("logs") or ""
            print("uses asset:", "Materialized" in logs or "automation asset" in logs)
            print("npm/playwright:", "npm install" in logs, "playwright test" in logs or "playwright install" in logs)
            print("logs tail:\n", logs[-1000:])
            if r.get("results"):
                res = r["results"][0]
                print("result", res.get("status"), "file", res.get("file"), "error", (res.get("error") or "")[:200])
            return
        print(i, "running", r.get("progress", {}).get("current"))


if __name__ == "__main__":
    main()
