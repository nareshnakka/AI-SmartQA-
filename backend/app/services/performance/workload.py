"""Workload profile definitions — smoke, load, stress, spike, soak."""

WORKLOAD_PROFILES = {
    "smoke": {
        "name": "Smoke",
        "description": "Minimal VUs to verify script health",
        "virtual_users": 5,
        "ramp_up": "1m",
        "duration": "5m",
        "ramp_down": "1m",
        "target_rps": None,
        "stages": [
            {"duration": "1m", "target": 5},
            {"duration": "3m", "target": 5},
            {"duration": "1m", "target": 0},
        ],
    },
    "load": {
        "name": "Load",
        "description": "Expected production load",
        "virtual_users": 100,
        "ramp_up": "5m",
        "duration": "30m",
        "ramp_down": "5m",
        "target_rps": 200,
        "stages": [
            {"duration": "5m", "target": 100},
            {"duration": "30m", "target": 100},
            {"duration": "5m", "target": 0},
        ],
    },
    "stress": {
        "name": "Stress",
        "description": "Beyond normal capacity to find breaking point",
        "virtual_users": 500,
        "ramp_up": "10m",
        "duration": "20m",
        "ramp_down": "5m",
        "target_rps": 1000,
        "stages": [
            {"duration": "5m", "target": 100},
            {"duration": "5m", "target": 300},
            {"duration": "5m", "target": 500},
            {"duration": "10m", "target": 500},
            {"duration": "5m", "target": 0},
        ],
    },
    "spike": {
        "name": "Spike",
        "description": "Sudden traffic burst",
        "virtual_users": 300,
        "ramp_up": "30s",
        "duration": "5m",
        "ramp_down": "2m",
        "target_rps": 500,
        "stages": [
            {"duration": "30s", "target": 300},
            {"duration": "3m", "target": 300},
            {"duration": "2m", "target": 0},
        ],
    },
    "soak": {
        "name": "Soak",
        "description": "Extended duration for memory leak detection",
        "virtual_users": 50,
        "ramp_up": "5m",
        "duration": "2h",
        "ramp_down": "5m",
        "target_rps": 50,
        "stages": [
            {"duration": "5m", "target": 50},
            {"duration": "2h", "target": 50},
            {"duration": "5m", "target": 0},
        ],
    },
}


def build_workload_model(profile_key: str, overrides: dict | None = None) -> dict:
    base = dict(WORKLOAD_PROFILES.get(profile_key, WORKLOAD_PROFILES["load"]))
    if overrides:
        base.update({k: v for k, v in overrides.items() if v is not None})
    return base


def apply_throughput_to_k6_options(workload: dict, throughput: dict | None) -> dict:
    """Merge throughput targets (RPS, p95 SLA) into k6 options."""
    opts = {
        "stages": workload.get("stages", []),
        "thresholds": {},
    }
    if throughput:
        if throughput.get("target_rps"):
            opts["thresholds"]["http_reqs"] = [f"rate>{throughput['target_rps']}"]
        if throughput.get("p95_ms"):
            opts["thresholds"]["http_req_duration"] = [f"p(95)<{throughput['p95_ms']}"]
        if throughput.get("error_rate"):
            opts["thresholds"]["http_req_failed"] = [f"rate<{throughput['error_rate']}"]
    else:
        opts["thresholds"] = {
            "http_req_duration": ["p(95)<500"],
            "http_req_failed": ["rate<0.01"],
        }
    return opts
