# AI Usage Log — Autonomous AI Creator (Problem Statement 3)

## Tools Used
- Claude Opus 4.6 via Antigravity IDE (primary development)
- Claude Sonnet 4.6 via Claude.ai (architecture planning, prompt refinement, submission checklist)
- Gemini 3.5 Flash via Antigravity IDE (initial scaffolding and debugging)

## Development Sessions

### Session 1 — Initial Build (Gemini 3.5 Flash, Antigravity IDE)
**Prompt summary:** Build an autonomous AI publishing agent for the ABTalks Vibe Code Hackathon Problem Statement 3. The agent must discover AI/tech topics from live sources (Hacker News, arXiv), apply editorial judgment using an LLM, write posts in a consistent persona voice, store them in SQLite, and publish autonomously over 48 hours after a single API initialization call.
**Output:** Full project scaffold including main.py, db.py, models.py, persona.py, discovery.py, editorial.py, writer.py, memory.py, scheduler.py, publisher.py. Configured Groq API integration, Breeth semantic memory, APScheduler background loop, and the two required API endpoints.

### Session 2 — Groq Migration & Debugging (Gemini 3.5 Flash, Antigravity IDE)
**Prompt summary:** Migrate the LLM backend from Gemini to Groq API. Fix rate limiting issues, add exponential backoff retry logic, resolve SQLite schema mismatches, fix store_post/store_rejection parameter signatures, and verify the full discover→judge→write→store pipeline works end-to-end.
**Output:** Fixed config.py with call_groq_with_retry wrapper, corrected memory.py function signatures, resolved database column mismatches, verified posts appear in the feed endpoint.

### Session 3 — Finalization & Audit (Claude Opus 4.6, Antigravity IDE)
**Prompt summary:** Reviewed full codebase against hackathon spec (all 12 verification tasks). Verified API contract matches exactly, fixed timestamp format to ISO 8601 with Z suffix, removed viewer.html (out of scope), rewrote README.md, verified editorial rejection logging, confirmed Breeth memory integration, ran full end-to-end simulation.
**Output:** Fixed UTC timestamps to use Z suffix, removed CORS middleware and viewer.html, rewrote README with deployment instructions, confirmed all API response shapes match spec, verified autonomous publishing loop works across multiple cycles with proper deduplication.

## AI Models Used in the Project Runtime
- **Groq API** (`llama-3.3-70b-versatile`) — LLM for topic editorial scoring and post writing
- **Breeth API** — Semantic memory layer for episode storage, fact recording, and near-duplicate detection

## Notes
All AI tools were used within ABTalks Vibe Code Hackathon rules. The autonomous agent runtime uses Groq (not the development AI tools) for its live inference during the 48-hour evaluation window. Development AI tools were used only for code generation, debugging, and review — they are not part of the running system.
