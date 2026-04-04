import json
import hashlib
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.database import get_db, AsyncSessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.person import Person
from app.schemas.document import (
    DocumentOut, DocumentListResponse, DocumentDetailOut,
    DuplicateDocumentResponse, SimilarDocument
)
from app.routers.auth import get_current_user, require_role, get_optional_user
from app.models.user import User
from app.services.chunker import chunk_text, extract_pdf_text
from app.services.embedding import embed_batch, embed_text
from app.services.duplicate import find_duplicates, find_similar_documents, validate_duplicates_with_llm
from app.services.facts_generator import generate_and_save_facts
from app.config import get_settings
from openai import AsyncOpenAI

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()

# ── Thresholds ─────────────────────────────────────────────────────────────────
AUTO_REJECT_THRESHOLD  = 0.98   # ≥ 98% → auto-rejected (near-identical content only)
MODERATOR_THRESHOLD    = 0.98   # ≥ 98% → needs moderator review (same as auto-reject effectively)


async def _compute_doc_similarity(db: AsyncSession, raw_text: str) -> tuple[float | None, str | None]:
    """
    Compare uploaded document against all existing chunk embeddings.
    Returns (max_avg_score, most_similar_doc_id).
    """
    candidates = await find_similar_documents(db, raw_text, threshold=0.0, limit=1)
    if not candidates:
        return None, None
    top = candidates[0]
    return top["similarity_score"], str(top["id"])


async def _auto_extract_and_create_person(db: AsyncSession, doc: Document, raw_text: str, current_user: User | None):
    if not raw_text.strip():
        doc.status = "processed"
        return

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = f"""
    Проанализируй текст и извлеки данные о РЕПРЕССИРОВАННОМ.
    Верни ТОЛЬКО валидный JSON с ключами (если данных нет, пиши null, не придумывай):
    full_name, birth_year, death_year, region, district, occupation, charge, arrest_date (YYYY-MM-DD),
    sentence, sentence_date (YYYY-MM-DD), rehabilitation_date (YYYY-MM-DD), biography.
    Если в тексте нет явных данных о репрессированном, верни JSON с full_name: null.

    Текст документа:
    {raw_text[:4000]}
    """
    try:
        response = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        message_content = response.choices[0].message.content
        if not message_content:
            doc.status = "processed"
            return

        data = json.loads(message_content)

        if data and data.get("full_name"):
            dupes = await find_duplicates(db, data["full_name"], threshold=0.95)
            if dupes:
                print(f"INFO: Person '{data['full_name']}' skipped - duplicate found")
                doc.status = "processed"
                return

            # Convert date strings to date objects
            from datetime import date
            for date_field in ("arrest_date", "sentence_date", "rehabilitation_date"):
                val = data.get(date_field)
                if isinstance(val, str):
                    try:
                        data[date_field] = date.fromisoformat(val)
                    except (ValueError, TypeError):
                        data[date_field] = None

            embedding = await embed_text(data["full_name"])
            new_person = Person(
                **data,
                status="verified",
                document_id=doc.id,
                name_embedding=embedding,
                created_by=current_user.id if current_user else None,
                source=f"Документ: {doc.filename}"
            )
            db.add(new_person)
            doc.status = "processed"
        else:
            doc.status = "processed"
    except Exception as e:
        doc.status = "failed_extraction"
        print(f"ERROR:    Failed to extract person from '{doc.filename}': {e}")


async def _generate_facts_background(doc_id, filename: str, raw_text: str):
    try:
        async with AsyncSessionLocal() as bg_db:
            await generate_and_save_facts(bg_db, doc_id, filename, raw_text)
    except Exception as e:
        print(f"ERROR:    Background facts generation failed for '{filename}': {e}")


