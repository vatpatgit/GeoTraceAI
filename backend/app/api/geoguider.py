"""GeoGuider API: chat turns, conversation history, workflow status / confirm / cancel. All data is scoped to the calling user."""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import llm
from app.auth.dependencies import require_authenticated_user
from app.config import settings
from app.database import get_db
from app.geoguider import engine
from app.geoguider.schemas import (ChatRequest, ChatResponse, ConversationOut, MessageOut, StatusOut, WState, Workflow, WorkflowOut)
from app.geoguider.tools import ToolContext, registry
from app.geoguider.workflow import RUNNING, InvalidTransition
from app.ml import registry as ml_registry
from app.models import GeoGuiderConversation, GeoGuiderMessage, User

logger = logging.getLogger(__name__)
router = APIRouter()
_hits: dict[uuid.UUID, deque] = defaultdict(deque)


def _enabled() -> None:
    if not settings.GEOGUIDER_ENABLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GeoGuider is disabled on this server.")


def _rate_limit(user_id: uuid.UUID) -> None:
    now = time.monotonic()
    q = _hits[user_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.GEOGUIDER_RATE_PER_MIN:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "rate_limited", "message": "You're sending messages too quickly. Wait a moment and try again."},
                            headers={"Retry-After": "30"})
    q.append(now)


async def _load(db: AsyncSession, user_id: uuid.UUID, conv_id: uuid.UUID, lock: bool = False) -> GeoGuiderConversation:
    q = select(GeoGuiderConversation).where(GeoGuiderConversation.id == conv_id, GeoGuiderConversation.user_id == user_id)  # ownership in the query itself
    if lock:
        q = q.with_for_update()
    conv = (await db.execute(q)).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


def _msg(db: AsyncSession, conv_id: uuid.UUID, role: str, content: str, reply: engine.Reply | None = None, trace: list | None = None) -> MessageOut:
    """Add a message row and return its API form built from plain values (a tool rollback expires ORM objects, which async code cannot reload)."""
    row = dict(id=uuid.uuid4(), conversation_id=conv_id, role=role, content=content[:6000], blocks=reply.blocks if reply else [],
               actions=reply.actions if reply else [], tool_calls=trace or [], created_at=datetime.now(timezone.utc))
    db.add(GeoGuiderMessage(**row))
    return MessageOut(id=row["id"], role=role, content=row["content"], blocks=row["blocks"], actions=row["actions"], created_at=row["created_at"])


async def _workflow_out(db: AsyncSession, user: User, conv_id: uuid.UUID, wf: Workflow) -> WorkflowOut:
    jobs: list[dict[str, Any]] = []
    if wf.job_ids:
        res = await registry.call("get_analysis_status", {"analysis_ids": wf.job_ids}, ToolContext(db, user, conv_id))
        jobs = res.data.get("jobs", []) if res.ok else []
    return WorkflowOut(conversation_id=conv_id, state=wf.state, pending=wf.pending, job_ids=wf.job_ids, jobs=jobs, cancellable=wf.state in RUNNING,
                       aoi=wf.aoi and {k: wf.aoi[k] for k in ("id", "name", "bbox", "area_km2") if k in wf.aoi}, period=wf.period, error=wf.error)


async def _save(db: AsyncSession, conv_id: uuid.UUID, wf: Workflow, title: str | None = None) -> None:
    conv = await db.get(GeoGuiderConversation, conv_id, populate_existing=True)  # reload: a tool rollback expires loaded rows
    conv.workflow = wf.model_dump(mode="json")
    if title and conv.title == "New conversation":
        conv.title = title[:80]
    conv.updated_at = datetime.now(timezone.utc)


async def _run_turn(db: AsyncSession, user: User, conv_id: uuid.UUID, wf: Workflow, ui, req: ChatRequest) -> tuple[engine.Reply, Workflow, list]:
    turn = engine.Turn(db, user, conv_id, wf, ui)
    try:
        reply = await (turn.choose(req.choice.pending_id, req.choice.option_id) if req.choice else turn.message(req.message or ""))
    except InvalidTransition as exc:
        logger.warning("geoguider invalid transition: %s", exc)
        reply = engine.Reply("That step isn't possible from where this analysis currently is. Tell me what you'd like to do and I'll start from a clean state.")
    except Exception:
        logger.exception("geoguider turn failed")
        await db.rollback()
        reply = engine.Reply("Something went wrong on my side while handling that. Nothing was started. Please try again.",
                             blocks=[{"type": "error", "code": "internal_error", "message": "Unexpected error (logged).", "retryable": True}])
    return reply, turn.wf, turn.ctx.trace


@router.get("/status", response_model=StatusOut)
async def geoguider_status(user: User = Depends(require_authenticated_user)):
    _enabled()
    cap = await engine.capabilities()
    return StatusOut(
        enabled=True,
        llm={"configured": cap["llm"], "provider": settings.LLM_PROVIDER if cap["llm"] else None, "mode": "llm" if cap["llm"] else "rules",
             "note": None if cap["llm"] else "No LLM is configured (LLM_PROVIDER / LLM_API_KEY / LLM_MODEL). GeoGuider uses its built-in command parser: it understands common requests "
                                             "but not free-form language."},
        geocoder={"configured": cap["geocoder"], "provider": settings.GEOCODER_PROVIDER},
        satellite={"catalogue": cap["catalogue"], "imagery": cap["imagery"]},
        weather={"configured": cap["weather"]},
        model={"id": settings.GEOGUIDER_MODEL_ID, "ready": cap["model"]},
        capabilities={"change_detection": cap["change_detection"], "weather_alerts": cap["weather"], "results": True, "place_search": cap["geocoder"],
                      "trend_analysis": False, "environmental_values": False})


