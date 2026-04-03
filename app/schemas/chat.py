from __future__ import annotations
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class ChatSessionOut(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionListResponse(BaseModel):
    items: List[ChatSessionOut]
    total: int
    page: int
    limit: int


class SourceChunk(BaseModel):
    chunk_id: str
    document_name: str
    chunk_text: str
    score: float


class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    sources: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MessageRequest(BaseModel):
    content: str