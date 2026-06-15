import json

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router
from app.models.schemas import AgentType


class SelfHealingAgent(BaseAgent):
    agent_type = AgentType.SELF_HEALING
    name = "Self-Healing Agent"
    description = "Repairs broken locators, API schema drift, and performance correlations"

    async def execute(self, context: AgentContext):
        failure_type = context.input_data.get("type", "ui")
        failure_data = context.input_data.get("failure", {})

        system_prompt = """You are the QEOS Self-Healing Agent.
Analyze test failures and propose repairs.

For UI: fix locators, XPath, CSS selectors.
For API: detect endpoint/parameter/schema changes.
For Performance: identify correlations, tokens, session IDs.

Respond with JSON:
{
  "healing_type": "ui|api|performance",
  "diagnosis": "root cause",
  "repairs": [{"original": "", "healed": "", "confidence": 0.95}],
  "impact_analysis": {"affected_tests": [], "severity": "low|medium|high"},
  "auto_retry_recommended": true
}"""

        router = get_llm_router()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(
                role=MessageRole.USER,
                content=f"Failure type: {failure_type}\n\n{json.dumps(failure_data, indent=2)}",
            ),
        ]

        try:
            response = await router.complete(
                messages,
                provider=context.llm_provider,
                model=context.llm_model,
                temperature=0.1,
            )
            return self.create_result(context, output={"analysis": response.content})
        except Exception as e:
            return self.create_result(context, error=str(e))


class DefectIntelligenceAgent(BaseAgent):
    agent_type = AgentType.DEFECT_INTELLIGENCE
    name = "Defect Intelligence Agent"
    description = "Root cause analysis, failure clustering, defect prediction, duplicate detection"

    async def execute(self, context: AgentContext):
        failures = context.input_data.get("failures", [])

        system_prompt = """You are the QEOS Defect Intelligence Agent.
Analyze test failures for patterns, root causes, and predictions.

Respond with JSON:
{
  "clusters": [{"id": "", "pattern": "", "failures": [], "root_cause": ""}],
  "duplicates": [{"primary": "", "duplicates": []}],
  "predictions": [{"area": "", "risk": "high", "reason": ""}],
  "recommendations": ["action items"]
}"""

        router = get_llm_router()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=json.dumps(failures, indent=2)),
        ]

        try:
            response = await router.complete(
                messages,
                provider=context.llm_provider,
                model=context.llm_model,
                temperature=0.2,
            )
            return self.create_result(context, output={"analysis": response.content})
        except Exception as e:
            return self.create_result(context, error=str(e))
