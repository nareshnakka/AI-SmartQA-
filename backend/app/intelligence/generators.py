"""Native generators for each QEOS agent task — no external LLM required."""

import json
from uuid import uuid4

from app.intelligence.knowledge_base import (
    PERFORMANCE_KEYWORDS,
    SECURITY_KEYWORDS,
    TEST_PATTERNS,
    TestPattern,
)
from app.intelligence.parser import ParsedRequirement, RequirementParser
from app.models.schemas import CoverageMatrix, TestCaseOutput


class RequirementsGenerator:
    """Generates test scenarios, cases, risk analysis, and coverage from requirements."""

    def __init__(self) -> None:
        self.parser = RequirementParser()

    def generate(self, content: str, source_type: str = "requirements") -> dict:
        requirements = self.parser.parse(content, source_type)
        if not requirements:
            requirements = [ParsedRequirement(
                id="REQ-001",
                title="General Requirement",
                description=content[:500],
            )]

        test_cases: list[TestCaseOutput] = []
        scenarios: list[str] = []
        covered_ids: set[str] = set()

        for req in requirements:
            req_scenarios, req_cases = self._generate_for_requirement(req)
            scenarios.extend(req_scenarios)
            test_cases.extend(req_cases)
            if req_cases:
                covered_ids.add(req.id)

        gaps = [r.id for r in requirements if r.id not in covered_ids]
        total = len(requirements)
        covered = len(covered_ids)
        coverage_pct = round((covered / total) * 100, 1) if total else 0.0

        risk = self._analyze_risk(requirements, test_cases)

        return {
            "test_scenarios": scenarios,
            "test_cases": [tc.model_dump(mode="json") for tc in test_cases],
            "risk_analysis": risk,
            "coverage_matrix": CoverageMatrix(
                total_requirements=total,
                covered_requirements=covered,
                coverage_percentage=coverage_pct,
                gaps=[f"{gid}: {next((r.title for r in requirements if r.id == gid), '')}" for gid in gaps],
            ).model_dump(mode="json"),
            "_engine": "qeos-native",
        }

    def _generate_for_requirement(
        self, req: ParsedRequirement
    ) -> tuple[list[str], list[TestCaseOutput]]:
        scenarios: list[str] = []
        cases: list[TestCaseOutput] = []
        text = f"{req.title} {req.description} {' '.join(req.keywords)}".lower()

        matched_patterns = self._match_patterns(text)
        if not matched_patterns:
            matched_patterns = [self._generic_pattern(req)]

        for pattern in matched_patterns:
            scenario = f"{pattern.name} for {req.id}: {req.title[:60]}"
            scenarios.append(scenario)

            steps = self._customize_steps(pattern.steps_template, req)
            expected = self._customize_expected(pattern.expected_template, req)

            cases.append(TestCaseOutput(
                title=f"{pattern.name} — {req.id}",
                description=f"Verify {pattern.name.lower()} for requirement: {req.title}",
                steps=steps,
                expected_results=expected,
                priority=max(req.priority, pattern.priority, key=lambda p: {"high": 3, "medium": 2, "low": 1}.get(p, 2)),
                tags=list(set(pattern.tags + req.keywords)),
                requirement_refs=[req.id],
            ))

        # Acceptance-criteria-driven cases
        for i, ac in enumerate(req.acceptance_criteria):
            cases.append(TestCaseOutput(
                title=f"AC Validation {req.id}-{i + 1}",
                description=f"Validate acceptance criterion: {ac}",
                steps=[f"Set up preconditions for {req.id}", f"Execute: {ac}", "Observe system behavior"],
                expected_results=[f"Acceptance criterion is met: {ac}"],
                priority=req.priority,
                tags=["acceptance-criteria"] + req.keywords,
                requirement_refs=[req.id],
            ))
            scenarios.append(f"Acceptance criteria validation for {req.id}: {ac[:60]}")

        return scenarios, cases

    def _match_patterns(self, text: str) -> list[TestPattern]:
        matched = []
        for pattern in TEST_PATTERNS:
            if any(kw in text for kw in pattern.trigger_keywords):
                matched.append(pattern)
        return matched[:4]  # Cap per requirement to avoid explosion

    def _generic_pattern(self, req: ParsedRequirement) -> TestPattern:
        return TestPattern(
            name="Functional Validation",
            category="functional",
            trigger_keywords=[],
            steps_template=[
                f"Navigate to the feature related to: {req.title[:50]}",
                "Perform the primary user action described in the requirement",
                "Verify the system response",
            ],
            expected_template=[
                "System behaves as specified in the requirement",
                "No errors or unexpected behavior occurs",
            ],
            priority=req.priority,
            tags=["functional"] + req.keywords,
        )

    def _customize_steps(self, template: list[str], req: ParsedRequirement) -> list[str]:
        steps = []
        for step in template:
            step = step.replace("{actor}", req.actor or "user")
            step = step.replace("{action}", req.action or req.title[:40])
            if req.action and "Navigate" not in step:
                step = f"{step} (Context: {req.action[:60]})"
            steps.append(step)
        return steps

    def _customize_expected(self, template: list[str], req: ParsedRequirement) -> list[str]:
        results = list(template)
        if req.benefit:
            results.append(f"Business benefit achieved: {req.benefit[:80]}")
        return results

    def _analyze_risk(
        self, requirements: list[ParsedRequirement], test_cases: list[TestCaseOutput]
    ) -> dict:
        high_risk = []
        for req in requirements:
            text = f"{req.title} {req.description}".lower()
            if any(kw in text for kw in ["payment", "security", "authentication", "pii", "financial"]):
                high_risk.append(f"{req.id}: {req.title[:60]}")

        high_priority_count = sum(1 for tc in test_cases if tc.priority == "high")
        overall = "high" if len(high_risk) >= 2 else "medium" if high_risk else "low"

        return {
            "high_risk_areas": high_risk or ["No critical risk areas identified"],
            "mitigation_suggestions": [
                "Prioritize high-risk test cases in regression suite",
                "Add security and negative test coverage for authentication flows",
                "Include performance validation for critical user journeys",
            ],
            "overall_risk_score": overall,
            "high_priority_tests": high_priority_count,
            "total_tests_generated": len(test_cases),
        }


