import json
import re

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router
from app.models.schemas import AgentType


SYSTEM_PROMPT = """You are the QEOS Test Design Agent.
Generate comprehensive test designs from requirements or test scenarios.

Respond ONLY with valid JSON:
{
  "functional_tests": [{"name": "", "type": "ui|api|e2e", "cases": []}],
  "api_tests": [{"endpoint": "", "method": "", "scenarios": []}],
  "performance_scenarios": [{"name": "", "description": "", "sla_targets": {}}],
  "security_scenarios": [{"name": "", "category": "auth|injection|xss", "steps": []}],
  "regression_pack": {"name": "", "test_ids": []},
  "smoke_pack": {"name": "", "test_ids": []}
}"""


class TestDesignAgent(BaseAgent):
    agent_type = AgentType.TEST_DESIGN
    name = "Test Design Agent"
    description = "Generates functional, API, performance, and security test designs"

    async def execute(self, context: AgentContext):
        input_text = json.dumps(context.input_data, indent=2)
        router = get_llm_router()

        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
            LLMMessage(role=MessageRole.USER, content=f"Design tests for:\n{input_text}"),
        ]

        try:
            response = await router.complete(
                messages,
                provider=context.llm_provider,
                model=context.llm_model,
                temperature=0.4,
            )
            parsed = self._parse_json(response.content)
            return self.create_result(context, output=parsed)
        except Exception as e:
            return self.create_result(context, error=str(e))

    def _parse_json(self, content: str) -> dict:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("Could not parse LLM response")
