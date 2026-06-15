# Phase 5 — Autonomous Quality System

## Status: Complete

## Capabilities

| Feature | Description |
|---------|-------------|
| **Browser Discovery** | Playwright crawl or HTTP fallback — maps real pages, forms, links |
| **Static Discovery** | Requirements keyword inference for flows/APIs |
| **Discovery → Tests** | Auto-generate requirements, test cases, and optional automation from sessions |
| **Live Playwright Execution** | Materializes assets to temp workspace, runs `npx playwright test` |
| **Dry-run Execution** | Static analysis + self-healing patches applied to assets |
| **Live Reports** | Platform + per-project quality score, ROI, monitoring events from DB |
| **Persistent Integrations** | Survive server restart; Jira sync API |
| **Environment Profiles** | DEV/STAGING/PROD per project |
| **Audit Logging** | Governance trail for environments and mutations |
| **Global Search** | Search projects, tests, assets, discovery sessions |
| **RBAC** | JWT auth, project-scoped access, OIDC SSO scaffold |

## Discovery Modes

| Mode | Behavior |
|------|----------|
| `static` | Requirements → inferred flows |
| `browser` | Live crawl via Playwright (HTTP fallback) |
| `both` | Merge static + crawled results |

Optional `username` / `password` for login during browser crawl.

## Execution Modes

| Mode | Behavior |
|------|----------|
| `dry_run` | Parse files, validate, self-heal suggestions |
| `live` | Run Playwright tests via Node.js (requires Node + npm) |

Falls back to dry-run if Node/Playwright unavailable.

## Setup (Live Runners)

```powershell
# Python Playwright (browser discovery)
cd backend
.\.venv\Scripts\pip install playwright
.\.venv\Scripts\python -m playwright install chromium

# Node.js (live test execution) — install from https://nodejs.org
node --version
npx --version
```

## API Endpoints

| Method | Endpoint |
|--------|----------|
| POST | `/projects/{id}/discovery/run` `{ mode, base_url, username?, password? }` |
| POST | `/projects/{id}/executions/run` `{ asset_id, mode: "live"|"dry_run" }` |
| GET | `/platform/capabilities` |
| POST | `/monitoring/events` |
| GET | `/auth/status` |
| POST | `/auth/login` (when `QEOS_AUTH_ENABLED=true`) |

## Config (.env)

```
PLAYWRIGHT_ENABLED=true
PLAYWRIGHT_HEADLESS=true
DISCOVERY_MAX_PAGES=10
EXECUTION_TIMEOUT_SEC=120
QEOS_AUTH_ENABLED=false
QEOS_DEFAULT_ADMIN_EMAIL=admin@qeos.local
QEOS_DEFAULT_ADMIN_PASSWORD=admin
```

## RBAC Roles

- `platform_admin` — full access
- `project_admin` — project management
- `tester` — run tests, view reports
- `automation_engineer` — studio, executions
- `business_user` — read-only reports

Set `QEOS_AUTH_ENABLED=true` to enforce JWT on all routes (except login, webhooks, health).

## Auth & SSO Endpoints

- `POST /auth/login` — email/password
- `GET /auth/me` — current user
- `GET /auth/sso/login` — OIDC redirect
- `POST /monitoring/webhooks/datadog` — Datadog alerts
- `POST /monitoring/webhooks/sentry` — Sentry issues

## Monitoring

Configure Datadog/Sentry webhooks pointing to your QEOS API. See **Platform → Monitoring** in the UI.

## Still Planned

- SAML 2.0
- Project-level RBAC enforcement on all routes
- Datadog API pull (metrics/logs query)
- Kubernetes load agents
