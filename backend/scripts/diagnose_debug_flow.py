"""Diagnose debug flow for End-to-end session walkthrough."""
import json
import os
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
PID = "be157118-6293-48b2-a3c4-5a982d833b27"


def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=30).read())


def post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


def main():
    health = get(f"{BASE}/health")
    print("health", health)

    cases = get(f"{BASE}/api/v1/projects/{PID}/test-cases")
    tc = next(c for c in cases if "End-to-end" in c.get("title", ""))
    print("test_case", tc["id"], tc["title"], "steps", len(tc.get("steps") or []), "status", tc.get("status"))

    assets = get(f"{BASE}/api/v1/projects/{PID}/automation/assets")
    asset = assets[0]
    print("asset", asset["id"], asset["name"], "files", len(asset.get("files") or []))
    for f in (asset.get("files") or [])[:8]:
        print(" ", f.get("path"), f.get("type", ""))

    body = {
        "test_case_ids": [tc["id"]],
        "mode": "live",
        "background": False,
        "framework": asset["framework"],
        "base_url": os.environ.get("BASE_URL", "https://example.com"),
        "asset_id": asset["id"],
        "run_name": "Debug diagnose",
    }
    print("\nstarting batch-run (sync)...")
    run = post(f"{BASE}/api/v1/projects/{PID}/executions/batch-run", body)
    print("status", run.get("status"))
    print("summary", run.get("summary"))
    logs = run.get("logs") or ""
    print("uses_asset", "automation asset" in logs or "asset_live_v2" in logs)
    print("logs tail:\n", logs[-1500:])
    if run.get("results"):
        r = run["results"][0]
        print("result", r.get("status"), "file", r.get("file"), "error", (r.get("error") or "")[:300])
        print("steps sample", (r.get("steps") or [])[:3])


if __name__ == "__main__":
    main()
