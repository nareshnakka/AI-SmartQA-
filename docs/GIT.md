# Git — Clone, Setup, and Stop

Repository: [https://github.com/nareshnakka/AI-SmartQA-](https://github.com/nareshnakka/AI-SmartQA-)

This guide is for anyone cloning the project on a new machine to review or run QEOS locally.

---

## 1. Clone the repository

### HTTPS (easiest)

```bash
git clone https://github.com/nareshnakka/AI-SmartQA-.git
cd AI-SmartQA-
```

### SSH (if you use SSH keys with GitHub)

```bash
git clone git@github.com:nareshnakka/AI-SmartQA-.git
cd AI-SmartQA-
```

### GitHub Desktop

1. Open **GitHub Desktop** → **File** → **Clone repository**
2. URL: `https://github.com/nareshnakka/AI-SmartQA-`
3. Choose a local folder and click **Clone**

---

## 2. One-click setup and run (Windows)

From the project root, double-click or run:

```bat
setup-and-run.bat
```

This script will:

- Install **Python 3.11+** and **Node.js LTS** via `winget` if they are missing
- Create `backend\.venv` and install Python packages
- Install **all automation & performance runners** (see table below)
- Run `npm ci` in `frontend`
- Start backend (`http://127.0.0.1:8000`) and frontend (`http://localhost:3000`)
- Open the app in your default browser

**First run can take 20–40 minutes** depending on network speed (browser binaries and Node runner cache are large).

### What gets installed

| Category | Tool | Installed by setup |
|----------|------|-------------------|
| **Functional** | Playwright (Python + Node) | Yes — required |
| | Cypress, Puppeteer, TestCafe, WebdriverIO | Yes — `runners-tools/` npm cache |
| | Robot Framework + Browser library | Yes — pip + `rfbrowser init` |
| | Selenium (Java/Maven) | Yes — via winget when available |
| | Appium (Python client) | Yes — pip; Appium server is separate |
| **Performance** | k6 (live runs) | Yes — via winget when available |
| | Locust | Yes — pip |
| | JMeter | Best-effort — winget |
| | Gatling | Scripts generated for export; needs Gatling CLI to run |

Re-run only runner setup anytime:

```bat
scripts\install-all-runners.bat
```

Check status:

```bat
cd backend
.venv\Scripts\python.exe scripts\verify_all_runners.py
```

Or open `http://127.0.0.1:8000/api/v1/platform/capabilities` after the backend is running.

If Python or Node was just installed, close the terminal, open a new one, and run `setup-and-run.bat` again so PATH is refreshed.

---

## 3. Manual setup (Windows, macOS, Linux)

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 20+ (LTS) |
| npm | Comes with Node |

Optional: Docker & Docker Compose (only if using PostgreSQL/Redis from `docker-compose.yml`).

### Steps

```bash
# 1. Environment
cp .env.example .env
cp .env backend/.env    # backend reads .env from its working directory

# 2. Backend
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-runners.txt
python scripts/install_all_runners.py --skip-winget

# Or on Windows after venv + requirements.txt:
# scripts\install-all-runners.bat

# 3. Frontend
cd ../frontend
npm ci

# 4. Start servers (two terminals)
# Terminal A — backend:
cd backend
.venv\Scripts\activate          # or: source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal B — frontend:
cd frontend
npm run dev
```

Open **http://localhost:3000** in your browser.

API docs: **http://127.0.0.1:8000/docs**

---

## 4. Verify the backend is up to date

Studio **Debug** runs real Playwright tests only when the API reports the live executor:

```bash
curl http://127.0.0.1:8000/health
```

Look for `"execution_executor": "asset_live_v2"`. If that field is missing, restart the backend:

```bat
scripts\stop-servers.bat
scripts\restart-all.bat
```

---

## 5. Stop / close the app (shut down servers)

When you are done reviewing or testing:

### Windows

```bat
scripts\stop-servers.bat
```

Or close the two terminal windows titled **QEOS Backend** and **QEOS Frontend**.

### Manual

Stop the processes listening on ports **8000** (API) and **3000** (UI), or press **Ctrl+C** in each server terminal.

---

## 6. Pull latest changes

If the repo is updated on GitHub:

```bash
git pull origin main
```

Then reinstall only if dependencies changed:

```bash
cd backend && .venv\Scripts\pip install -r requirements.txt
cd ../frontend && npm ci
```

---

## 7. Push changes (contributors)

```bash
git add .
git commit -m "Describe your change"
git push origin main
```

Use a [Personal Access Token](https://github.com/settings/tokens) or `gh auth login` for HTTPS push. Do **not** commit `.env`, `*.db`, `.venv`, or `node_modules` — they are listed in `.gitignore`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `TypeError: Failed to fetch` in Studio / Executions | Backend not running. Run `scripts\restart-backend.bat` and keep that window open. Verify `http://127.0.0.1:8000/health` in a browser. |
| Debug finishes in ~2s, no real browser | Stale backend — restart with `scripts\restart-all.bat` |
| `npm` or `python` not found after winget install | Open a **new** terminal and run setup again |
| Runners missing (Discovery, debug, k6, Cypress, …) | `scripts\install-all-runners.bat` then `scripts\restart-backend.bat` |
| Discovery HTTP crawl only | Same as above; verify `playwright_browsers: true` on `/health` |
| Performance simulates instead of live k6 | `winget install GrafanaLabs.k6`, new terminal, `scripts\install-all-runners.bat` |

For architecture and features, see [README.md](../README.md) and [docs/](.).
