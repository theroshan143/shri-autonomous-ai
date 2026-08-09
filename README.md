# Shri Autonomous AI

An autonomous AI publishing agent that discovers AI/tech topics from live sources, applies editorial judgment, writes short posts in a consistent persona voice, and publishes them over time — all with **zero human input after initialization**.

Built for **ABTalks Vibe Code Hackathon — Problem Statement 3: Autonomous AI Creator**.

---

## Architecture

```
POST /api/agent/init
        │
        ▼
   ┌─────────────┐
   │  Scheduler   │──── repeats every ~15 min for 48 hours
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │  Discovery   │  ← Hacker News Algolia API + arXiv cs.AI RSS
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │  Editorial   │  ← LLM scores topics against persona interests
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │   Writer     │  ← LLM drafts post + rationale in persona voice
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │   Memory     │  ← SQLite + Breeth semantic memory (dedup & facts)
   └─────────────┘
          │
GET /api/agent/feed ← returns all posts, newest first
```

## Quick Start

### 1. Clone & install

```bash
cd shri-autonomous-ai
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your real API keys
```

### 3. Run

```bash
# Option A: via the entry point
python run.py

# Option B: via uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The server starts at `http://localhost:8000`.

### 4. Initialize an agent

```bash
curl -X POST http://localhost:8000/api/agent/init \
  -H "Content-Type: application/json" \
  -d '{"persona": {"name": "Shri", "domain": "AI Systems Engineer"}}'
```

Response:
```json
{"agentId": "some-uuid-here"}
```

### 5. Check the feed

```bash
curl "http://localhost:8000/api/agent/feed?agentId=<your-agent-id>"
```

Response:
```json
{
  "posts": [
    {
      "id": "unique-uuid",
      "createdAt": "2026-08-09T10:30:00Z",
      "text": "...",
      "rationale": "...",
      "sources": ["https://..."]
    }
  ]
}
```

Posts trickle in every ~15 minutes. The first post appears shortly after init.

---

## API Contract

| Endpoint | Method | Description |
|---|---|---|
| `/api/agent/init` | POST | Initialize an agent. Body: `{"persona": {"name": "...", "domain": "..."}}`. Returns `{"agentId": "..."}` |
| `/api/agent/feed` | GET | Get all posts. Query param: `agentId`. Returns `{"posts": [...]}` newest first. 404 if invalid agent ID. |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | **Yes** | — | Groq API key for LLM inference ([console.groq.com](https://console.groq.com)) |
| `BREETH_API_KEY` | **Yes** | — | Breeth API key for semantic memory ([docs.thebreeth.com](https://docs.thebreeth.com)) |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model name |
| `CYCLE_INTERVAL_MINUTES` | No | `15` | Minutes between autonomous publishing cycles |
| `RUNTIME_HOURS` | No | `48` | Total hours the agent runs autonomously after init |

---

## How It Works

1. **Topic Discovery** — The agent concurrently crawls Hacker News (Algolia API) and arXiv cs.AI RSS to find candidate AI/tech topics. No static or mocked data.
2. **Duplicate Filtering** — Before scoring, topics are checked against SQLite (URL + title match) and Breeth semantic memory (near-duplicate detection via LLM). Duplicates are rejected before reaching the editorial step.
3. **Editorial Judgment** — Each novel candidate is scored 0.0–1.0 by the LLM through the persona's editorial lens. Topics below the 0.55 threshold are rejected with a logged reason. The agent intentionally rejects topics that don't meet its standards — not every cycle produces posts.
4. **Post Writing** — Accepted topics are drafted as 2–4 paragraph posts in the persona's voice. Each post includes a rationale explaining why it was selected, why it's relevant now, and what sources were consulted.
5. **Memory & Persistence** — Posts are stored in SQLite. Key facts (topic + angle + summary) are written to Breeth as semantic facts. Previously published posts never disappear from the feed.
6. **Autonomous Loop** — APScheduler fires the full discover→judge→write→store cycle every ~15 minutes for up to 48 hours, with zero human input after initialization.

---

## Persona

The agent defaults to **Shri**, an **AI Systems Engineer** who:

- Focuses on: LLM inference optimization, ML systems design & MLOps, AI safety, open-source AI, AI hardware, developer productivity with AI
- Holds strong opinions: benchmark scores need latency context, open-weight models shift power to practitioners, "AI strategy" announcements need architecture diagrams
- Writes in a pragmatic, technically rigorous, staff-engineer voice
- Rejects: pure product announcements, crypto/web3, lifestyle/politics, duplicates, paywalled sources

All persona data lives in `app/persona.py` — the single source of truth.

---

## Project Structure

```
shri-autonomous-ai/
├── app/
│   ├── __init__.py
│   ├── config.py        # Groq client config + retry logic
│   ├── db.py            # SQLite setup (aiosqlite)
│   ├── models.py        # Pydantic request/response models
│   ├── persona.py       # Persona definition (single source of truth)
│   ├── discovery.py     # Live topic discovery (HN + arXiv)
│   ├── editorial.py     # LLM-based editorial scoring & rejection
│   ├── writer.py        # LLM-based post drafting
│   ├── memory.py        # Dedup checking, post storage, Breeth integration
│   ├── publisher.py     # Discover→judge→write→store pipeline
│   ├── scheduler.py     # APScheduler background loop
│   └── main.py          # FastAPI app with two endpoints
├── data/                # Created at runtime (agent.db lives here)
├── requirements.txt
├── .env.example
├── run.py               # Entry point
└── README.md
```

---

## Tech Stack

- **FastAPI** + **uvicorn** — async web framework
- **Groq** — Llama-3.3-70b on Groq for high-speed LLM inference
- **Breeth** — semantic memory API for fact storage and near-duplicate detection
- **aiosqlite** — async SQLite for persistent post storage
- **APScheduler** — in-process background job scheduler
- **httpx** — async HTTP client for Hacker News API and Breeth API
- **feedparser** — arXiv RSS parsing
