import json
import re

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, MessageRole
from app.llm.router import get_llm_router
from app.models.schemas import AgentType, AutomationFramework


FRAMEWORK_PROMPTS = {
    AutomationFramework.PLAYWRIGHT: "Generate TypeScript Playwright tests with page object model.",
    AutomationFramework.SELENIUM: "Generate Java Selenium WebDriver tests with Page Factory pattern.",
    AutomationFramework.CYPRESS: "Generate JavaScript Cypress tests with custom commands.",
    AutomationFramework.APPIUM: "Generate Python Appium mobile automation scripts.",
    AutomationFramework.WEBDRIVERIO: "Generate TypeScript WebdriverIO tests with page objects.",
    AutomationFramework.ROBOT_FRAMEWORK: "Generate Robot Framework keyword-driven tests.",
}


class AutomationAgent(BaseAgent):
    agent_type = AgentType.AUTOMATION
    name = "Automation Agent"
    description = "Generates framework-specific automation scripts from test cases"

    async def execute(self, context: AgentContext):
        framework = context.input_data.get("framework", AutomationFramework.PLAYWRIGHT.value)
        test_cases = context.input_data.get("test_cases", context.input_data)
        language = context.input_data.get("language", "typescript")

        framework_enum = AutomationFramework(framework) if framework in [f.value for f in AutomationFramework] else AutomationFramework.PLAYWRIGHT
        framework_hint = FRAMEWORK_PROMPTS.get(framework_enum, "Generate automation tests.")

        system_prompt = f"""You are the QEOS Automation Agent.
{framework_hint}
Language: {language}

Respond with JSON:
{{
  "framework": "{framework}",
  "language": "{language}",
  "files": [
    {{"path": "tests/example.spec.ts", "content": "// full file content", "type": "test"}},
    {{"path": "pages/LoginPage.ts", "content": "// page object", "type": "page_object"}}
  ],
  "dependencies": ["package names"],
  "ci_pipeline_snippet": "yaml snippet for CI"
}}"""

        router = get_llm_router()
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(
                role=MessageRole.USER,
                content=f"Generate automation for:\n{json.dumps(test_cases, indent=2)}",
            ),
        ]

        try:
            response = await router.complete(
                messages,
                provider=context.llm_provider,
                model=context.llm_model,
                temperature=0.2,
            )
            parsed = self._parse_json(response.content)
            return self.create_result(
                context,
                output=parsed,
                artifacts=[{"type": "automation_code", "files": parsed.get("files", [])}],
            )
        except Exception as e:
            return self.create_result(context, error=str(e))

    def _parse_json(self, content: str) -> dict:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"raw_output": content, "files": []}