class TestDesignGenerator:
    """Generates test design artifacts from requirements or test cases."""

    def generate(self, input_data: dict) -> dict:
        content = input_data.get("content") or json.dumps(input_data)
        req_gen = RequirementsGenerator()
        req_output = req_gen.generate(content if isinstance(content, str) else json.dumps(content))

        test_cases = req_output.get("test_cases", [])
        functional = []
        api_tests = []
        security = []
        performance = []

        for tc in test_cases:
            tags = tc.get("tags", [])
            name = tc.get("title", "Test")
            tc_id = tc.get("id", str(uuid4()))

            if "api" in tags or "integration" in tags:
                api_tests.append({
                    "endpoint": f"/api/{tags[0] if tags else 'resource'}",
                    "method": "GET/POST",
                    "scenarios": [name],
                    "test_id": tc_id,
                })
            elif "security" in tags:
                security.append({
                    "name": name,
                    "category": "auth" if "authentication" in tags else "validation",
                    "steps": tc.get("steps", []),
                })
            elif "performance" in tags or "load" in tags:
                performance.append({
                    "name": name,
                    "description": tc.get("description", ""),
                    "sla_targets": {"p95_ms": 500, "error_rate_pct": 1.0},
                })
            else:
                test_type = "e2e" if "e2e" in tags else "ui"
                functional.append({"name": name, "type": test_type, "cases": [tc], "test_id": tc_id})

        all_ids = [tc.get("id", str(i)) for i, tc in enumerate(test_cases)]
        smoke_ids = [tc.get("id") for tc in test_cases if tc.get("priority") == "high"][:5]

        return {
            "functional_tests": functional,
            "api_tests": api_tests or [{"endpoint": "/api/health", "method": "GET", "scenarios": ["Health check"]}],
            "performance_scenarios": performance or [{
                "name": "Baseline Load Test",
                "description": "Validate system under normal load",
                "sla_targets": {"p95_ms": 1000, "throughput_rps": 100},
            }],
            "security_scenarios": security or [{
                "name": "Authentication Boundary Test",
                "category": "auth",
                "steps": ["Attempt access without credentials", "Verify 401 response"],
            }],
            "regression_pack": {"name": "Full Regression", "test_ids": all_ids},
            "smoke_pack": {"name": "Smoke Pack", "test_ids": smoke_ids or all_ids[:3]},
            "_engine": "qeos-native",
        }


