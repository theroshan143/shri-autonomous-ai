"""
Pydantic models for API request/response and internal data transfer.
"""

from __future__ import annotations

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import List, Optional


# ── API request / response models ──────────────────────────────────────


class PersonaInput(BaseModel):
    name: str = Field(..., description="Name of the AI persona")
    domain: str = Field(..., description="Domain of expertise (e.g. 'AI/ML')")


class InitRequest(BaseModel):
    persona: PersonaInput


class InitResponse(BaseModel):
    agentId: str


class PostOut(BaseModel):
    id: str
    createdAt: str
    text: str
    rationale: str
    sources: List[str]


class FeedResponse(BaseModel):
    posts: List[PostOut]


# ── Internal data-transfer objects ─────────────────────────────────────


class CandidateTopic(BaseModel):
    """A raw story/item pulled from a live source."""
    title: str
    url: str
    source_name: str  # e.g. "Hacker News", "arXiv cs.AI"
    published_at: Optional[str] = None  # ISO 8601 if available
    summary: Optional[str] = None


class ScoredTopic(BaseModel):
    """A candidate after editorial scoring."""
    topic: CandidateTopic
    score: float = Field(..., ge=0.0, le=1.0)
    accept: bool
    reject_reason: Optional[str] = None


class DraftPost(BaseModel):
    """Output of the writer before storing."""
    text: str
    rationale: str
    angle: Optional[str] = None
    summary: Optional[str] = None
