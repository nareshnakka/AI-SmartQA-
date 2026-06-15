"""Extract correlation rules from HAR and OpenAPI specs."""

import json
import re
from typing import Any


def extract_from_har(har_data: dict | str) -> list[dict]:
    """Parse HAR file and infer correlation candidates from Set-Cookie, tokens, IDs."""
    if isinstance(har_data, str):
        har_data = json.loads(har_data)

    entries = har_data.get("log", {}).get("entries", [])
    rules: list[dict] = []
    seen: set[str] = set()

    for entry in entries:
        req = entry.get("request", {})
        resp = entry.get("response", {})
        url = req.get("url", "")
        method = req.get("method", "GET")

        for header in resp.get("headers", []):
            name = header.get("name", "").lower()
            if name == "set-cookie" and "session" in header.get("value", "").lower():
                key = f"cookie_{method}_{_slug(url)}"
                if key not in seen:
                    seen.add(key)
                    rules.append({
                        "name": key,
                        "extract_from": "response.headers['Set-Cookie']",
                        "extractor": "regex",
                        "pattern": r"([^=]+)=([^;]+)",
                        "use_in": "subsequent_requests",
                        "source_url": url,
                        "method": method,
                    })

        content = resp.get("content", {}).get("text", "") or ""
        for pattern, var_name in [
            (r'"token"\s*:\s*"([^"]+)"', "auth_token"),
            (r'"csrfToken"\s*:\s*"([^"]+)"', "csrf_token"),
            (r'"sessionId"\s*:\s*"([^"]+)"', "session_id"),
            (r'"id"\s*:\s*"([a-f0-9-]{36})"', "resource_id"),
        ]:
            if re.search(pattern, content):
                key = f"{var_name}_{method}_{_slug(url)}"
                if key not in seen:
                    seen.add(key)
                    rules.append({
                        "name": key,
                        "extract_from": f"response.body (JSON path: {var_name})",
                        "extractor": "jsonpath",
                        "pattern": pattern,
                        "use_in": "subsequent_requests",
                        "source_url": url,
                        "method": method,
                    })

    return rules


def extract_from_openapi(spec: dict | str) -> list[dict]:
    """Infer correlation from OpenAPI security schemes and response schemas."""
    if isinstance(spec, str):
        spec = json.loads(spec)

    rules: list[dict] = []
    components = spec.get("components", {})
    security = spec.get("security", []) or components.get("securitySchemes", {})

    for name, scheme in (components.get("securitySchemes") or {}).items():
        if scheme.get("type") == "apiKey":
            rules.append({
                "name": name,
                "extract_from": scheme.get("in", "header") + ":" + scheme.get("name", name),
                "extractor": "header",
                "use_in": "all_authenticated_requests",
            })
        elif scheme.get("type") == "oauth2":
            rules.append({
                "name": f"{name}_token",
                "extract_from": "oauth2/token response access_token",
                "extractor": "jsonpath",
                "pattern": r'"access_token"\s*:\s*"([^"]+)"',
                "use_in": "Authorization header",
            })

    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, op in methods.items():
            if method.startswith("x-"):
                continue
            for code, response in (op.get("responses") or {}).items():
                if not str(code).startswith("2"):
                    continue
                content = (response.get("content") or {}).get("application/json", {})
                schema = content.get("schema", {})
                props = schema.get("properties", schema.get("items", {}).get("properties", {}))
                for prop in ("token", "sessionId", "csrfToken", "id"):
                    if prop in props:
                        rules.append({
                            "name": f"{prop}_{method}_{_slug(path)}",
                            "extract_from": f"response.body.{prop}",
                            "extractor": "jsonpath",
                            "pattern": f'"{prop}"',
                            "use_in": "subsequent_requests",
                            "source_path": path,
                            "method": method.upper(),
                        })

    return rules


def inject_correlations_into_k6(script: str, rules: list[dict]) -> str:
    """Inject k6 correlation helpers at top of script."""
    if not rules:
        return script

    helpers = [
        "import { SharedArray } from 'k6/data';",
        "",
        "// QEOS auto-correlation variables",
    ]
    for rule in rules:
        name = rule.get("name", "var").replace("-", "_")
        helpers.append(f"let {name} = null; // extract from: {rule.get('extract_from', '')}")

    helpers.append("")
    helpers.append("function applyCorrelations(res) {")
    for rule in rules:
        name = rule.get("name", "var").replace("-", "_")
        if rule.get("extractor") == "regex" and rule.get("pattern"):
            helpers.append(f"  const m_{name} = res.body.match(/{rule['pattern']}/);")
            helpers.append(f"  if (m_{name}) {name} = m_{name}[1] || m_{name}[0];")
        elif "csrf" in name.lower() or "token" in name.lower():
            helpers.append(f"  try {{ const j = res.json(); if (j.token) {name} = j.token; if (j.csrfToken) {name} = j.csrfToken; }} catch(e) {{}}")
    helpers.append("}")
    helpers.append("")

    block = "\n".join(helpers)
    if "import http from 'k6/http'" in script:
        script = script.replace("import http from 'k6/http';", "import http from 'k6/http';\n" + block, 1)
    else:
        script = block + script

    if "export default function" in script and "applyCorrelations" not in script:
        script = script.replace(
            "export default function () {",
            "export default function () {\n  // Correlation applied per response via applyCorrelations(res)",
        )

    return script


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", text)[:40]
