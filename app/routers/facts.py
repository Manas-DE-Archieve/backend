from uuid import UUID
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database import get_db, AsyncSessionLocal
from app.models.fact import Fact
from app.models.document import Document
from app.services.facts_generator import generate_and_save_facts
from app.routers.auth import get_current_user, require_role
from app.models.user import User
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/api/facts", tags=["facts"])


class FactOut(BaseModel):
    id: UUID
    document_id: Optional[UUID] = None
    source_filename: Optional[str] = None
    icon: Optional[str] = None
    category: Optional[str] = None
    title: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class FactsResponse(BaseModel):
    items: List[FactOut]
    total: int
    remaining: int  # unseen facts count after this batch


@router.get("", response_model=FactsResponse)
async def get_facts(
    limit: int = Query(6, ge=1, le=20),
    seen_ids: str = Query("", description="Comma-separated UUIDs already seen"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns `limit` unseen facts in random order.
    Client passes seen_ids to exclude already-shown facts.
    When all are seen, returns empty list with remaining=0.
    """
    total = (await db.execute(select(func.count()).select_from(Fact))).scalar_one()

    exclude: List[UUID] = []
    if seen_ids.strip():
        for s in seen_ids.split(","):
            try:
                exclude.append(UUID(s.strip()))
            except ValueError:
                pass

    query = select(Fact)
    if exclude:
        query = query.where(Fact.id.notin_(exclude))

    # Random order via PostgreSQL RANDOM()
    query = query.order_by(text("RANDOM()")).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    unseen_count_q = select(func.count()).select_from(Fact)
    if exclude:
        unseen_count_q = unseen_count_q.where(Fact.id.notin_(exclude))
    unseen_total = (await db.execute(unseen_count_q)).scalar_one()
    remaining = max(0, unseen_total - len(rows))

    return FactsResponse(items=list(rows), total=total, remaining=remaining)


@router.post("/generate", status_code=202)
async def trigger_facts_generation(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role(["moderator", "super_admin"])),
):
    """
    Trigger background generation of facts for all documents that don't have any yet.
    Returns immediately; generation runs in the background.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            docs_result = await db.execute(
                select(Document).where(
                    Document.raw_text.isnot(None),
                    ~Document.id.in_(
                        select(Fact.document_id).where(Fact.document_id.isnot(None))
                    )
                )
            )
            docs = docs_result.scalars().all()
            print(f"INFO: Generating facts for {len(docs)} documents...")
            for doc in docs:
                await generate_and_save_facts(db, doc.id, doc.filename, doc.raw_text or "")

    background_tasks.add_task(_run)
    return {"message": "Генерация запущена в фоне"}