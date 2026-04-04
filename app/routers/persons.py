import json
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from openai import AsyncOpenAI

from app.database import get_db
from app.models.person import Person
from app.schemas.person import (
    PersonCreate, PersonUpdate, PersonOut, PersonStatusUpdate,
    PersonListResponse, DuplicateCheckResponse, SimilarPerson
)
from app.routers.auth import get_current_user, require_role
from app.models.user import User
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.duplicate import find_duplicates
from app.services.embedding import embed_text
from app.services.chunker import extract_pdf_text
from app.config import get_settings

router = APIRouter(prefix="/api/persons", tags=["persons"])
settings = get_settings()

# --- НОВАЯ KILLER FEATURE: AI-Экстракция ---
@router.post("/extract", status_code=200)
async def auto_extract_person_data(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Анализирует документ (PDF/Скан/Текст) и извлекает данные о репрессированном в формате JSON."""
    content = await file.read()
    filename = file.filename.lower() if file.filename else ""
    
    # 1. Читаем текст (сработает и OCR для сканов!)
    if filename.endswith(".pdf"):
        raw_text = extract_pdf_text(content)
    else:
        raw_text = content.decode("utf-8", errors="replace")

    if not raw_text.strip():
        raise HTTPException(400, "Не удалось распознать текст на документе")

    # 2. Отправляем в OpenAI с жестким форматом JSON
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    prompt = f"""
    Ты - опытный архивариус. Проанализируй исторический документ и извлеки данные о репрессированном.
    Верни ТОЛЬКО валидный JSON со следующими ключами (если данных нет, пиши null, не придумывай):
    - full_name (строка, ФИО полностью)
    - birth_year (целое число или null)
    - death_year (целое число или null)
    - region (строка: Чуйская область, Ошская область и т.д.)
    - district (строка, район или город)
    - occupation (строка, профессия)
    - charge (строка, например '58-10')
    - arrest_date (строка в формате YYYY-MM-DD)
    - sentence (строка, приговор)
    - sentence_date (строка в формате YYYY-MM-DD)
    - rehabilitation_date (строка в формате YYYY-MM-DD)
    - biography (строка, краткая суть дела на 2-3 предложения)

    Текст документа:
    {raw_text[:4000]}
    """

    try:
        response = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} # Заставляем ИИ вернуть идеальный JSON
        )
        extracted_data = json.loads(response.choices[0].message.content)
        return extracted_data
    except Exception as e:
        raise HTTPException(500, f"Ошибка ИИ: {str(e)}")

# --- СТАРЫЕ ЭНДПОИНТЫ ---

@router.get("/stats/summary")
async def get_summary_stats(db: AsyncSession = Depends(get_db)):
    """Single-query aggregate stats for the homepage."""
    result = await db.execute(text("""
        SELECT
            COUNT(*)                                            AS total,
            COUNT(*) FILTER (WHERE sentence ILIKE '%расстрел%') AS executed,
            COUNT(*) FILTER (WHERE rehabilitation_date IS NOT NULL) AS rehabilitated,
            COUNT(DISTINCT region) FILTER (WHERE region IS NOT NULL) AS regions
        FROM persons
        WHERE status = 'verified'
    """))
    row = result.mappings().first()
    return {
        "total":         int(row["total"]),
        "executed":      int(row["executed"]),
        "rehabilitated": int(row["rehabilitated"]),
        "regions":       int(row["regions"]),
    }


@router.get("/stats/regions")
async def get_region_stats(db: AsyncSession = Depends(get_db)):
    """Returns count of repressed persons per region — used for the map."""
    result = await db.execute(
        select(Person.region, func.count(Person.id).label("count"))
        .where(Person.region.isnot(None))
        .group_by(Person.region)
        .order_by(func.count(Person.id).desc())
    )
    rows = result.all()
    return {
        "regions": [{"region": r.region, "count": r.count} for r in rows],
        "total": sum(r.count for r in rows),
    }


@router.get("", response_model=PersonListResponse)
async def list_persons(
    q: Optional[str] = None,
    region: Optional[str] = None,
    charge: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    # If charge query — use semantic vector search through chunks
    semantic_doc_ids: list | None = None
    if charge and charge.strip():
        try:
            vec = await embed_text(charge.strip())
            vec_str = "[" + ",".join(str(x) for x in vec) + "]"
            sim_result = await db.execute(text("""
                SELECT DISTINCT d.id
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                  AND (1 - (c.embedding <=> CAST(:vec AS vector))) > 0.3
                ORDER BY d.id
                LIMIT 200
            """), {"vec": vec_str})
            semantic_doc_ids = [row[0] for row in sim_result.fetchall()]
        except Exception as e:
            print(f"WARNING: semantic search failed: {e}")

    query = select(Person)

    if q:
        query = query.where(
            text("similarity(full_name, :q) > 0.1").bindparams(q=q)
        ).order_by(text("similarity(full_name, :q2) DESC").bindparams(q2=q))

    if semantic_doc_ids is not None:
        if semantic_doc_ids:
            query = query.where(Person.document_id.in_(semantic_doc_ids))
        else:
            # No semantic matches — also try ILIKE fallback on charge field
            query = query.where(Person.charge.ilike(f"%{charge}%"))

    if region:
        query = query.where(Person.region == region)
    if year_from:
        query = query.where(Person.birth_year >= year_from)
    if year_to:
        query = query.where(Person.birth_year <= year_to)
    if status:
        query = query.where(Person.status == status)
    else:
        query = query.where(Person.status == "verified")

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    return PersonListResponse(items=list(rows), total=total, page=page, limit=limit)


@router.post("", response_model=PersonOut | DuplicateCheckResponse, status_code=201)
async def create_person(
    body: PersonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not body.force:
        dupes = await find_duplicates(db, body.full_name)
        if dupes:
            similar = [SimilarPerson(**d) for d in dupes]
            return DuplicateCheckResponse(
                duplicates_found=True,
                similar_persons=similar,
                message="Найдены похожие записи. Продолжить сохранение?"
            )

    embedding = await embed_text(body.full_name)

    person = Person(
        **body.model_dump(exclude={"force"}),
        name_embedding=embedding,
        created_by=current_user.id,
    )
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.get("/{person_id}", response_model=PersonOut)
async def get_person(person_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Person not found")
    return person


@router.put("/{person_id}", response_model=PersonOut)
async def update_person(
    person_id: UUID,
    body: PersonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Person not found")

    if current_user.role not in ("moderator", "super_admin") and person.created_by != current_user.id:
        raise HTTPException(403, "Forbidden")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(person, field, value)

    if body.full_name:
        person.name_embedding = await embed_text(body.full_name)

    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=204)
async def delete_person(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Person not found")
    await db.delete(person)
    await db.commit()


@router.patch("/{person_id}/status", response_model=PersonOut)
async def update_status(
    person_id: UUID,
    body: PersonStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Person not found")
    if body.status not in ("pending", "verified", "rejected"):
        raise HTTPException(400, "Invalid status")
    person.status = body.status
    await db.commit()
    await db.refresh(person)
    return person