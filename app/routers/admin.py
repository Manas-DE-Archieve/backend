from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.document import Document
from app.models.person import Person
from app.schemas.user import UserOut, UserRoleUpdate, UserListResponse
from app.schemas.document import DocumentOut, DocumentListResponse, DocumentVerifyRequest
from app.schemas.person import PersonOut, PersonListResponse
from app.routers.auth import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=UserListResponse)
async def list_users(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("super_admin")),
):
    query = select(User)
    if q:
        query = query.where(User.email.ilike(f"%{q}%"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    users = (await db.execute(query)).scalars().all()

    return UserListResponse(items=list(users), total=total, page=page, limit=limit)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: UUID,
    body: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("super_admin")),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role.")
    if body.role not in ["user", "moderator"]:
        raise HTTPException(status_code=400, detail="Invalid role.")

    result = await db.execute(select(User).where(User.id == user_id))
    user_to_update = result.scalar_one_or_none()
    if not user_to_update:
        raise HTTPException(status_code=404, detail="User not found.")
    if user_to_update.role == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot change the role of another super admin.")

    user_to_update.role = body.role
    await db.commit()
    await db.refresh(user_to_update)
    return user_to_update


# ── Persons moderation ─────────────────────────────────────────────────────────

@router.get("/pending-persons", response_model=PersonListResponse)
async def list_pending_persons(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    query = select(Person).where(Person.status == "pending")
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    rows = (await db.execute(
        query.order_by(Person.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    return PersonListResponse(items=list(rows), total=total, page=page, limit=limit)


@router.patch("/persons/{person_id}/verify", response_model=PersonOut)
async def verify_person(
    person_id: UUID,
    body: DocumentVerifyRequest,  # reuse: status = verified | rejected
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Person not found")
    if body.status not in ("verified", "rejected"):
        raise HTTPException(400, "Status must be 'verified' or 'rejected'")
    person.status = body.status
    await db.commit()
    await db.refresh(person)
    return person


# ── Documents moderation ───────────────────────────────────────────────────────

@router.get("/pending-documents", response_model=DocumentListResponse)
async def list_pending_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    min_similarity: float = Query(0.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    """
    Returns documents pending moderation, sorted by similarity_score DESC.
    Moderator sees highest-risk items first.
    """
    query = select(Document).where(Document.verification_status == "pending")

    if min_similarity > 0:
        query = query.where(Document.similarity_score >= min_similarity)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    rows = (await db.execute(
        query.order_by(Document.similarity_score.desc().nulls_last())
             .offset(offset).limit(limit)
    )).scalars().all()

    return DocumentListResponse(items=list(rows), total=total, page=page, limit=limit)


@router.patch("/documents/{doc_id}/verify", response_model=DocumentOut)
async def verify_document(
    doc_id: UUID,
    body: DocumentVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    if body.status not in ("verified", "rejected"):
        raise HTTPException(400, "Status must be 'verified' or 'rejected'")
    doc.verification_status = body.status
    await db.commit()
    await db.refresh(doc)
    return doc