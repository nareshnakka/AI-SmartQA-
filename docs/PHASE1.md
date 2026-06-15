# Phase 1 — AI Test Generation (Complete)

## What's Included

### Requirement Ingestion
- Text input (user stories, BDD, BRD, free-form)
- File upload (`.txt`, `.md`, `.csv`, `.json`)
- Requirement CRUD per project

### AI Test Generation (QEOS Native Intelligence)
- Test scenario generation
- Test case generation with steps and expected results
- Priority assignment and tagging
- Risk analysis
- Coverage matrix with gap identification

### Test Design
- Automatic regression pack creation
- Smoke pack creation
- Multi-domain test design output

### Persistence
- SQLite by default (`backend/qeos.db`) — zero config
- PostgreSQL supported via `DATABASE_URL` env var
- Models: Project, Requirement, TestCase, TestScenario, TestSuite, AgentRun, CoverageSnapshot

### Export
- JSON export: `/api/v1/projects/{id}/export/json`
- CSV export: `/api/v1/projects/{id}/export/csv`

### UI Workflow
1. Dashboard → view Phase 1 status
2. Projects → create project
3. Project detail → paste requirements → Generate
4. Review test cases (expandable steps/expected results)
5. View coverage gaps and risk
6. Export CSV/JSON

## API Endpoints (Phase 1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/phase1/status` | Phase 1 completion status |
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects/{id}` | Project detail + counts |
| POST | `/api/v1/projects/{id}/generate` | **Core** — generate & persist tests |
| POST | `/api/v1/projects/{id}/requirements/upload` | Upload requirement file |
| GET | `/api/v1/projects/{id}/test-cases` | List test cases |
| GET | `/api/v1/projects/{id}/coverage` | Coverage matrix |
| GET | `/api/v1/projects/{id}/export/csv` | Export CSV |
| GET | `/api/v1/projects/{id}/runs` | Agent run history |

## Start

```powershell
cd backend
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000

cd frontend
npm run dev
```

Open http://localhost:3000 → Create Project → Generate Test Cases
