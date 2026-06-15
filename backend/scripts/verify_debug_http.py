"""HTTP verify debug on configurable port (default 8001)."""
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("QEOS_API", "http://127.0.0.1:8001")
PID = "be157118-6293-48b2-a3c4-5a982d833b27"
TC_TITLE = "End-to-end session walkthrough"


def main() -> None:
    h = json.loads(urllib.request.urlopen(f"{BASE}/health", timeout=10).read())
    print("HEALTH", h)

    assets = json.loads(urllib.request.urlopen(f"{BASE}/api/v1/projects/{PID}/automation/assets").read())
    asset = assets[0]
    print("ASSET", asset["name"], "v", asset.get("version"), "files", len(asset.get("files", [])))

    cases = json.loads(urllib.request.urlopen(f"{BASE}/api/v1/projects/{PID}/test-cases").read())
    tc = next(c for c in cases if TC_TITLE in c["title"])
    print("TC", tc["title"], len(tc.get("steps", [])))

    body = json.dumps(
        {
            "test_case_ids": [tc["id"]],
            "mode": "live",
            "background": True,
            "framework": asset["framework"],
            "base_url": "https://opensource-demo.orangehrmlive.com",
            "asset_id": asset["id"],
        }
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/projects/{PID}/executions/batch-run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    run = json.loads(urllib.request.urlopen(req, timeout=30).read())
    print("STARTED", run["id"], run["status"])

    for i in range(180):
        time.sleep(2)
        r = json.loads(urllib.request.urlopen(f"{BASE}/api/v1/projects/{PID}/executions/{run['id']}").read())
        if r["status"] != "running":
            logs = r.get("logs") or ""
            print("FINAL", r["status"])
            print("EXECUTOR", "asset_live_v2" in logs)
            print("ORANGEHRM", "orangehrm-navigation" in logs)
            print("LOGS_TAIL\n", logs[-1200:].encode("ascii", errors="replace").decode("ascii"))
            if r.get("results"):
                res = r["results"][0]
                print("RESULT", res.get("status"), (res.get("error") or "")[:300])
            return
        prog = r.get("progress") or {}
        print(i, "running", prog.get("phase"), prog.get("detail", "")[:80])

    print("TIMEOUT")
    sys.exit(1)


if __name__ == "__main__":
    main()
