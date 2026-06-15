"""QEOS Native Intelligence Engine — central orchestrator."""

import json
import re
from enum import Enum

import structlog

from app.intelligence.generators import (
    AutomationGenerator,
    DefectIntelligenceGenerator,
    PerformanceGenerator,
    RequirementsGenerator,
    SelfHealingGenerator,
    TestDesignGenerator,
)

logger = structlog.get_logger()


class TaskType(str, Enum):
    REQUIREMENTS = "requirements"
    TEST_DESIGN = "test_design"
    AUTOMATION = "automation"
    PERFORMANCE = "performance"
    SELF_HEALING = "self_healing"
    DEFECT_INTELLIGENCE = "defect_intelligence"
    GENERAL = "general"


# Map system prompt keywords to task types
TASK_DETECTORS: list[tuple[TaskType, list[str]]] = [
    (TaskType.REQUIREMENTS, ["requirements agent", "test scenarios", "coverage matrix", "brd", "user stor"]),
    (TaskType.TEST_DESIGN, ["test design agent", "functional_tests", "regression_pack", "smoke_pack"]),
    (TaskType.AUTOMATION, ["automation agent", "page object", "playwright", "selenium", "cypress"]),
    (TaskType.PERFORMANCE, ["performance engineering", "workload model", "jmeter", "k6 script"]),
    (TaskType.SELF_HEALING, ["self-healing", "locator healing", "locator repair"]),
    (TaskType.DEFECT_INTELLIGENCE, ["defect intelligence", "failure clustering", "root cause"]),
]


class QEOSIntelligenceEngine:
    """
    Proprietary QEOS intelligence engine.
    Uses domain knowledge, pattern matching, and template generation —
    no external LLM API required.
    """

    VERSION = "1.1.0"

    def __init__(self) -> None:
        self.requirements = RequirementsGenerator()
        self.test_design = TestDesignGenerator()
        self.automation = AutomationGenerator()
        self.performance = PerformanceGenerator()
        self.self_healing = SelfHealingGenerator()
        self.defect = DefectIntelligenceGenerator()

    def detect_task(self, system_prompt: str, user_content: str) -> TaskType:
        combined = (system_prompt + " " + user_content).lower()
        for task_type, keywords in TASK_DETECTORS:
            if any(kw in combined for kw in keywords):
                return task_type
        return TaskType.GENERAL

    def generate(self, task: TaskType, input_data: dict) -> dict:
        logger.info("qeos_native_generate", task=task.value)

        generators = {
            TaskType.REQUIREMENTS: lambda: self.requirements.generate(
                input_data.get("content", ""),
                input_data.get("source_type", "requirements"),
            ),
            TaskType.TEST_DESIGN: lambda: self.test_design.generate(input_data),
            TaskType.AUTOMATION: lambda: self.automation.generate(input_data),
            TaskType.PERFORMANCE: lambda: self.performance.generate(input_data),
            TaskType.SELF_HEALING: lambda: self.self_healing.generate(input_data),
            TaskType.DEFECT_INTELLIGENCE: lambda: self.defect.generate(input_data),
        }

        if task in generators:
            result = generators[task]()
            result["_qeos_engine_version"] = self.VERSION
            return result

        # General fallback — try to parse as requirements
        content = input_data.get("content") or json.dumps(input_data)
        return self.requirements.generate(content if isinstance(content, str) else json.dumps(content))

    def generate_from_messages(self, system_prompt: str, user_content: str) -> str:
        """Generate JSON response from LLM-style messages (for provider compatibility)."""
        task = self.detect_task(system_prompt, user_content)
        input_data = self._parse_user_input(user_content)
        result = self.generate(task, input_data)
        return json.dumps(result, indent=2)

    def _parse_user_input(self, user_content: str) -> dict:
        # Extract source type
        source_match = re.search(r"Source type:\s*(\w+)", user_content, re.IGNORECASE)
        source_type = source_match.group(1) if source_match else "requirements"

        # Extract requirements block
        req_match = re.search(r"Requirements:\s*\n(.+)", user_content, re.DOTALL | re.IGNORECASE)
        if req_match:
            return {"content": req_match.group(1).strip(), "source_type": source_type}

        # Try JSON input (for chained agents)
        json_match = re.search(r"\{.*\}", user_content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try "Generate automation for:" or "Design tests for:"
        for prefix in ["Generate automation for:", "Design tests for:", "Failure type:"]:
            if prefix.lower() in user_content.lower():
                idx = user_content.lower().index(prefix.lower())
                remainder = user_content[idx + len(prefix):].strip()
                try:
                    return json.loads(remainder)
                except json.JSONDecodeError:
                    if "Failure type:" in prefix:
                        parts = remainder.split("\n", 1)
                        return {"type": parts[0].strip(), "failure": json.loads(parts[1]) if len(parts) > 1 else {}}
                    return {"content": remainder}

        return {"content": user_content, "source_type": source_type}


_engine: QEOSIntelligenceEngine | None = None


def get_intelligence_engine() -> QEOSIntelligenceEngine:
    global _engine
    if _engine is None:
        _engine = QEOSIntelligenceEngine()
    return _engine
