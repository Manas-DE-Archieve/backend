from __future__ import annotations
from uuid import UUID
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class PersonBase(BaseModel):
    full_name: str
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    region: Optional[str] = None
    district: Optional[str] = None
    occupation: Optional[str] = None
    charge: Optional[str] = None
    arrest_date: Optional[date] = None
    sentence: Optional[str] = None
    sentence_date: Optional[date] = None
    rehabilitation_date: Optional[date] = None
    biography: Optional[str] = None
    source: Optional[str] = None


class PersonCreate(PersonBase):
    force: bool = False  # bypass duplicate warning


class PersonUpdate(PersonBase):
    full_name: Optional[str] = None


class PersonStatusUpdate(BaseModel):
    status: str  # pending | verified | rejected


class PersonOut(PersonBase):
    id: UUID
    status: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SimilarPerson(BaseModel):
    id: UUID
    full_name: str
    birth_year: Optional[int] = None
    region: Optional[str] = None
    similarity_score: float


class DuplicateCheckResponse(BaseModel):
    duplicates_found: bool
    similar_persons: List[SimilarPerson]
    message: str


class PersonListResponse(BaseModel):
    items: List[PersonOut]
    total: int
    page: int
    limit: int
