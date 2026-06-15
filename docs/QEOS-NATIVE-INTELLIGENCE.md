# QEOS Native Intelligence Engine — Architecture

## Overview

QEOS ships with its **own proprietary intelligence engine (QNIE)** — you do not need OpenAI, Anthropic, or any external LLM to run the platform.

```
┌─────────────────────────────────────────────────────────┐
│              QEOS Native Intelligence Engine             │
├─────────────────────────────────────────────────────────┤
│  Requirement Parser    │  User stories, BDD, BRD, AC     │
│  Knowledge Base        │  12+ QA testing patterns        │
│  Pattern Matcher       │  Keyword → test pattern mapping │
│  Generators            │  Per-agent output generation    │
├─────────────────────────────────────────────────────────┤
│  Phase 2 (optional): Local neural model via Ollama      │
│  Phase 3 (optional): Fine-tuned QEOS domain model       │
└─────────────────────────────────────────────────────────┘
```

## How It Works (Phase 1 — Current)

1. **Parse** — Extract structured requirements from raw text
2. **Match** — Map requirements to domain testing patterns (auth, CRUD, payment, API, security...)
3. **Generate** — Produce test scenarios, cases, coverage matrix, risk analysis
4. **Extend** — Chain to test design, automation templates, performance scripts

### Supported Input Formats

- User stories: `As a <role>, I want <action>, so that <benefit>`
- BDD: `Given / When / Then` scenarios
- Numbered requirements: `REQ-001`, `US-001`, `FR-001`
- Bullet acceptance criteria
- Free-form paragraphs

### Example

**Input:**
```
As a customer, I want to login with valid credentials, so that I can access my account.

Acceptance Criteria:
- Valid email and password grants access
- Invalid password shows error message
```

**Output:** Test scenarios, positive/negative test cases, risk analysis, coverage matrix — all generated locally.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/intelligence/status` | Engine status and capabilities |
| `POST /api/v1/intelligence/generate/requirements` | Direct requirement → test generation |
| `POST /api/v1/agents/run` | Run any agent (uses QEOS Native by default) |

## Provider Configuration

```env
DEFAULT_LLM_PROVIDER=qeos-native
DEFAULT_LLM_MODEL=qeos-intelligence-v1
```

No API keys required.

## Roadmap: Building a Custom Neural Model

While Phase 1 uses a rule + knowledge engine (fast, deterministic, private), you can evolve to a custom neural model:

### Phase 2 — Hybrid Mode (Native + Local Neural)

Install [Ollama](https://ollama.ai) and pull a model:

```bash
ollama pull llama3.2
```

Set provider to hybrid — native engine runs first, Ollama adds edge cases:

```env
DEFAULT_LLM_PROVIDER=qeos-hybrid
QEOS_HYBRID_AUTO=true
OLLAMA_MODEL=llama3.2
```

Or call directly: `POST /api/v1/intelligence/generate/hybrid`

Hybrid mode always works offline (native-only fallback when Ollama is unavailable).

### Phase 3 — Training Data Collection (Automatic)

Every successful agent run is auto-saved as a fine-tuning pair:

- View stats: `GET /api/v1/intelligence/training/stats`
- Export: `POST /api/v1/intelligence/training/export`
- Download: `GET /api/v1/intelligence/training/download`
- UI: QA Studio → Training Data page

### Phase 4 — Fine-Tune Your Own QEOS Model

Use the training scaffold in `backend/training/`:

1. Collect your test cases, requirements, and automation scripts as training pairs
2. Fine-tune a small open-source base model (Llama, Mistral, Qwen)
3. Deploy via Ollama or vLLM
4. Set `QEOS_MODEL_PATH` and `QEOS_ENABLE_NEURAL=true`

This gives you a **domain-specific QEOS model** trained on your organization's quality patterns.

### Why Not Train From Scratch?

Training a general LLM from scratch requires millions of dollars in compute. The practical path is:

1. **Now:** QEOS Native engine (proprietary, instant)
2. **Later:** Fine-tune open-source base on QA domain data
3. **Enterprise:** Hybrid — native engine + neural enhancement for complex cases

## Architecture Decision

| Approach | Pros | Cons |
|----------|------|------|
| **QEOS Native (current)** | Zero cost, private, deterministic, always works | Less creative on novel requirements |
| **Local Ollama** | Better language understanding, still private | Needs GPU/RAM |
| **Fine-tuned QEOS model** | Best domain accuracy | Requires training data + compute |
| **External APIs** | Highest quality | Cost, privacy, dependency |

QEOS defaults to **QEOS Native** and upgrades gracefully as you add neural capabilities.
