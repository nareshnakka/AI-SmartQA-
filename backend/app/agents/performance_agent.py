import json
import re

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router
from app.models.schemas import AgentType, PerformanceTool


class PerformanceAgent(BaseAgent):
    agent_type = AgentType.PERFORMANCE
    name = "Performance Engineering Agent"
    description = "Generates workload models, JMeter/k6/Gatling scripts, and load profiles"

    async def execute(self, context: AgentContext):
        tool = context.input_data.get("tool", PerformanceTool.K6.value)
        flows = context.input_data.get("flows", [])
        distribution = context.input_data.get("distribution", {})

        system_prompt = f"""You are the QEOS Performance Engineering Agent.
Generate performance test assets for tool: {tool}

If flow distribution is provided (e.g. Flow A=50%, B=30%, C=20%), build workload model accordingly.

Respond with JSON:
{{
  "tool": "{tool}",
  "workload_model": {{"virtual_users": 100, "ramp_up": "5m", "duration": "30m", "flows": []}},
  "scripts": [{{"path": "load-test.js", "content": "script content"}}],
  "correlation_rules": [],
  "parameterization": {{}},
  "data_models": []
}}"""

        user_content = json.dumps({
            "functional_flows": flows,
            "distribution": distribution,
            "requirements": context.input_data.get("requirements", ""),
        }, indent=2)

        router = get_llm_router()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=user_content),
        ]

        try:
            response = await router.complete(
                messages,
                provider=context.llm_provider,
                model=context.llm_model,
                temperature=0.2,
            )
            parsed = self._parse_json(response.content)
            return self.create_result(context, output=parsed)
        except Exception as e:
            return self.create_result(context, error=str(e))

    def _parse_json(self, content: str) -> dict:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"raw_output": content}
