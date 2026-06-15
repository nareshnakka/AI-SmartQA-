"""Enhanced performance script generation from browser replay with correlation + parameterization."""

import json

from app.services.performance.correlation import inject_correlations_into_k6
from app.services.performance.parameterization import (
    build_parameterization_map,
    generate_data_pools,
    inject_parameterization_k6,
)
from app.services.performance.workload import WORKLOAD_PROFILES, apply_throughput_to_k6_options, build_workload_model


class PerformanceEngine:
    """Full performance engineering generator — scripts driven by browser replay flows."""

    def generate(
        self,
        tool: str,
        flows: list[dict],
        profile: str = "load",
        correlation_rules: list[dict] | None = None,
        data_pools: list[dict] | None = None,
        throughput_config: dict | None = None,
        base_url: str = "https://example.com",
    ) -> dict:
        workload = build_workload_model(profile, throughput_config)
        pools = data_pools or generate_data_pools()
        rules = correlation_rules or []

        scenarios = []
        for i, f in enumerate(flows):
            http_steps = f.get("steps") or self._default_steps(f, base_url)
            scenarios.append({
                "id": f"scenario-{i}",
                "name": f.get("name", f"Flow {i + 1}"),
                "weight": f.get("weight", 100 // max(len(flows), 1)),
                "source": f.get("source", "generated"),
                "steps": [
                    {
                        "action": s.get("action", "GET"),
                        "url": s.get("url", base_url),
                        "name": s.get("name", f"Step {j + 1}"),
                        "think": s.get("think"),
                    }
                    for j, s in enumerate(http_steps)
                ],
            })

        if tool == "k6":
            script = self._k6_script(flows, workload, throughput_config, base_url)
            script = inject_correlations_into_k6(script, rules)
            script = inject_parameterization_k6(script, pools)
            scripts = [{"path": "load-test.js", "content": script, "type": "k6"}]
        elif tool == "jmeter":
            scripts = [{"path": "load-test.jmx", "content": self._jmeter_xml(flows, workload, base_url), "type": "jmeter"}]
        elif tool == "gatling":
            scripts = [{"path": "LoadSimulation.scala", "content": self._gatling_scala(flows, base_url), "type": "gatling"}]
        elif tool == "locust":
            scripts = [{"path": "locustfile.py", "content": self._locust_py(flows, base_url), "type": "locust"}]
        else:
            scripts = [{"path": "load-test.js", "content": self._k6_script(flows, workload, throughput_config, base_url), "type": "k6"}]

        for pool in pools:
            scripts.append({"path": pool["filename"], "content": pool.get("content", ""), "type": "data"})

        return {
            "tool": tool,
            "workload_model": workload,
            "throughput_config": throughput_config or {
                "target_rps": workload.get("target_rps"),
                "p95_ms": 500,
                "error_rate": 0.01,
            },
            "workload_profile": profile,
            "scenarios": scenarios,
            "scripts": scripts,
            "correlation_rules": rules,
            "parameterization": build_parameterization_map(pools),
            "data_pools": pools,
            "flow_distribution": {f["name"]: f.get("weight", 0) for f in flows},
            "replay_source": flows[0].get("source") if flows else None,
            "_engine": "qeos-performance-replay-v3",
        }

    def _default_steps(self, flow: dict, base_url: str) -> list[dict]:
        name = flow.get("name", "flow")
        return [
            {"action": "GET", "url": base_url, "name": f"Open {name}"},
            {"action": "GET", "url": f"{base_url.rstrip('/')}/", "name": f"Verify {name}", "think": "1s"},
        ]

    def _flow_http_steps(self, flow: dict, base_url: str) -> list[dict]:
        steps = flow.get("steps")
        if steps and isinstance(steps[0], dict) and steps[0].get("url"):
            return steps
        return self._default_steps(flow, base_url)

    def _escape_js(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")

    def _k6_http_call(self, step: dict) -> str:
        method = step.get("action", "GET").upper()
        url = self._escape_js(step.get("url", "/"))
        name = self._escape_js(step.get("name", "request"))
        tag = f"{{ tags: {{ name: '{name}', transaction: '{name}' }} }}"
        if method == "POST":
            return f"    res = http.post('{url}', null, {tag});"
        if method == "PUT":
            return f"    res = http.put('{url}', null, {tag});"
        if method == "DELETE":
            return f"    res = http.del('{url}', null, {tag});"
        return f"    res = http.get('{url}', {tag});"

    def _k6_script(self, flows: list, workload: dict, throughput: dict | None, base_url: str) -> str:
        opts = apply_throughput_to_k6_options(workload, throughput)
        stages_str = ",\n    ".join(
            f"{{ duration: '{s['duration']}', target: {s['target']} }}" for s in opts.get("stages", [])
        )
        thresholds = opts.get("thresholds", {})
        thresh_lines = ",\n    ".join(f"'{k}': {json.dumps(v)}" for k, v in thresholds.items())

        flow_blocks = []
        for flow in flows:
            name = self._escape_js(flow.get("name", "flow"))
            steps = self._flow_http_steps(flow, base_url)
            step_lines = []
            for step in steps:
                txn = self._escape_js(step.get("name", "step"))
                step_lines.append(self._k6_http_call(step))
                step_lines.append(f"    check(res, {{ '{txn} status OK': (r) => r.status >= 200 && r.status < 400 }});")
                think = step.get("think") or "1"
                if isinstance(think, str) and think.endswith("s"):
                    think = think[:-1]
                step_lines.append(f"    sleep({think});")

            flow_blocks.append(f"""
  group('{name}', () => {{
{chr(10).join(step_lines)}
  }});""")

        return f"""// QEOS Performance Script — generated from browser replay / test case flows
import http from 'k6/http';
import {{ sleep, group, check }} from 'k6';

export const options = {{
  stages: [
    {stages_str}
  ],
  thresholds: {{
    {thresh_lines}
  }},
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
}};

export default function () {{
{"".join(flow_blocks)}
}}
"""

    def _jmeter_xml(self, flows: list, workload: dict, base_url: str) -> str:
        samplers = []
        for flow in flows:
            for step in self._flow_http_steps(flow, base_url):
                samplers.append(f"""
      <HTTPSamplerProxy guiclass="HttpTestSampleGui" testname="{self._escape_js(step.get('name', 'request'))}">
        <stringProp name="HTTPSampler.domain">{base_url.replace('https://', '').replace('http://', '').split('/')[0]}</stringProp>
        <stringProp name="HTTPSampler.path">{step.get('url', '/').split('/', 3)[-1] if '://' in step.get('url', '') else step.get('url', '/')}</stringProp>
        <stringProp name="HTTPSampler.method">{step.get('action', 'GET')}</stringProp>
      </HTTPSamplerProxy>""")
        flow_names = ", ".join(f.get("name", "flow") for f in flows)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testname="QEOS Replay Load Test">
      <stringProp name="TestPlan.comments">Browser replay flows: {flow_names}</stringProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testname="Load Users">
        <stringProp name="ThreadGroup.num_threads">{workload.get('virtual_users', 100)}</stringProp>
        <stringProp name="ThreadGroup.ramp_time">{str(workload.get('ramp_up', '5m')).replace('m', '')}</stringProp>
      </ThreadGroup>
      <hashTree>{"".join(samplers)}
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>"""

    def _gatling_scala(self, flows: list, base_url: str) -> str:
        scn_defs = []
        setup_parts = []
        for f in flows:
            slug = self._slug(f.get("name", "flow"))
            execs = []
            for step in self._flow_http_steps(f, base_url):
                path = step.get("url", "/").split("://")[-1]
                if "/" in path:
                    path = "/" + path.split("/", 1)[-1]
                execs.append(f'http("{self._escape_js(step.get("name", "req"))}").{step.get("action", "get").lower()}("{path}")')
            exec_chain = ".exec(".join(execs) + ")" * len(execs) if execs else 'http("home").get("/")'
            scn_defs.append(f'  val {slug} = scenario("{f.get("name", "flow")}").exec({exec_chain})')
            setup_parts.append(f"{slug}.inject(rampUsers({f.get('weight', 10)}) during (5 minutes))")
        scns = "\n".join(scn_defs)
        setup = ",\n    ".join(setup_parts) if setup_parts else 'scenario("default").inject(atOnceUsers(1))'
        return f"""import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class QeosLoadSimulation extends Simulation {{
  val httpProtocol = http.baseUrl("{base_url}")
{scns}
  setUp({setup}).protocols(httpProtocol)
}}"""

    def _locust_py(self, flows: list, base_url: str) -> str:
        tasks = []
        for f in flows:
            slug = self._slug(f.get("name", "flow"))
            lines = []
            for step in self._flow_http_steps(f, base_url):
                url = step.get("url", base_url)
                path = url.replace(base_url, "") or "/"
                meth = step.get("action", "GET").lower()
                if meth == "post":
                    lines.append(f'        self.client.post("{path}", name="{step.get("name", "post")}")')
                else:
                    lines.append(f'        self.client.get("{path}", name="{step.get("name", "get")}")')
            body = "\n".join(lines) if lines else f'        self.client.get("/")'
            tasks.append(f'    @task({f.get("weight", 10)})\n    def {slug}(self):\n{body}')
        return f"""from locust import HttpUser, task, between

class QeosUser(HttpUser):
    wait_time = between(1, 3)
    host = "{base_url}"

{chr(10).join(tasks)}
"""

    def _slug(self, name: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in name.lower())[:30]

    def _duration_seconds(self, duration: str) -> int:
        if duration.endswith("h"):
            return int(duration[:-1]) * 3600
        if duration.endswith("m"):
            return int(duration[:-1]) * 60
        return int(duration) if duration.isdigit() else 1800
