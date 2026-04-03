import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from openai import AsyncOpenAI

from app.database import get_db
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.person import Person
from app.schemas.document import DocumentOut, DocumentListResponse, DocumentDetailOut
from app.routers.auth import get_current_user, require_role, get_optional_user
from app.models.user import User
from app.services.chunker import chunk_text, extract_pdf_text
from app.services.embedding import embed_batch, embed_text
from app.services.duplicate import find_duplicates
from app.config import get_settings

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()


async def _auto_extract_and_create_person(db: AsyncSession, doc: Document, raw_text: str, current_user: User | None):
    """
    Tries to extract person data from text using an LLM and creates a new Person record.
    Updates the document status based on the outcome.
    """
    if not raw_text.strip():
        doc.status = "processed"  # No text to process, but not an error
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
        data = json.loads(response.choices[0].message.content)

        if data and data.get("full_name"):
            # A person was found, check for duplicates before creating
            dupes = await find_duplicates(db, data["full_name"], threshold=0.7)
            if dupes:
                print(f"INFO:     Duplicate found for '{data['full_name']}' from doc '{doc.filename}'. Skipping person creation.")
                doc.status = "processed" # Processed, but person not added due to duplication
                return

            embedding = await embed_text(data["full_name"])
            new_person = Person(
                **data,
                document_id=doc.id,
                name_embedding=embedding,
                created_by=current_user.id if current_user else None,
                source=f"Документ: {doc.filename}"
            )
            db.add(new_person)
            doc.status = "processed"
            print(f"INFO:     Successfully extracted and created person '{data['full_name']}' from '{doc.filename}'.")
        else:
            doc.status = "processed" # No person found, but processing was successful
    except Exception as e:
        doc.status = "failed_extraction"
        print(f"ERROR:    Failed to extract person from '{doc.filename}': {e}")


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
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

    doc = Document(
        filename=filename,
        file_type=file_type,
        raw_text=raw_text,
        status="processing",
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()

    # --- NEW: Auto-create person from document text ---
    await _auto_extract_and_create_person(db, doc, raw_text, current_user)
    # --- END NEW ---

    chunks_text = chunk_text(raw_text)
    if chunks_text:
        embeddings = await embed_batch(chunks_text)
        chunk_objects = [
            Chunk(document_id=doc.id, chunk_text=txt, chunk_index=i, embedding=emb)
            for i, (txt, emb) in enumerate(zip(chunks_text, embeddings))
        ]
        db.add_all(chunk_objects)

    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    scope: str = Query("all", enum=["all", "my"]),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user)
):
    query = select(Document)
    if scope == "my":
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required for this scope")
        query = query.where(Document.uploaded_by == current_user.id)

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
    current_user: User = Depends(require_role("moderator", "super_admin")),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # Also delete any person associated with this document
    await db.execute(delete(Person).where(Person.document_id == doc_id))
    await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
    await db.delete(doc)
    await db.commit()