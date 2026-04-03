from __future__ import annotations
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


# ── Documents ──────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: UUID
    filename: str
    file_type: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ── Chat ───────────────────────────────────────────────────
class ChatSessionOut(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


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


# ── Auth ───────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True
