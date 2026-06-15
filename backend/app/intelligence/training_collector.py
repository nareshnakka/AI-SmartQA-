"""Collects agent input/output pairs for future QEOS model fine-tuning."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.config import settings
from app.models.schemas import AgentType

logger = structlog.get_logger()

# Instruction templates per agent — used as fine-tuning system prompts
AGENT_INSTRUCTIONS: dict[str, str] = {
    AgentType.REQUIREMENTS.value: (
        "You are the QEOS Requirements Agent. Given business requirements, "
        "generate test scenarios, test cases, risk analysis, and coverage matrix as JSON."
    ),
    AgentType.TEST_DESIGN.value: (
        "You are the QEOS Test Design Agent. Given requirements or test scenarios, "
        "generate functional, API, performance, and security test designs as JSON."
    ),
    AgentType.AUTOMATION.value: (
        "You are the QEOS Automation Agent. Given test cases, generate "
        "framework-specific automation scripts with page objects as JSON."
    ),
    AgentType.PERFORMANCE.value: (
        "You are the QEOS Performance Agent. Given functional flows, generate "
        "workload models, k6/JMeter scripts, and correlation rules as JSON."
    ),
    AgentType.SELF_HEALING.value: (
        "You are the QEOS Self-Healing Agent. Given test failure details, "
        "diagnose root cause and propose locator/API repairs as JSON."
    ),
    AgentType.DEFECT_INTELLIGENCE.value: (
        "You are the QEOS Defect Intelligence Agent. Given failure logs, "
        "cluster failures, identify root causes, and predict risks as JSON."
    ),
}


class TrainingDataCollector:
    """
    Automatically captures successful agent runs as training pairs.
    Format: JSONL with {instruction, input, output, metadata}
    Compatible with backend/training/train.py
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir:
            self.data_dir = data_dir
        elif settings.qeos_training_data_dir:
            backend_root = Path(__file__).resolve().parent.parent.parent
            self.data_dir = backend_root / settings.qeos_training_data_dir
        else:
            backend_root = Path(__file__).resolve().parent.parent.parent
            self.data_dir = backend_root / "training" / "data" / "collected"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "collected.jsonl"

    @property
    def enabled(self) -> bool:
        return settings.qeos_training_collect

    def record(
        self,
        agent_type: AgentType,
        input_data: dict[str, Any],
        output: dict[str, Any],
        provider: str = "qeos-native",
        model: str = "qeos-intelligence-v1",
        run_id: str | None = None,
    ) -> bool:
        if not self.enabled:
            return False

        instruction = AGENT_INSTRUCTIONS.get(agent_type.value, "You are a QEOS quality engineering agent.")

        # Strip internal metadata from output for cleaner training data
        clean_output = {k: v for k, v in output.items() if not k.startswith("_")}

        record = {
            "instruction": instruction,
            "input": self._format_input(agent_type, input_data),
            "output": json.dumps(clean_output, ensure_ascii=False),
            "metadata": {
                "agent_type": agent_type.value,
                "provider": provider,
                "model": model,
                "run_id": run_id,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info("training_data_collected", agent=agent_type.value, run_id=run_id)
            return True
        except Exception as e:
            logger.error("training_data_collect_failed", error=str(e))
            return False

    def _format_input(self, agent_type: AgentType, input_data: dict) -> str:
        if agent_type == AgentType.REQUIREMENTS:
            content = input_data.get("content", "")
            source = input_data.get("source_type", "requirements")
            return f"Source type: {source}\n\nRequirements:\n{content}"
        return json.dumps(input_data, ensure_ascii=False, indent=2)

    def get_stats(self) -> dict:
        if not self._file.exists():
            return {"total_records": 0, "by_agent": {}, "file": str(self._file)}

        records = self.load_all()
        by_agent: dict[str, int] = {}
        for r in records:
            agent = r.get("metadata", {}).get("agent_type", "unknown")
            by_agent[agent] = by_agent.get(agent, 0) + 1

        return {
            "total_records": len(records),
            "by_agent": by_agent,
            "file": str(self._file),
            "collection_enabled": self.enabled,
        }

    def load_all(self) -> list[dict]:
        if not self._file.exists():
            return []
        records = []
        with open(self._file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def export_jsonl(self, output_path: Path | None = None) -> Path:
        """Export clean training JSONL (instruction/input/output only)."""
        output = output_path or self.data_dir / "export.jsonl"
        records = self.load_all()
        with open(output, "w", encoding="utf-8") as f:
            for r in records:
                clean = {
                    "instruction": r["instruction"],
                    "input": r["input"],
                    "output": r["output"],
                }
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")
        return output

    def clear(self) -> int:
        count = len(self.load_all())
        if self._file.exists():
            self._file.unlink()
        return count


_collector: TrainingDataCollector | None = None


def get_training_collector() -> TrainingDataCollector:
    global _collector
    if _collector is None:
        _collector = TrainingDataCollector()
    return _collector
