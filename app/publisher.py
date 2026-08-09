"""
Publisher — the discover→judge→write→store pipeline.

One call to `run_cycle()` performs a full autonomous publishing cycle.
The scheduler calls this on a timer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.discovery import discover_topics
from app.editorial import judge_candidates
from app.memory import get_recent_titles, store_post, write_breeth_fact
from app.models import ScoredTopic
from app.persona import Persona
from app.writer import write_post

logger = logging.getLogger(__name__)


async def run_cycle(agent_id: str, persona: Persona) -> int:
    """
    Execute one full discover → judge → write → store cycle.

    Returns the number of posts published in this cycle (0 or more).
    """
    logger.info("═══ Cycle start for agent %s ═══", agent_id)

    # 1. Discover
    candidates = await discover_topics(max_per_source=15)
    if not candidates:
        logger.warning("No candidates discovered this cycle.")
        return 0

    # 2. Judge
    accepted: list[ScoredTopic] = await judge_candidates(
        persona=persona,
        agent_id=agent_id,
        candidates=candidates,
        max_accept=2,
    )

    if not accepted:
        logger.info("No topics passed editorial review this cycle.")
        return 0

    # 3. Write & Store
    recent_titles = await get_recent_titles(agent_id)
    published_count = 0

    for scored in accepted:
        try:
            draft = await write_post(persona, scored, recent_titles)
            post_id = str(uuid.uuid4())

            await store_post(
                agent_id=agent_id,
                post_id=post_id,
                text=draft.text,
                rationale=draft.rationale,
                sources=[scored.topic.url],
                title=scored.topic.title,
                url=scored.topic.url,
            )

            # Write fact to Breeth memory layer
            if draft.angle and draft.summary:
                await write_breeth_fact(
                    subject=scored.topic.title,
                    predicate=draft.angle,
                    obj=draft.summary
                )

            published_count += 1
            recent_titles.insert(0, scored.topic.title)  # update context for next post

            logger.info(
                "Published post %s — '%s' (score=%.2f)",
                post_id, scored.topic.title, scored.score,
            )

        except Exception as exc:
            logger.error("Failed to publish post for '%s': %s", scored.topic.title, exc)

    logger.info("═══ Cycle end: %d posts published ═══", published_count)
    return published_count
