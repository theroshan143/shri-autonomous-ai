"""
Editorial judgment — scores candidate topics using the Groq LLM
through the lens of the configured persona.

Candidates that score below the threshold are rejected with a logged reason.
"""

from __future__ import annotations

import json
import logging
import asyncio
from typing import List

# pyrefly: ignore [missing-import]
from groq import AsyncGroq

from app.config import GROQ_API_KEY, GROQ_MODEL, call_groq_with_retry
from app.models import CandidateTopic, ScoredTopic
from app.persona import Persona
from app import memory

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.55  # topics below this are rejected


def _get_client() -> AsyncGroq:
    return AsyncGroq(api_key=GROQ_API_KEY)


async def score_topic(
    persona: Persona,
    topic: CandidateTopic,
    already_published_titles: List[str],
) -> ScoredTopic:
    """
    Ask the LLM to score a single candidate topic.
    Returns a ScoredTopic with accept/reject decision.
    """
    published_context = (
        "Already-published titles (avoid duplicates):\n"
        + "\n".join(f"  - {t}" for t in already_published_titles[-20:])
        if already_published_titles
        else "No posts published yet."
    )

    user_msg = (
        f"Candidate topic:\n"
        f"  Title: {topic.title}\n"
        f"  URL: {topic.url}\n"
        f"  Source: {topic.source_name}\n"
        f"  Published: {topic.published_at or 'unknown'}\n"
        f"  Summary: {topic.summary or 'N/A'}\n\n"
        f"{published_context}"
    )

    messages = [
        {"role": "system", "content": persona.scoring_prompt()},
        {"role": "user", "content": user_msg}
    ]

    try:
        client = _get_client()
        response = await call_groq_with_retry(
            client=client,
            messages=messages,
            model=GROQ_MODEL,
            temperature=0.2,
            max_tokens=256,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        score = float(result.get("score", 0.0))
        accept = bool(result.get("accept", False))
        reject_reason = result.get("reject_reason")

        # Override: enforce threshold even if LLM said accept
        if score < SCORE_THRESHOLD:
            accept = False
            reject_reason = reject_reason or f"Score {score:.2f} below threshold {SCORE_THRESHOLD}"

        return ScoredTopic(
            topic=topic,
            score=score,
            accept=accept,
            reject_reason=reject_reason,
        )

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Failed to parse LLM scoring response: %s", exc)
        return ScoredTopic(
            topic=topic,
            score=0.0,
            accept=False,
            reject_reason=f"Scoring parse error: {exc}",
        )
    except Exception as exc:
        logger.error("LLM scoring call failed: %s", exc)
        return ScoredTopic(
            topic=topic,
            score=0.0,
            accept=False,
            reject_reason=f"Scoring API error: {exc}",
        )


async def judge_candidates(
    persona: Persona,
    agent_id: str,
    candidates: List[CandidateTopic],
    max_accept: int = 2,
) -> List[ScoredTopic]:
    """
    Run editorial judgment on a batch of candidates.

    1. Pre-filter duplicates via memory.
    2. Score remaining with the LLM.
    3. Return up to `max_accept` accepted topics (highest score first).
    4. Log rejections.
    """
    published_titles = await memory.get_recent_titles(agent_id)

    # Pre-filter: skip known duplicates before calling the LLM
    novel_candidates: List[CandidateTopic] = []
    for c in candidates:
        is_dup, reason = await memory.is_duplicate(agent_id, c)
        if is_dup:
            logger.info("Pre-filter duplicate: %s (%s)", c.title, reason)
            await memory.store_rejection(agent_id, c.title, c.url, reason)
            continue
        novel_candidates.append(c)

    if not novel_candidates:
        logger.info("No novel candidates to score this cycle.")
        return []

    # Score each candidate (sequential to respect API rate limits)
    scored: List[ScoredTopic] = []
    accepted_count = 0
    for candidate in novel_candidates[:10]:  # cap LLM calls per cycle
        if accepted_count >= max_accept:
            logger.info("Found %d accepted topics, stopping scoring early.", accepted_count)
            break

        result = await score_topic(persona, candidate, published_titles)
        scored.append(result)

        if result.accept:
            accepted_count += 1
        else:
            await memory.store_rejection(
                agent_id, candidate.title, candidate.url,
                result.reject_reason or "Below threshold",
            )

        # Proactively sleep 6 seconds between scoring queries to respect rate limits
        await asyncio.sleep(6.0)

    # Filter for accepted topics
    accepted = [s for s in scored if s.accept]

    logger.info(
        "Editorial: %d candidates → %d scored → %d accepted",
        len(candidates), len(scored), len(accepted),
    )
    return accepted
