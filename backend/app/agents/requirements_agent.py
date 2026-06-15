import json
import re

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router
from app.models.schemas import AgentType, CoverageMatrix, RequirementsAgentOutput, TestCaseOutput


SYSTEM_PROMPT = """You are the QEOS Requirements Agent, an expert quality engineering analyst.
Given business requirements (BRD, FRD, user stories, acceptance criteria, Jira tickets),
produce structured test engineering outputs.

Respond ONLY with valid JSON matching this schema:
{
  "test_scenarios": ["scenario descriptions"],
  "test_cases": [
    {
      "title": "string",
      "description": "string",
      "steps": ["step 1", "step 2"],
      "expected_results": ["expected 1"],
      "priority": "high|medium|low",
      "tags": ["tag1"],
      "requirement_refs": ["REQ-001"]
    }
  ],
  "risk_analysis": {
    "high_risk_areas": ["area"],
    "mitigation_suggestions": ["suggestion"],
    "overall_risk_score": "low|medium|high"
  },
  "coverage_matrix": {
    "total_requirements": 0,
    "covered_requirements": 0,
    "coverage_percentage": 0.0,
    "gaps": ["uncovered requirement"]
  }
}"""


class RequirementsAgent(BaseAgent):
    agent_type = AgentType.REQUIREMENTS
    name = "Requirements Agent"
    description = "Analyzes BRD/FRD/user stories and generates test scenarios, cases, and coverage matrix"

    async def execute(self, context: AgentContext):
        content = context.input_data.get("content", "")
        source_type = context.input_data.get("source_type", "requirements")

        if not content:
            return self.create_result(context, error="No requirement content provided")

        router = get_llm_router()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
            LLMMessage(
                role=MessageRole.USER,
                content=f"Source type: {source_type}\n\nRequirements:\n{content}",
            ),
        ]

        try:
            response = await router.complete(
                messages,
                provider=context.llm_provider,
                model=context.llm_model,
                temperature=0.3,
            )
            parsed = self._parse_response(response.content)
            return self.create_result(context, output=parsed)
        except Exception as e:
            return self.create_result(context, error=str(e))

    def _parse_response(self, content: str) -> dict:
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            output = RequirementsAgentOutput(
                test_scenarios=data.get("test_scenarios", []),
                test_cases=[TestCaseOutput(**tc) for tc in data.get("test_cases", [])],
                risk_analysis=data.get("risk_analysis", {}),
                coverage_matrix=CoverageMatrix(**data.get("coverage_matrix", {
                    "total_requirements": 0,
                    "covered_requirements": 0,
                    "coverage_percentage": 0.0,
                })),
            )
            return output.model_dump(mode="json")
        raise ValueError("Could not parse LLM response as JSON")
