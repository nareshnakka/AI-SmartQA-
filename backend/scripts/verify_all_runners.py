"""Report which automation and performance runners are ready on this machine."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as script: add backend to path
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.runners.setup_status import collect_runner_status  # noqa: E402


def main() -> int:
    if "--json" in sys.argv:
        print(json.dumps(collect_runner_status(), indent=2))
        return 0

    status = collect_runner_status()
    auto = status["automation"]
    perf = status["performance"]

    print("Automation runners:")
    for name, info in auto.items():
        mark = "OK" if info["ready"] else "MISSING"
        line = f"  [{mark}] {name}"
        if not info["ready"] and info.get("hint"):
            line += f" — {info['hint']}"
        print(line)

    print("\nPerformance tools:")
    for name, info in perf.items():
        mark = "OK" if info["ready"] else "OPTIONAL"
        line = f"  [{mark}] {name}"
        if not info["ready"] and info.get("hint"):
            line += f" — {info['hint']}"
        print(line)

    if not auto["playwright"]["ready"]:
        print("\nCRITICAL: Playwright is required for QA Discovery and live debug.")
        return 1
    if not status["k6_available"]:
        print("\nWARN: k6 not on PATH — live performance runs simulate until k6 is installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
