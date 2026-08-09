"""
Topic discovery — pull live items from Hacker News Algolia API and arXiv RSS.

No API keys required for either source.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import httpx

from app.models import CandidateTopic

logger = logging.getLogger(__name__)

# ── Hacker News Algolia API ───────────────────────────────────────────

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"

# Keywords used to filter AI/tech stories on HN
HN_KEYWORDS = [
    "AI", "LLM", "GPT", "machine learning", "deep learning",
    "neural network", "transformer", "inference", "MLOps",
    "open source AI", "Claude", "Gemini", "Llama",
    "fine-tuning", "RAG", "vector database", "AI safety",
    "alignment", "GPU", "TPU", "CUDA",
]


async def _fetch_hn_stories(client: httpx.AsyncClient, max_items: int = 20) -> List[CandidateTopic]:
    """Search HN for recent AI/tech stories."""
    topics: List[CandidateTopic] = []
    keywords_to_query = ["AI", "LLM", "machine learning", "GPT", "Claude", "Gemini", "Llama"]

    async def fetch_keyword(keyword: str) -> List[CandidateTopic]:
        try:
            resp = await client.get(
                HN_SEARCH_URL,
                params={
                    "query": keyword,
                    "tags": "story",
                    "hitsPerPage": 10,
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for hit in data.get("hits", []):
                    title = hit.get("title", "")
                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                    created = hit.get("created_at", "")
                    if title:
                        results.append(
                            CandidateTopic(
                                title=title,
                                url=url,
                                source_name="Hacker News",
                                published_at=created,
                                summary=None,
                            )
                        )
                return results
        except Exception as exc:
            logger.warning("HN fetch for '%s' failed: %s", keyword, exc)
        return []

    tasks = [fetch_keyword(kw) for kw in keywords_to_query]
    batches = await asyncio.gather(*tasks)

    seen_urls = set()
    for batch in batches:
        for topic in batch:
            if topic.url not in seen_urls:
                seen_urls.add(topic.url)
                topics.append(topic)

    return topics[:max_items]


# ── arXiv RSS (cs.AI) ─────────────────────────────────────────────────

ARXIV_RSS_URL = "https://rss.arxiv.org/rss/cs.AI"


async def _fetch_arxiv_stories(max_items: int = 15) -> List[CandidateTopic]:
    """Parse the arXiv cs.AI RSS feed."""
    topics: List[CandidateTopic] = []

    try:
        # feedparser is sync; run in executor to keep event loop free
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, ARXIV_RSS_URL)

        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").replace("\n", " ").strip()
            link = entry.get("link", "")
            summary = entry.get("summary", "").replace("\n", " ").strip()
            published = entry.get("published", "")

            if not title:
                continue

            topics.append(
                CandidateTopic(
                    title=title,
                    url=link,
                    source_name="arXiv cs.AI",
                    published_at=published or None,
                    summary=summary or None,
                )
            )
    except Exception as exc:
        logger.warning("arXiv RSS fetch failed: %s", exc)

    return topics


# ── Public interface ──────────────────────────────────────────────────


async def discover_topics(max_per_source: int = 15) -> List[CandidateTopic]:
    """
    Pull candidate topics from all live sources concurrently.
    Returns a merged, deduplicated list.
    """
    async with httpx.AsyncClient() as client:
        hn_task = _fetch_hn_stories(client, max_items=max_per_source)
        arxiv_task = _fetch_arxiv_stories(max_items=max_per_source)

        hn_topics, arxiv_topics = await asyncio.gather(
            hn_task, arxiv_task, return_exceptions=True
        )

    results: List[CandidateTopic] = []
    for batch in (hn_topics, arxiv_topics):
        if isinstance(batch, Exception):
            logger.warning("Source returned error: %s", batch)
            continue
        results.extend(batch)

    # Basic dedup by URL
    seen_urls: set[str] = set()
    unique: List[CandidateTopic] = []
    for t in results:
        if t.url not in seen_urls:
            seen_urls.add(t.url)
            unique.append(t)

    logger.info("Discovered %d unique candidate topics", len(unique))
    return unique