class AutomationGenerator:
    """Generates framework-specific automation code templates."""

    TEMPLATES = {
        "playwright": {
            "language": "typescript",
            "deps": ["@playwright/test"],
            "test_file": '''import {{ test, expect }} from '@playwright/test';
import {{ {page_class} }} from '../pages/{page_class}';

test.describe('{suite_name}', () => {{
  test('{test_name}', async ({{ page }}) => {{
    const pg = new {page_class}(page);
{steps}
    // Expected: {expected}
  }});
}});
''',
            "page_object": '''import {{ Page, Locator }} from '@playwright/test';

export class {page_class} {{
  readonly page: Page;
{locators}

  constructor(page: Page) {{
    this.page = page;
{locator_init}
  }}

{methods}
}}
''',
        },
        "selenium": {
            "language": "java",
            "deps": ["selenium-java", "testng"],
            "test_file": '''import org.testng.annotations.Test;
import static org.testng.Assert.*;

public class {class_name} {{
    @Test(description = "{test_name}")
    public void {method_name}() {{
{steps}
    }}
}}
''',
        },
        "cypress": {
            "language": "javascript",
            "deps": ["cypress"],
            "test_file": '''describe('{suite_name}', () => {{
  it('{test_name}', () => {{
{steps}
  }});
}});
''',
        },
    }

    def generate(self, input_data: dict) -> dict:
        framework = input_data.get("framework", "playwright")
        test_cases = input_data.get("test_cases", [])
        if not test_cases and isinstance(input_data, dict):
            test_cases = input_data.get("test_cases", [input_data]) if "title" not in input_data else [input_data]

        if not test_cases:
            test_cases = [{"title": "Sample Test", "steps": ["Navigate to app", "Verify homepage"], "expected_results": ["Page loads"]}]

        template = self.TEMPLATES.get(framework, self.TEMPLATES["playwright"])
        files = []

        for i, tc in enumerate(test_cases[:5]):
            title = tc.get("title", f"Test_{i + 1}")
            safe_name = "".join(c if c.isalnum() else "_" for c in title)[:30]
            steps = tc.get("steps", [])
            expected = "; ".join(tc.get("expected_results", ["Success"]))

            if framework == "playwright":
                step_lines = "\n".join(f"    await pg.performStep{i + 1}();  // {s}" for i, s in enumerate(steps))
                page_class = "AppPage"
                content = template["test_file"].format(
                    page_class=page_class,
                    suite_name=safe_name,
                    test_name=title,
                    steps=step_lines or "    await page.goto('/');",
                    expected=expected[:80],
                )
                files.append({"path": f"tests/{safe_name}.spec.ts", "content": content, "type": "test"})

                if i == 0:
                    methods = "\n".join(
                        f"  async performStep{j + 1}() {{ /* {s} */ }}"
                        for j, s in enumerate(steps)
                    )
                    po_content = template["page_object"].format(
                        page_class=page_class,
                        locators="  readonly submitBtn: Locator;",
                        locator_init="    this.submitBtn = page.locator('[data-testid=\"submit\"]');",
                        methods=methods or "  async navigate() { await this.page.goto('/'); }",
                    )
                    files.append({"path": f"pages/{page_class}.ts", "content": po_content, "type": "page_object"})

            elif framework == "selenium":
                step_lines = "\n".join(f"        // Step: {s}" for s in steps)
                content = template["test_file"].format(
                    class_name=safe_name,
                    test_name=title,
                    method_name=f"test{safe_name}",
                    steps=step_lines or "        // Implement test steps",
                )
                files.append({"path": f"src/test/java/{safe_name}.java", "content": content, "type": "test"})

            else:  # cypress
                step_lines = "\n".join(f"    // {s}" for s in steps)
                content = template["test_file"].format(
                    suite_name=safe_name,
                    test_name=title,
                    steps=step_lines or "    cy.visit('/');",
                )
                files.append({"path": f"cypress/e2e/{safe_name}.cy.js", "content": content, "type": "test"})

        return {
            "framework": framework,
            "language": template["language"],
            "files": files,
            "dependencies": template["deps"],
            "ci_pipeline_snippet": self._ci_snippet(framework),
            "_engine": "qeos-native",
        }

    def _ci_snippet(self, framework: str) -> str:
        snippets = {
            "playwright": """jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npx playwright install
      - run: npx playwright test""",
            "selenium": """jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: mvn test""",
            "cypress": """jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npx cypress run""",
        }
        return snippets.get(framework, snippets["playwright"])


