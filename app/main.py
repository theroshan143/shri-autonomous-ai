"""
FastAPI application — the only two endpoints are:

  POST /api/agent/init
  GET  /api/agent/feed
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.db import init_db
from app.memory import agent_exists, get_all_posts, register_agent
from app.models import FeedResponse, InitRequest, InitResponse
from app.persona import build_persona
from app.scheduler import start_agent

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-24s │ %(levelname)-5s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    await init_db()
    logger.info("Database initialized")
    yield


# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Shri Autonomous AI",
    description="An autonomous AI publishing agent that discovers, evaluates, and writes about AI/tech topics.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────────

@app.post("/api/agent/init", response_model=InitResponse)
async def init_agent(req: InitRequest):
    """
    Initialize a new autonomous agent.

    Called exactly once. Starts a background publishing loop that runs
    for ~48 hours with zero further input.
    """
    agent_id = str(uuid.uuid4())
    persona = build_persona(name=req.persona.name, domain=req.persona.domain)

    # Register in DB
    await register_agent(agent_id, req.persona.name, req.persona.domain)

    # Start the background scheduler
    start_agent(agent_id, persona)

    logger.info(
        "Agent %s initialized — persona='%s', domain='%s'",
        agent_id, req.persona.name, req.persona.domain,
    )

    return InitResponse(agentId=agent_id)


@app.get("/api/agent/feed", response_model=FeedResponse)
async def get_feed(agentId: str = Query(..., description="Agent ID returned from /init")):
    """
    Retrieve all posts published by an agent, newest first.

    Previously returned posts remain available forever.
    """
    if not await agent_exists(agentId):
        raise HTTPException(status_code=404, detail=f"Agent '{agentId}' not found")

    posts = await get_all_posts(agentId)
    return FeedResponse(posts=posts)
