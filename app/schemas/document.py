from __future__ import annotations
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    file_type: Optional[str] = None
    status: str
    verification_status: str = "verified"
    similarity_score: Optional[float] = None
    duplicate_of_id: Optional[UUID] = None
    uploaded_by: Optional[UUID] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class DocumentDetailOut(DocumentOut):
    raw_text: Optional[str] = None


class DocumentListResponse(BaseModel):
    items: List[DocumentOut]
    total: int
    page: int
    limit: int


class SimilarDocument(BaseModel):
    id: UUID
    filename: str
    similarity_score: float


class DuplicateDocumentResponse(BaseModel):
    duplicates_found: bool = True
    message: str
    similar_documents: List[SimilarDocument]


class DocumentVerifyRequest(BaseModel):
    status: str  # verified | rejected