"""
Memory layer — query helpers for the posts & rejections tables.

Provides dedup checking and context retrieval so the agent doesn't
repeat itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import asyncio
from datetime import datetime, timezone
from typing import List, Optional


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 with Z suffix (not +00:00)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# pyrefly: ignore [missing-import]
import httpx
# pyrefly: ignore [missing-import]
from groq import AsyncGroq

from app.config import GROQ_API_KEY, GROQ_MODEL, call_groq_with_retry
from app.db import get_db_conn
from app.models import CandidateTopic, PostOut

logger = logging.getLogger(__name__)

BREETH_API_URL = "https://api.thebreeth.com/v1"


def _get_groq_client() -> AsyncGroq:
    return AsyncGroq(api_key=GROQ_API_KEY)


async def is_url_duplicate(agent_id: str, url: str) -> bool:
    """Check SQLite to see if the URL has already been published."""
    async with get_db_conn() as db:
        cursor = await db.execute(
            "SELECT 1 FROM posts WHERE agent_id = ? AND sources LIKE ? LIMIT 1",
            (agent_id, f"%{url}%"),
        )
        row = await cursor.fetchone()
        return row is not None


async def is_duplicate(agent_id: str, topic: CandidateTopic) -> tuple[bool, str]:
    """
    Check if a topic is a duplicate.
    1. Direct URL check in local SQLite.
    2. Exact title check in local SQLite.
    3. Semantic similarity check against Breeth past facts.
    """
    # 1. Check URL
    if await is_url_duplicate(agent_id, topic.url):
        return True, "Duplicate URL in local memory"

    # 2. Check exact title
    async with get_db_conn() as db:
        cursor = await db.execute(
            "SELECT 1 FROM posts WHERE agent_id = ? AND title = ? LIMIT 1",
            (agent_id, topic.title),
        )
        row = await cursor.fetchone()
        if row is not None:
            return True, "Duplicate title in local memory"

    # 3. Semantic similarity check via Breeth Memory
    try:
        related_edges = await query_breeth_search(topic.title)
        if related_edges:
            too_similar, reason = await check_similarity_with_llm(
                topic.title,
                topic.summary or "",
                related_edges
            )
            if too_similar:
                return True, f"Semantic duplicate: {reason}"
    except Exception as exc:
        logger.error("Failed to run semantic similarity check: %s", exc)

    return False, ""


async def query_breeth_search(query_str: str) -> List[dict]:
    """Query Breeth Memory API search endpoint to find related past facts."""
    api_key = os.environ.get("BREETH_API_KEY")
    if not api_key:
        logger.warning("BREETH_API_KEY env var not set; skipping semantic search.")
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query_str,
        "limit": 5,
        "score_threshold": 0.4
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BREETH_API_URL}/search",
                json=payload,
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("edges", [])
            else:
                logger.error("Breeth search failed with status %d: %s", resp.status_code, resp.text)
                return []
    except Exception as exc:
        logger.error("Exception during Breeth search: %s", exc)
        return []


async def check_similarity_with_llm(
    candidate_title: str,
    candidate_summary: str,
    related_edges: List[dict]
) -> tuple[bool, str]:
    """Use Groq to check if the candidate is too semantically similar to past facts."""
    facts_str = "\n".join(f"- {edge.get('fact')}" for edge in related_edges if edge.get('fact'))
    if not facts_str:
        return False, ""

    user_msg = (
        f"Candidate Topic:\n"
        f"  Title: {candidate_title}\n"
        f"  Summary: {candidate_summary or 'N/A'}\n\n"
        f"Recently Published Facts from Memory:\n"
        f"{facts_str}\n\n"
        "Determine if the candidate topic is too similar to any of the recently published facts (i.e. covering the same development or taking the same angle/stance).\n"
        "Return ONLY a JSON object with two keys:\n"
        "{\n"
        "  \"too_similar\": true or false,\n"
        "  \"reason\": \"<brief explanation of why it is or is not too similar>\"\n"
        "}"
    )

    messages = [
        {"role": "system", "content": "You are a similarity checking assistant."},
        {"role": "user", "content": user_msg}
    ]

    try:
        client = _get_groq_client()
        response = await call_groq_with_retry(
            client=client,
            messages=messages,
            model=GROQ_MODEL,
            temperature=0.1,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        return bool(result.get("too_similar", False)), str(result.get("reason", ""))
    except Exception as exc:
        logger.error("Failed to check topic similarity with LLM: %s", exc)
        return False, f"Similarity check error: {exc}"


def topic_hash(title: str, url: str) -> str:
    """Generate a stable 8-char hash of a topic."""
    hasher = hashlib.md5(f"{title}:{url}".encode("utf-8"))
    return hasher.hexdigest()[:8]


async def store_rejection(agent_id: str, title: str, url: str, reason: str) -> None:
    """Store a candidate rejection in SQLite database."""
    async with get_db_conn() as db:
        await db.execute(
            """
            INSERT INTO rejections (agent_id, created_at, title, url, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                _utc_now_iso(),
                title,
                url,
                reason
            )
        )
        await db.commit()


