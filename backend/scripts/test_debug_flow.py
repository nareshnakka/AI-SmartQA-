"""Test debug flow batch execution."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(url: str) -> dict:
    return json.loads(urllib.request.urlopen(url, timeout=30).read())


def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def main() -> None:
    projects = get(f"{BASE}/api/v1/projects")
    if not projects:
        print("no projects")
        return
    pid = projects[0]["id"]
    print("project", pid, projects[0].get("name"))
    cases = get(f"{BASE}/api/v1/projects/{pid}/test-cases")
    print("cases", len(cases))
    if not cases:
        return
    tc = next((c for c in cases if (c.get("steps") or [])), cases[0])
    print("tc", tc["id"], tc["title"], "steps", len(tc.get("steps") or []))

    run = post(
        f"{BASE}/api/v1/projects/{pid}/executions/batch-run",
        {
            "test_case_ids": [tc["id"]],
            "mode": "live",
            "background": True,
            "framework": "playwright",
            "base_url": "https://opensource-demo.orangehrmlive.com",
        },
    )
    run_id = run["id"]
    print("run", run_id, run["status"], "progress", run.get("progress"))

    for i in range(60):
        time.sleep(0.3)
        r = get(f"{BASE}/api/v1/projects/{pid}/executions/{run_id}")
        n_results = len(r.get("results") or [])
        res0 = (r.get("results") or [{}])[0] if n_results else {}
        print(i, r["status"], "results", n_results, "r0status", res0.get("status"), "progress", r.get("progress", {}).get("current"))
        if r["status"] != "running":
            for res in r.get("results") or []:
                print(" result", res.get("title"), res.get("status"), "steps", len(res.get("steps") or []))
                for s in (res.get("steps") or [])[:5]:
                    print("  ", s.get("order"), s.get("status"), s.get("description", "")[:60])
            break


if __name__ == "__main__":
    main()