@router.post("/check-duplicates", response_model=DuplicateDocumentResponse)
async def check_document_duplicates(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    content = await file.read()
    filename = file.filename or "unknown"
    content_type = file.content_type or ""

    if "pdf" in content_type or filename.endswith(".pdf"):
        raw_text = extract_pdf_text(content)
    else:
        raw_text = content.decode("utf-8", errors="replace")

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    exact_q = await db.execute(select(Document).where(Document.content_hash == content_hash, Document.verification_status != "auto_rejected"))
    exact = exact_q.scalars().first()
    if exact:
        return DuplicateDocumentResponse(
            duplicates_found=True,
            message=f"Документ с идентичным содержимым уже существует: «{exact.filename}».",
            similar_documents=[
                SimilarDocument(id=exact.id, filename=exact.filename, similarity_score=1.0)
            ],
        )

    candidates = await find_similar_documents(db, raw_text, threshold=0.30, limit=3)
    if not candidates:
        return DuplicateDocumentResponse(
            duplicates_found=False,
            message="Совпадений не найдено. Документ можно загрузить.",
            similar_documents=[],
        )

    confirmed = await validate_duplicates_with_llm(raw_text, candidates)
    if confirmed:
        return DuplicateDocumentResponse(
            duplicates_found=True,
            message=f"Найдено {len(confirmed)} похожих документов.",
            similar_documents=[SimilarDocument(**s) for s in confirmed],
        )

    return DuplicateDocumentResponse(
        duplicates_found=False,
        message="Совпадений не найдено. Документ можно загрузить.",
        similar_documents=[],
    )


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    filename = file.filename or "unknown"
    content_type = file.content_type or ""

    if "pdf" in content_type or filename.endswith(".pdf"):
        raw_text = extract_pdf_text(content)
        file_type = "pdf"
    else:
        raw_text = content.decode("utf-8", errors="replace")
        file_type = "txt" if not filename.endswith(".md") else "md"

    # ── Exact duplicate check ──────────────────────────────────────────────────
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    if not force:
        existing_q = await db.execute(select(Document).where(Document.content_hash == content_hash))
        if existing_q.scalars().first():
            raise HTTPException(
                status_code=409,
                detail=f"Документ с таким же содержанием ('{filename}') уже существует в архиве."
            )

    # ── Save doc first (need id for chunks) ───────────────────────────────────
    doc = Document(
        filename=filename,
        file_type=file_type,
        raw_text=raw_text,
        content_hash=None if force else content_hash,  # skip unique constraint on force
        status="processing",
        verification_status="verified",   # will update below
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()  # get doc.id

    # ── Chunk + embed ──────────────────────────────────────────────────────────
    chunks_text = chunk_text(raw_text)
    if chunks_text:
        embeddings = await embed_batch(chunks_text)
        chunk_objects = [
            Chunk(document_id=doc.id, chunk_text=txt, chunk_index=i, embedding=emb)
            for i, (txt, emb) in enumerate(zip(chunks_text, embeddings))
        ]
        db.add_all(chunk_objects)
        await db.flush()  # chunks must be in DB before similarity query

    # ── Similarity check against existing docs ────────────────────────────────
    # Query avg chunk similarity excluding the just-uploaded doc
    from sqlalchemy import text as sa_text
    sample = raw_text[:3000].strip()
    similarity_score = None
    duplicate_of_id = None

    if sample:
        sample_embedding = await embed_text(sample)
        vec_str = "[" + ",".join(str(x) for x in sample_embedding) + "]"
        try:
            sim_result = await db.execute(
                sa_text("""
                    SELECT
                        d.id,
                        AVG(1 - (c.embedding <=> CAST(:vec AS vector))) AS avg_score
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.embedding IS NOT NULL
                      AND d.id != :doc_id
                      AND d.verification_status != 'auto_rejected'
                    GROUP BY d.id
                    ORDER BY avg_score DESC
                    LIMIT 1
                """),
                {"vec": vec_str, "doc_id": doc.id}
            )
            row = sim_result.mappings().first()
            if row:
                similarity_score = round(float(row["avg_score"]), 4)
                duplicate_of_id = row["id"]
        except Exception as e:
            print(f"WARNING: similarity check failed: {e}")

    # ── Apply thresholds ───────────────────────────────────────────────────────
    doc.similarity_score = similarity_score
    doc.duplicate_of_id = duplicate_of_id

    if similarity_score is not None and similarity_score >= AUTO_REJECT_THRESHOLD:
        # Auto-reject: block the upload entirely
        doc.verification_status = "auto_rejected"
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Документ автоматически отклонён: схожесть {round(similarity_score * 100)}% превышает порог 85%.",
                "similarity_score": similarity_score,
                "duplicate_of_id": str(duplicate_of_id) if duplicate_of_id else None,
            }
        )
    elif similarity_score is not None and similarity_score >= MODERATOR_THRESHOLD:
        # Flag for moderator review
        doc.verification_status = "pending"
    else:
        doc.verification_status = "verified"

    # ── Person extraction ──────────────────────────────────────────────────────
    await _auto_extract_and_create_person(db, doc, raw_text, current_user)

    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(_generate_facts_background, doc.id, filename, raw_text)

    return doc


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    scope: str = Query("all", enum=["all", "my"]),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: str = Query(None, description="Search by filename or content"),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user)
):
    query = select(Document).where(Document.verification_status != "auto_rejected")
    if scope == "my":
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required for this scope")
        query = query.where(Document.uploaded_by == current_user.id)
    if q and q.strip():
        search = f"%{q.strip()}%"
        query = query.where(
            Document.filename.ilike(search) | Document.raw_text.ilike(search)
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    query = query.order_by(Document.uploaded_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    return DocumentListResponse(items=list(rows), total=total, page=page, limit=limit)


@router.get("/{doc_id}", response_model=DocumentDetailOut)
async def get_document(doc_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    is_owner = doc.uploaded_by == current_user.id
    is_admin_or_mod = current_user.role in ("moderator", "super_admin")

    if not is_owner and not is_admin_or_mod:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    await db.execute(delete(Person).where(Person.document_id == doc_id))
    await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
    await db.delete(doc)
    await db.commit()