async def get_recent_titles(agent_id: str, limit: int = 20) -> List[str]:
    """Retrieve list of recently published post titles for an agent."""
    async with get_db_conn() as db:
        cursor = await db.execute(
            "SELECT title FROM posts WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def store_post(
    agent_id: str,
    post_id: str,
    text: str,
    rationale: str,
    sources: List[str],
    title: str,
    url: str,
) -> None:
    """Persist a published post."""
    now = _utc_now_iso()
    h = topic_hash(title, url)
    async with get_db_conn() as db:
        await db.execute(
            "INSERT INTO posts (id, agent_id, created_at, text, rationale, sources, topic_hash, title) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (post_id, agent_id, now, text, rationale, json.dumps(sources), h, title),
        )
        await db.commit()


async def get_all_posts(agent_id: str) -> List[PostOut]:
    """Return all posts for an agent, newest first (for the feed endpoint)."""
    async with get_db_conn() as db:
        cursor = await db.execute(
            "SELECT id, created_at, text, rationale, sources "
            "FROM posts WHERE agent_id = ? ORDER BY created_at DESC",
            (agent_id,),
        )
        rows = await cursor.fetchall()

    posts: List[PostOut] = []
    for row in rows:
        posts.append(
            PostOut(
                id=row["id"],
                createdAt=row["created_at"],
                text=row["text"],
                rationale=row["rationale"],
                sources=json.loads(row["sources"]) if row["sources"] else [],
            )
        )
    return posts


async def agent_exists(agent_id: str) -> bool:
    """Check whether an agent has been registered."""
    async with get_db_conn() as db:
        cursor = await db.execute(
            "SELECT 1 FROM agents WHERE agent_id = ? LIMIT 1",
            (agent_id,),
        )
        return (await cursor.fetchone()) is not None


async def register_agent(agent_id: str, name: str, domain: str) -> None:
    """Insert a new agent record."""
    now = _utc_now_iso()
    async with get_db_conn() as db:
        await db.execute(
            "INSERT INTO agents (agent_id, persona_name, persona_domain, created_at) "
            "VALUES (?, ?, ?, ?)",
            (agent_id, name, domain, now),
        )
        await db.commit()


async def write_breeth_fact(subject: str, predicate: str, obj: str) -> None:
    """Write a new fact node to Breeth memory layer."""
    api_key = os.environ.get("BREETH_API_KEY")
    if not api_key:
        logger.warning("BREETH_API_KEY not found; skipping writing fact to Breeth.")
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "group_id": "default"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BREETH_API_URL}/facts",
                json=payload,
                headers=headers
            )
            if resp.status_code in (200, 201):
                logger.info("Successfully wrote fact to Breeth memory: %s %s %s", subject, predicate, obj)
            else:
                logger.error("Failed to write fact to Breeth (status %d): %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Exception writing fact to Breeth: %s", exc)