@router.get("/tools")
async def list_tools(user: User = Depends(require_authenticated_user)):
    _enabled()
    return {"tools": registry.describe()}


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    _enabled()
    user_id = user.id
    _rate_limit(user_id)
    if body.message and len(body.message) > settings.GEOGUIDER_MAX_MESSAGE_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "message_too_long", "message": f"Messages are limited to {settings.GEOGUIDER_MAX_MESSAGE_CHARS} characters."})
    if body.conversation_id:
        conv = await _load(db, user_id, body.conversation_id, lock=True)
    else:
        conv = GeoGuiderConversation(id=uuid.uuid4(), user_id=user_id, title="New conversation", workflow={})
        db.add(conv)
        await db.commit()  # committed before any tool runs: a tool failure rolls back its own work only
        conv = await _load(db, user_id, conv.id, lock=True)
    conv_id = conv.id
    wf = Workflow.model_validate(conv.workflow or {})
    text = (body.message or "").strip()
    if body.choice and not text:
        p = wf.pending
        o = next((o for o in (p.options if p else []) if o.id == body.choice.option_id), None)
        text = o.label if o else "(choice)"
    msgs = [_msg(db, conv_id, "user", text)]
    await db.commit()  # the user's message is kept even if a step fails
    conv = await _load(db, user_id, conv_id, lock=True)  # re-lock for the whole turn and re-read the workflow another request may have changed meanwhile
    wf = Workflow.model_validate(conv.workflow or {})
    reply, wf, trace = await _run_turn(db, user, conv_id, wf, body.ui, body)
    # the user may have been reloaded by a tool recovery; fetch what the response needs from ids, not from possibly expired objects
    msgs.append(_msg(db, conv_id, "assistant", reply.text or "Done.", reply, trace))
    await _save(db, conv_id, wf, title=text)
    await db.commit()
    user = await db.get(User, user_id, populate_existing=True)
    return ChatResponse(conversation_id=conv_id, messages=msgs, workflow=await _workflow_out(db, user, conv_id, wf),
                        suggestions=reply.suggestions[:5])


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    _enabled()
    rows = (await db.execute(select(GeoGuiderConversation).where(GeoGuiderConversation.user_id == user.id).order_by(GeoGuiderConversation.updated_at.desc()).limit(20))).scalars().all()
    return [ConversationOut(id=c.id, title=c.title, updated_at=c.updated_at) for c in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    _enabled()
    conv = await _load(db, user.id, conversation_id)
    rows = (await db.execute(select(GeoGuiderMessage).where(GeoGuiderMessage.conversation_id == conv.id).order_by(GeoGuiderMessage.created_at).limit(300))).scalars().all()
    wf = Workflow.model_validate(conv.workflow or {})
    return ConversationOut(id=conv.id, title=conv.title, updated_at=conv.updated_at, messages=[MessageOut.model_validate(m) for m in rows],
                           workflow=await _workflow_out(db, user, conv.id, wf))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    _enabled()
    conv = await _load(db, user.id, conversation_id)
    await db.delete(conv)
    await db.commit()


async def _sync(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> dict[str, Any]:
    user_id = user.id
    conv = await _load(db, user_id, conversation_id, lock=True)  # serialises concurrent polls: results are announced exactly once
    wf = Workflow.model_validate(conv.workflow or {})
    new: list[MessageOut] = []
    turn = engine.Turn(db, user, conversation_id, wf, None)
    try:
        reply = await turn.sync()
    except InvalidTransition as exc:
        logger.warning("geoguider sync transition: %s", exc)
        reply = None
    if reply is not None:
        new.append(_msg(db, conversation_id, "assistant", reply.text or "Done.", reply, turn.ctx.trace))
    await _save(db, conversation_id, turn.wf)
    await db.commit()
    user = await db.get(User, user_id, populate_existing=True)
    return {"workflow": await _workflow_out(db, user, conversation_id, turn.wf), "new_messages": new}


@router.get("/conversations/{conversation_id}/workflow")
async def workflow_status(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    """Live workflow state. Polling this also advances it from the real job states and posts the results message once they exist."""
    _enabled()
    return await _sync(db, user, conversation_id)


@router.post("/conversations/{conversation_id}/workflow/confirm", response_model=ChatResponse)
async def workflow_confirm(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    _enabled()
    conv = await _load(db, user.id, conversation_id)
    wf = Workflow.model_validate(conv.workflow or {})
    if wf.state != WState.SCENES_SELECTED or wf.pending is None or wf.pending.kind != "confirm_plan":
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "nothing_to_confirm", "message": "There is no plan waiting for confirmation."})
    from app.geoguider.schemas import ChoicePick
    return await chat(ChatRequest(conversation_id=conversation_id, choice=ChoicePick(pending_id=wf.pending.id, option_id="confirm")), db, user)


@router.post("/conversations/{conversation_id}/workflow/cancel", response_model=ChatResponse)
async def workflow_cancel(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_authenticated_user)):
    _enabled()
    await _load(db, user.id, conversation_id)
    return await chat(ChatRequest(conversation_id=conversation_id, message="cancel"), db, user)
