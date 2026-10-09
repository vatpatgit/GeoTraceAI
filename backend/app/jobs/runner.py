"""Queue + worker loop.

Jobs live in ``analysis_jobs``. Workers claim with ``SELECT ... FOR UPDATE SKIP LOCKED`` so any number of worker
processes (``python -m app.jobs.worker``) or the embedded loop can run safely side by side; a lost worker is detected
by its stale heartbeat and the job is re-queued (idempotent re-run) or failed after too many attempts.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app import storage
from app.config import settings
from app.database import async_session_maker
from app.jobs.executor import execute_analysis
from app.models import AnalysisEvent, AnalysisJob
from app.models.analysis import ACTIVE_STATUSES

logger = logging.getLogger(__name__)
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
MAX_ATTEMPTS = 3


async def claim_next() -> uuid.UUID | None:
    async with async_session_maker() as db:
        stmt = (select(AnalysisJob).where(AnalysisJob.status == "queued", AnalysisJob.cancel_requested.is_(False))
                .order_by(AnalysisJob.created_at).limit(1).with_for_update(skip_locked=True))
        job = (await db.execute(stmt)).scalar_one_or_none()
        if job is None:
            return None
        now = datetime.now(timezone.utc)
        job.status, job.locked_by, job.heartbeat_at = "validating", WORKER_ID, now
        job.started_at = job.started_at or now
        job.attempt += 1
        job.stage_message = "Starting"
        db.add(AnalysisEvent(analysis_id=job.id, status="validating", progress=0.0, message=f"Picked up by worker (attempt {job.attempt})"))
        await db.commit()
        return job.id


async def recover_stale() -> int:
    """Re-queue (or fail) jobs whose worker stopped heartbeating."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.JOB_STALE_MINUTES)
    n = 0
    async with async_session_maker() as db:
        stale = (await db.execute(select(AnalysisJob).where(
            AnalysisJob.status.in_([s for s in ACTIVE_STATUSES if s != "queued"]),
            or_(AnalysisJob.heartbeat_at < cutoff, AnalysisJob.heartbeat_at.is_(None)),
            AnalysisJob.updated_at < cutoff).with_for_update(skip_locked=True))).scalars().all()
        for job in stale:
            if job.attempt >= MAX_ATTEMPTS:
                job.status, job.finished_at, job.locked_by = "failed", datetime.now(timezone.utc), None
                job.error = {"code": "worker_lost", "message": "The worker processing this analysis stopped responding.", "details": {"attempts": job.attempt}}
                msg = "Failed: worker lost"
            else:
                job.status, job.locked_by, job.progress = "queued", None, 0.0
                msg = f"Re-queued after worker loss (attempt {job.attempt})"
            job.stage_message = msg
            db.add(AnalysisEvent(analysis_id=job.id, status=job.status, progress=0.0, message=msg))
            n += 1
        await db.commit()
    return n


async def run_loop(stop: asyncio.Event, concurrency: int | None = None) -> None:
    limit = concurrency or settings.JOB_CONCURRENCY
    running: set[asyncio.Task] = set()
    last_recover = 0.0
    logger.info("job worker %s started (concurrency=%s)", WORKER_ID, limit)
    while not stop.is_set():
        try:
            now = asyncio.get_running_loop().time()
            if now - last_recover > 60:
                last_recover = now
                if await recover_stale():
                    logger.warning("recovered stale jobs")
                storage.cleanup_temp()
            if len(running) >= limit:  # bounded concurrency
                await asyncio.sleep(settings.JOB_POLL_SECONDS)
                continue
            job_id = await claim_next()
            if job_id is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=settings.JOB_POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                continue
            task = asyncio.create_task(execute_analysis(job_id))
            running.add(task)
            task.add_done_callback(running.discard)
        except Exception:
            logger.exception("worker loop error")
            await asyncio.sleep(2)
    if running:
        await asyncio.wait(running, timeout=30)


async def drain(max_jobs: int = 100) -> int:
    """Run queued jobs to completion in the foreground (used by tests and ``python -m app.jobs.worker --once``)."""
    done = 0
    while done < max_jobs:
        jid = await claim_next()
        if jid is None:
            break
        await execute_analysis(jid)
        done += 1
    return done