class PerformanceGenerator:
    """Generates performance scripts and workload models."""

    def generate(self, input_data: dict) -> dict:
        flows = input_data.get("flows", [])
        distribution = input_data.get("distribution", {})
        tool = input_data.get("tool", "k6")

        if not flows:
            flows = [{"name": "Default Flow", "weight": 100}]

        if distribution:
            total = sum(distribution.values()) or 100
            flows = [{"name": k, "weight": round(v / total * 100)} for k, v in distribution.items()]

        k6_script = self._generate_k6(flows)
        jmeter_note = self._generate_jmeter_outline(flows)

        return {
            "tool": tool,
            "workload_model": {
                "virtual_users": 100,
                "ramp_up": "5m",
                "duration": "30m",
                "flows": flows,
            },
            "scripts": [
                {"path": "load-test.js", "content": k6_script, "type": "k6"},
                {"path": "load-test.jmx", "content": jmeter_note, "type": "jmeter"},
            ],
            "correlation_rules": [
                {"name": "session_token", "extract_from": "response.headers['Set-Cookie']", "use_in": "subsequent_requests"},
                {"name": "csrf_token", "extract_from": "response.body.csrfToken", "use_in": "POST requests"},
            ],
            "parameterization": {"users": "data/users.csv", "products": "data/products.csv"},
            "data_models": [{"name": "users", "fields": ["username", "password", "role"]}],
            "_engine": "qeos-native",
        }

    def _generate_k6(self, flows: list[dict]) -> str:
        flow_blocks = []
        for flow in flows:
            name = flow.get("name", "flow")
            weight = flow.get("weight", 100)
            flow_blocks.append(f"""
  // Flow: {name} ({weight}%)
  group('{name}', () => {{
    http.get('{self._url_for_flow(name)}');
    sleep(1);
  }});""")

        return f"""import http from 'k6/http';
import {{ sleep, group }} from 'k6';

export const options = {{
  stages: [
    {{ duration: '5m', target: 100 }},
    {{ duration: '30m', target: 100 }},
    {{ duration: '5m', target: 0 }},
  ],
  thresholds: {{
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  }},
}};

export default function () {{
{"".join(flow_blocks)}
}}
"""

    def _generate_jmeter_outline(self, flows: list[dict]) -> str:
        return f"<!-- JMeter test plan for {len(flows)} flows: {', '.join(f['name'] for f in flows)} -->"

    def _url_for_flow(self, name: str) -> str:
        slug = name.lower().replace(" ", "-")
        return f"https://example.com/api/{slug}"


