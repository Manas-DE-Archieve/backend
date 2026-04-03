import json
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.chat import ChatSession, ChatMessage
from app.schemas.document import ChatSessionOut, ChatMessageOut, MessageRequest
from app.routers.auth import get_current_user, oauth2_scheme
from app.models.user import User
from app.services.rag import stream_rag_answer

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def get_optional_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Returns user if token provided, None otherwise."""
    try:
        return await get_current_user(token, db)
    except Exception:
        return None


async def _get_session(session_id: UUID, db: AsyncSession) -> ChatSession:
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    session = ChatSession(user_id=current_user.id if current_user else None)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}", response_model=list[ChatMessageOut])
async def get_session_messages(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_session(session_id, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.post("/sessions/{session_id}/message")
async def send_message(
    session_id: UUID,
    body: MessageRequest,
    db: AsyncSession = Depends(get_db),
):
    await _get_session(session_id, db)

    # Save user message
    user_msg = ChatMessage(session_id=session_id, role="user", content=body.content)
    db.add(user_msg)
    await db.commit()

    # Build conversation history (last 10 messages)
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(11)  # 10 + the one we just saved
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [{"role": m.role, "content": m.content} for m in history_rows[:-1]]  # exclude current

    # Collect full response for saving
    full_response_tokens = []
    sources_data = None

    async def event_stream():
        nonlocal full_response_tokens, sources_data
        async for line in stream_rag_answer(db, body.content, history):
            yield line
            # Parse to collect tokens & sources for DB save
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                    if payload["type"] == "token":
                        full_response_tokens.append(payload["data"])
                    elif payload["type"] == "sources":
                        sources_data = payload["data"]
                except Exception:
                    pass

        # Save assistant message after streaming completes
        assistant_text = "".join(full_response_tokens)
        if assistant_text:
            asst_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
                sources=sources_data,
            )
            db.add(asst_msg)
            await db.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
