from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.models.document import Document
from app.models.chunk import Chunk
from app.schemas.document import DocumentOut
from app.routers.auth import get_current_user, require_role
from app.models.user import User
from app.services.chunker import chunk_text, extract_pdf_text
from app.services.embedding import embed_batch

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    filename = file.filename or "unknown"
    content_type = file.content_type or ""

    # Detect type and extract text
    if "pdf" in content_type or filename.endswith(".pdf"):
        raw_text = extract_pdf_text(content)
        file_type = "pdf"
    elif filename.endswith(".md"):
        raw_text = content.decode("utf-8", errors="replace")
        file_type = "md"
    else:
        raw_text = content.decode("utf-8", errors="replace")
        file_type = "txt"

    doc = Document(
        filename=filename,
        file_type=file_type,
        raw_text=raw_text,
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()  # get doc.id before commit

    # Chunk the text
    chunks_text = chunk_text(raw_text)
    if not chunks_text:
        raise HTTPException(400, "Document is empty")

    # Batch embed all chunks in a single API call
    embeddings = await embed_batch(chunks_text)

    chunk_objects = [
        Chunk(
            document_id=doc.id,
            chunk_text=chunks_text[i],
            chunk_index=i,
            embedding=embeddings[i],
        )
        for i in range(len(chunks_text))
    ]
    db.add_all(chunk_objects)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.uploaded_at.desc()))
    return result.scalars().all()


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("moderator", "admin")),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
    await db.delete(doc)
    await db.commit()
