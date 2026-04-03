from typing import List, AsyncIterator
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from openai import AsyncOpenAI
from app.config import get_settings
from app.services.embedding import embed_text

settings = get_settings()

SYSTEM_PROMPT_TEMPLATE = """Ты — архивный ИИ-ассистент проекта «Архивдин Үнү» (Голос из архива).
Ты помогаешь исследователям работать с документами об жертвах репрессий 1918–1953 годов.
Отвечай ТОЛЬКО на основе предоставленных документов.
Если ответа нет в документах — честно скажи об этом.
Не придумывай факты. Цитируй источники.

КОНТЕКСТ ИЗ ДОКУМЕНТОВ:
{context}"""


async def retrieve_chunks(db: AsyncSession, question: str, top_k: int = 3) -> List[dict]:
    """Vector similarity search for relevant document chunks."""
    embedding = await embed_text(question)
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

    result = await db.execute(
        text("""
            SELECT c.id, c.chunk_text, d.filename,
                   1 - (c.embedding <=> CAST(:vec AS vector)) AS score
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:vec AS vector)
            LIMIT :top_k
        """),
        {"vec": vec_str, "top_k": top_k}
    )
    rows = result.mappings().all()
    return [
        {
            "chunk_id": str(row["id"]),
            "document_name": row["filename"],
            "chunk_text": row["chunk_text"],
            "score": round(float(row["score"]), 4),
        }
        for row in rows
    ]


async def stream_rag_answer(
    db: AsyncSession,
    question: str,
    history: List[dict],
    top_k: int | None = None,
) -> AsyncIterator[str]:
    """
    Yields SSE-formatted lines.
    Events: sources → token (multiple) → done
    """
    top_k = top_k or settings.top_k_chunks
    chunks = await retrieve_chunks(db, question, top_k)

    # Emit sources first
    yield f"data: {json.dumps({'type': 'sources', 'data': chunks})}\n\n"

    context = "\n\n---\n\n".join(c["chunk_text"] for c in chunks)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-10:],
        {"role": "user", "content": question},
    ]

    stream = await client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield f"data: {json.dumps({'type': 'token', 'data': delta})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
