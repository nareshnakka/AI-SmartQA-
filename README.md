# QEOS — Quality Engineering Operating System

An AI-native enterprise platform that transforms business requirements into executable quality assets across the full SDLC.

## Vision

**Requirement → Test Case → Automation → Performance → Security → Execution → Defect Analysis → Executive Reporting**

QEOS acts as an intelligent quality engineering operating system powered by coordinated AI agents, open-source testing frameworks, and enterprise integrations.

## Core Capabilities

| Domain | Frameworks & Tools |
|--------|-------------------|
| **Functional** | Selenium, Playwright, Cypress, WebdriverIO, Robot Framework, Appium, TestCafe, Puppeteer |
| **API** | Postman, REST Assured, Karate, SuperTest, Bruno, Insomnia |
| **Performance** | JMeter, k6, Gatling, Locust, Taurus |
| **Security** | OWASP ZAP, Burp Suite, Nuclei, SonarQube, Snyk |

## Extensibility

Add integrations, agents, and UI features at any time without modifying core code.

See [docs/EXTENSIBILITY.md](docs/EXTENSIBILITY.md) for step-by-step guides.

## AI Model Layer

QEOS ships with its **own proprietary intelligence engine** — no external LLM required.

| Mode | Provider | Description |
|------|----------|-------------|
| **Default** | `qeos-native` | Proprietary QA intelligence — works offline, zero cost |
| Optional | `ollama` | Local open-source models on your hardware |
| Optional | OpenAI, Anthropic, Gemini | External APIs when configured |

See [docs/EXTENSIBILITY.md](docs/EXTENSIBILITY.md) for adding integrations, agents, and features.

## AI Agent Architecture

- **Requirements Agent** — BRD/FRD/user stories → test scenarios, coverage matrix
- **Test Design Agent** — functional, API, performance, security test design
- **Automation Agent** — framework-specific script generation
- **Performance Engineering Agent** — workload models, load scripts
- **Self-Healing Agent** — locator repair, impact analysis
- **Defect Intelligence Agent** — RCA, failure clustering, prediction

## Integrations

### Source Control & DevOps
- GitHub, Bitbucket, GitLab, Azure DevOps, Gitea, Forgejo

### CI/CD
- Jenkins, GitHub Actions, GitLab CI, Azure Pipelines, CircleCI, Bamboo

### Enterprise Systems
- Jira, Confluence, ServiceNow, SharePoint

## Roadmap

| Phase | Focus |
|-------|-------|
| **Phase 1** | AI Test Generation |
| **Phase 2** | AI Automation Generation |
| **Phase 3** | AI Performance Engineering |
| **Phase 4** | Multi-Agent Autonomous Quality System |
| **Phase 5** | Fully Autonomous Quality Engineering Platform |

## Quick Start

**New to the project?** See **[docs/GIT.md](docs/GIT.md)** for how to **clone**, install, run, and **stop** the app on a fresh machine.

**Windows one-click:** run `update-and-install.bat` from the repo root after cloning, then `restart.bat` to start.

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 20+
- PostgreSQL 16+ (or use Docker)

### Development

```bash
# Copy environment template
cp .env.example .env

# Start infrastructure
docker compose up -d postgres redis

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (QA Studio)
cd frontend
npm install
npm run dev
```

- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **QA Studio**: http://localhost:3000

## Project Structure

```
├── backend/                 # FastAPI + Python agents
│   └── app/
│       ├── agents/          # Multi-agent orchestration
│       ├── llm/             # LLM-agnostic provider layer
│       ├── integrations/    # GitHub, Bitbucket, Jira, CI/CD
│       ├── api/             # REST endpoints
│       └── models/          # Domain models & schemas
├── frontend/                # Next.js QA Studio
├── docs/                    # Architecture & design docs
└── docker-compose.yml
```

## License

Proprietary — Enterprise AI Quality Engineering Platform
