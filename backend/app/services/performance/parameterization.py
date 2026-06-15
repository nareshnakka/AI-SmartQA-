"""Data pool generation and script parameterization."""

import csv
import io
import json
from typing import Any


DEFAULT_POOLS = {
    "users": {
        "filename": "data/users.csv",
        "columns": ["username", "password", "role"],
        "rows": [
            ["user1@test.com", "Pass123!", "customer"],
            ["user2@test.com", "Pass123!", "customer"],
            ["admin@test.com", "Admin123!", "admin"],
        ],
    },
    "products": {
        "filename": "data/products.csv",
        "columns": ["sku", "name", "price"],
        "rows": [
            ["SKU-001", "Widget A", "19.99"],
            ["SKU-002", "Widget B", "29.99"],
            ["SKU-003", "Widget C", "39.99"],
        ],
    },
}


def generate_data_pools(custom: dict | None = None) -> list[dict]:
    """Build data pool definitions with CSV content."""
    pools = []
    source = {**DEFAULT_POOLS, **(custom or {})}
    for key, pool in source.items():
        content = _to_csv(pool.get("columns", []), pool.get("rows", []))
        pools.append({
            "id": key,
            "name": key.replace("_", " ").title(),
            "filename": pool.get("filename", f"data/{key}.csv"),
            "columns": pool.get("columns", []),
            "row_count": len(pool.get("rows", [])),
            "content": content,
            "format": "csv",
        })
    return pools


def _to_csv(columns: list[str], rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    if columns:
        writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def inject_parameterization_k6(script: str, pools: list[dict]) -> str:
    """Add SharedArray data loading to k6 script."""
    if not pools:
        return script

    imports = []
    loaders = []
    for pool in pools:
        var = pool["id"].replace("-", "_")
        cols = pool.get("columns", [])
        rows = []
        reader = csv.reader(io.StringIO(pool.get("content", "")))
        header = next(reader, cols)
        for row in reader:
            if len(row) >= len(header):
                rows.append(dict(zip(header, row)))

        if not rows:
            continue

        imports.append(f"const {var}Data = new SharedArray('{var}', function () {{")
        imports.append(f"  return {json.dumps(rows)};")
        imports.append("});")
        imports.append("")

    if not imports:
        return script

    block = "\n".join(imports)
    if "SharedArray" not in script:
        if "import { sleep" in script:
            script = script.replace(
                "import { sleep",
                "import { SharedArray } from 'k6/data';\nimport { sleep",
            )
        elif "import http" in script:
            script = script.replace("import http", "import { SharedArray } from 'k6/data';\nimport http")

    if "export default function" in script:
        idx = script.index("export default function")
        script = script[:idx] + block + "\n" + script[idx:]
        # Use first pool in default function
        first_var = pools[0]["id"].replace("-", "_")
        script = script.replace(
            "export default function () {",
            f"export default function () {{\n  const user = {first_var}Data[__VU % {first_var}Data.length];",
            1,
        )

    return script


def build_parameterization_map(pools: list[dict]) -> dict:
    return {
        "pools": [{"id": p["id"], "filename": p["filename"], "columns": p.get("columns", []), "row_count": p.get("row_count", 0)} for p in pools],
        "strategy": "round_robin",
        "binding": "vu_index_modulo",
    }
