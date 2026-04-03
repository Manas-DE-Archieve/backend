# --- START OF FILE backend/app/schemas/document.py ---

from __future__ import annotations
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Documents ──────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: UUID
    filename: str
    file_type: Optional[str] = None
    status: str
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

# --- НОВЫЕ СХЕМЫ ДЛЯ ПРЕДУПРЕЖДЕНИЯ О ДУБЛИКАТАХ ---
class SimilarDocument(BaseModel):
    id: UUID
    filename: str
    similarity_score: float

class DuplicateDocumentResponse(BaseModel):
    duplicates_found: bool = True
    message: str
    similar_documents: List[SimilarDocument]
# --- END OF FILE backend/app/schemas/document.py ---