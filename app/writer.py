"""
Writer — drafts a post using the Groq LLM with the persona's voice.

Takes a scored topic + memory context and produces a DraftPost with
the text and a rationale field explaining the editorial decision.
"""

from __future__ import annotations

import json
import logging
from typing import List

# pyrefly: ignore [missing-import]
from groq import AsyncGroq

from app.config import GROQ_API_KEY, GROQ_MODEL, call_groq_with_retry
from app.models import DraftPost, ScoredTopic
from app.persona import Persona

logger = logging.getLogger(__name__)


def _get_client() -> AsyncGroq:
    return AsyncGroq(api_key=GROQ_API_KEY)


async def write_post(
    persona: Persona,
    scored: ScoredTopic,
    recent_titles: List[str],
) -> DraftPost:
    """
    Draft a short post and its rationale using the LLM.

    The prompt combines:
      • The persona's system prompt (voice, interests, style)
      • The chosen topic's details
      • Recent titles for context (avoid repetition in angle)
    """
    recent_context = (
        "Your recent posts covered these topics (don't repeat the same angle):\n"
        + "\n".join(f"  - {t}" for t in recent_titles[-15:])
        if recent_titles
        else "This is your first post — introduce your perspective naturally."
    )

    user_msg = (
        f"Write a short post (2-4 paragraphs, ~150-250 words) about this topic:\n\n"
        f"Title: {scored.topic.title}\n"
        f"URL: {scored.topic.url}\n"
        f"Source: {scored.topic.source_name}\n"
        f"Summary: {scored.topic.summary or 'N/A'}\n"
        f"Published: {scored.topic.published_at or 'recently'}\n\n"
        f"{recent_context}\n\n"
        "Return ONLY valid JSON with exactly four keys:\n"
        '{\n'
        '  "text": "<your post text>",\n'
        '  "rationale": "<why this topic was selected, why it is relevant now, and why it passed your editorial standards>",\n'
        '  "angle": "<a brief summary of the angle/opinion/stance taken in the post (e.g. defends_x, critiques_y, etc.)>",\n'
        '  "summary": "<a short one-sentence summary of the post content>"\n'
        '}\n\n'
        "CRITICAL: The output must be valid, parseable JSON. Do not include raw, unescaped double quotes inside any of the string fields. "
        "If you need to include quotes inside the post 'text' or 'rationale', use single quotes (e.g. 'real-time reasoning') instead."
    )

    messages = [
        {"role": "system", "content": persona.system_prompt()},
        {"role": "user", "content": user_msg}
    ]

    try:
        client = _get_client()
        response = await call_groq_with_retry(
            client=client,
            messages=messages,
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        return DraftPost(
            text=result["text"],
            rationale=result["rationale"],
            angle=result.get("angle"),
            summary=result.get("summary"),
        )

    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse writer LLM response: %s", exc)
        fallback_text = raw if 'raw' in dir() else f"Interesting development: {scored.topic.title}"
        return DraftPost(
            text=fallback_text,
            rationale=f"Auto-generated fallback due to parse error: {exc}",
        )

    except Exception as exc:
        logger.error("Writer LLM call failed: %s", exc)
        return DraftPost(
            text=f"Notable development in {persona.domain}: {scored.topic.title}. "
                 f"Read more at {scored.topic.url}",
            rationale=f"Fallback post — LLM error: {exc}",
        )
