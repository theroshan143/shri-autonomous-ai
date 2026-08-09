# Prompts Log — Shri Autonomous AI

This file documents the key prompts used during development (Vibe Coding) and the runtime prompt templates utilized by the agent during the 48-hour autonomous publishing loop.

---

## 1. Development Prompts

### Session 1 — Initial Scaffold & Architecture
Used to generate the core asynchronous FastAPI application, sqlite persistence, APScheduler loop, and HN/arXiv discovery layer.
```text
Build an autonomous AI publishing agent for the ABTalks Vibe Code Hackathon Problem Statement 3.
The agent must:
1. Crawl tech topics from live free sources (Hacker News Algolia API + arXiv cs.AI RSS feed).
2. Use an LLM to score topics based on a target persona's technical interests.
3. intentional reject weak topics (score below 0.55) and store rejections in SQLite database.
4. Use the LLM to draft a 2-4 paragraph tech post in the persona's voice including a rationale explaining why it was chosen.
5. Persist published posts in SQLite.
6. Integrate with Breeth API memory layer to query past published facts and write new published facts to prevent semantic duplication.
7. Run asynchronously in a background scheduler loop every 15 minutes for up to 48 hours in the same process as FastAPI.
8. Expose two endpoints: POST /api/agent/init (body: persona name and domain, returns agentId) and GET /api/agent/feed?agentId=<id> (returns posts in reverse chronological order).
```

### Session 2 — Groq Migration & Database Signature Alignment
Used to migrate model inference from Gemini to Groq Llama 3.3 and align functions to prevent SQLite errors.
```text
I am migrating the model integration from Gemini to Groq API.
1. Create a wrapper client using official `groq` SDK in config.py that includes exponential backoff retry logic to handle 429 rate limit errors gracefully.
2. Align function parameters in memory.py (`store_post` and `store_rejection`) to match what app/publisher.py calls.
3. Fix SQLite database exceptions by matching columns (agent_id, created_at, title, url, reason) exactly during database queries.
```

### Session 3 — Final Audit & Spec Compliance
Used to align the API shapes and timestamp formatting with the exact requirements of the hackathon evaluators.
```text
Review the code for ABTalks Vibe Code Hackathon Problem Statement 3.
1. Verify the feed response returns UTC timestamps ending with the 'Z' suffix (e.g. 2026-08-09T10:30:00Z) instead of '+00:00'. Create a helper function in memory.py to handle this.
2. Remove viewer.html and any frontend files from the workspace as the spec explicitly says they are out of scope.
3. Remove CORS middleware from app/main.py as we do not have a frontend.
```

---

## 2. Runtime Prompt Templates

These prompts are embedded in the agent's code (`app/persona.py` and `app/writer.py`) and are dynamically sent to the Groq API (`llama-3.3-70b-versatile`) during each autonomous cycle.

### A. Editorial Scoring Prompt
Used to evaluate whether a discovered topic matches Shri's persona interests and should be published.
```text
You are the editorial filter for {name}.
Domain: {domain}
Interests: {interests}

Score the following candidate topic from 0.0 to 1.0 on these axes:
  1. Relevance to the persona's interests (0-0.4)
  2. Recency / timeliness (0-0.3)
  3. Novelty vs already-published posts (0-0.3)

Reject (score=0) if any of these apply:
  • Pure product announcement with no technical substance
  • Crypto / blockchain / web3 unless directly about AI compute
  • Lifestyle, politics, or celebrity content
  • Duplicate or near-duplicate of a topic already published
  • Paywalled source with no public summary available

Return ONLY valid JSON: {"score": <float>, "accept": <bool>, "reject_reason": <string|null>}
```

### B. Post Writing Prompt
Used to draft the final article and compile the required metadata.
```text
Write a short post (2-4 paragraphs, ~150-250 words) about this topic:

Title: {title}
URL: {url}
Source: {source_name}
Summary: {summary}
Published: {published_at}

{recent_context}

Return ONLY valid JSON with exactly four keys:
{
  "text": "<your post text>",
  "rationale": "<why this topic was selected, why it is relevant now, and why it passed your editorial standards>",
  "angle": "<a brief summary of the angle/opinion/stance taken in the post (e.g. defends_x, critiques_y, etc.)>",
  "summary": "<a short one-sentence summary of the post content>"
}

CRITICAL: The output must be valid, parseable JSON. Do not include raw, unescaped double quotes inside any of the string fields. If you need to include quotes inside the post 'text' or 'rationale', use single quotes (e.g. 'real-time reasoning') instead.
```