class SelfHealingGenerator:
    """Analyzes failures and proposes repairs."""

    LOCATOR_ALTERNATIVES = {
        "id": ["data-testid", "name", "css", "xpath"],
        "xpath": ["css", "data-testid", "text", "role"],
        "css": ["data-testid", "xpath", "text"],
    }

    def generate(self, input_data: dict) -> dict:
        failure_type = input_data.get("type", "ui")
        failure = input_data.get("failure", {})
        error_msg = failure.get("error", failure.get("message", "Element not found"))
        locator = failure.get("locator", failure.get("selector", ""))

        repairs = []
        if failure_type == "ui" and locator:
            locator_type = "xpath" if locator.startswith("//") else "css" if "=" in locator else "id"
            for alt in self.LOCATOR_ALTERNATIVES.get(locator_type, ["data-testid"]):
                repairs.append({
                    "original": locator,
                    "healed": f"[{alt}='...']  # QEOS suggested alternative strategy",
                    "confidence": 0.75,
                    "strategy": alt,
                })

        return {
            "healing_type": failure_type,
            "diagnosis": self._diagnose(failure_type, error_msg),
            "repairs": repairs or [{"original": str(locator), "healed": "[data-testid='element']", "confidence": 0.6}],
            "impact_analysis": {
                "affected_tests": failure.get("test_name", ["Unknown test"]),
                "severity": "high" if "timeout" in error_msg.lower() else "medium",
            },
            "auto_retry_recommended": "timeout" in error_msg.lower() or "stale" in error_msg.lower(),
            "_engine": "qeos-native",
        }

    def _diagnose(self, failure_type: str, error_msg: str) -> str:
        error_lower = error_msg.lower()
        if failure_type == "ui":
            if "not found" in error_lower or "no such element" in error_lower:
                return "UI locator drift detected — element selector no longer matches DOM"
            if "timeout" in error_lower:
                return "Element interaction timeout — possible slow render or locator issue"
        if failure_type == "api":
            if "404" in error_msg:
                return "API endpoint change detected"
            if "schema" in error_lower:
                return "Response schema drift detected"
        return f"Failure analyzed: {error_msg[:100]}"


class DefectIntelligenceGenerator:
    """Clusters failures and identifies root causes."""

    def generate(self, input_data: dict) -> dict:
        failures = input_data.get("failures", [])
        if not failures:
            failures = [input_data] if input_data else []

        clusters: dict[str, list] = {}
        for f in failures:
            error = str(f.get("error", f.get("message", "unknown")))
            key = self._cluster_key(error)
            clusters.setdefault(key, []).append(f)

        cluster_output = [
            {
                "id": f"CLU-{i + 1:03d}",
                "pattern": key,
                "failures": [str(f.get("test_name", f.get("name", "unknown"))) for f in items],
                "root_cause": self._root_cause(key),
                "count": len(items),
            }
            for i, (key, items) in enumerate(clusters.items())
        ]

        return {
            "clusters": cluster_output,
            "duplicates": self._find_duplicates(failures),
            "predictions": self._predict(failures),
            "recommendations": [
                "Fix highest-count failure cluster first",
                "Add self-healing locators for UI drift patterns",
                "Review recent deployments for API schema changes",
            ],
            "_engine": "qeos-native",
        }

    def _cluster_key(self, error: str) -> str:
        error_lower = error.lower()
        if "timeout" in error_lower:
            return "Timeout failures"
        if "not found" in error_lower or "404" in error:
            return "Element/Endpoint not found"
        if "assert" in error_lower:
            return "Assertion failures"
        if "connection" in error_lower:
            return "Connection/Network failures"
        return "Other failures"

    def _root_cause(self, pattern: str) -> str:
        causes = {
            "Timeout failures": "Slow environment, missing waits, or performance degradation",
            "Element/Endpoint not found": "Locator drift or API endpoint change after deployment",
            "Assertion failures": "Application behavior change or test data mismatch",
            "Connection/Network failures": "Environment instability or service outage",
        }
        return causes.get(pattern, "Requires manual investigation")

    def _find_duplicates(self, failures: list) -> list:
        seen: dict[str, str] = {}
        dups = []
        for f in failures:
            key = str(f.get("error", ""))[:50]
            name = str(f.get("test_name", f.get("name", "")))
            if key in seen:
                dups.append({"primary": seen[key], "duplicates": [name]})
            else:
                seen[key] = name
        return dups

    def _predict(self, failures: list) -> list:
        if len(failures) >= 3:
            return [{"area": "Regression risk", "risk": "high", "reason": f"{len(failures)} failures in current run"}]
        return [{"area": "Stability", "risk": "low", "reason": "Failure count within normal range"}]
