"""
Scheduler — fires the publishing cycle on a timer using APScheduler.

Each agent gets its own interval job that runs for up to RUNTIME_HOURS.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

# pyrefly: ignore [missing-import]
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.persona import Persona
from app.publisher import run_cycle

logger = logging.getLogger(__name__)

# Global scheduler instance (one per process)
_scheduler: AsyncIOScheduler | None = None

# Track active agents so we can shut down cleanly
_active_agents: Dict[str, dict] = {}


def _get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
        logger.info("APScheduler started")
    return _scheduler


def _cycle_interval() -> int:
    """Publishing cycle interval in minutes (default 15)."""
    return int(os.environ.get("CYCLE_INTERVAL_MINUTES", "15"))


def _runtime_hours() -> float:
    """Total autonomous runtime in hours (default 48)."""
    return float(os.environ.get("RUNTIME_HOURS", "48"))


async def _tick(agent_id: str, persona: Persona) -> None:
    """Wrapper called by APScheduler on each tick."""
    info = _active_agents.get(agent_id)
    if not info:
        return

    # Check if runtime exceeded
    elapsed = datetime.now(timezone.utc) - info["started_at"]
    max_runtime = timedelta(hours=_runtime_hours())

    if elapsed > max_runtime:
        logger.info(
            "Agent %s exceeded runtime (%.1f h). Removing job.",
            agent_id, elapsed.total_seconds() / 3600,
        )
        stop_agent(agent_id)
        return

    try:
        count = await run_cycle(agent_id, persona)
        info["cycles"] += 1
        info["total_posts"] += count
        logger.info(
            "Agent %s — cycle #%d done, %d posts this cycle, %d total",
            agent_id, info["cycles"], count, info["total_posts"],
        )
    except Exception as exc:
        logger.error("Cycle failed for agent %s: %s", agent_id, exc, exc_info=True)


def start_agent(agent_id: str, persona: Persona) -> None:
    """Register a repeating job for the given agent."""
    scheduler = _get_scheduler()
    interval = _cycle_interval()

    _active_agents[agent_id] = {
        "started_at": datetime.now(timezone.utc),
        "cycles": 0,
        "total_posts": 0,
        "persona": persona,
    }

    # Fire immediately, then repeat every `interval` minutes
    scheduler.add_job(
        _tick,
        trigger="interval",
        minutes=interval,
        args=[agent_id, persona],
        id=f"agent_{agent_id}",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),  # run first cycle immediately
    )

    logger.info(
        "Scheduled agent %s: every %d min for up to %.0f hours",
        agent_id, interval, _runtime_hours(),
    )


def stop_agent(agent_id: str) -> None:
    """Remove the job for an agent."""
    scheduler = _get_scheduler()
    job_id = f"agent_{agent_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    _active_agents.pop(agent_id, None)
    logger.info("Stopped agent %s", agent_id)


def is_agent_active(agent_id: str) -> bool:
    return agent_id in _active_agents
