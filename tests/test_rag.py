import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
@patch("app.services.rag.embed_text", new_callable=AsyncMock, return_value=[0.0] * 1536)
async def test_retrieve_chunks_returns_list(mock_emb):
    from app.services.rag import retrieve_chunks

    row = {
        "id": "chunk-uuid",
        "chunk_text": "Тестовый фрагмент документа",
        "filename": "test.txt",
        "score": 0.88,
    }
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row]
    db.execute = AsyncMock(return_value=mock_result)

    chunks = await retrieve_chunks(db, "тестовый вопрос", top_k=3)
    assert len(chunks) == 1
    assert chunks[0]["document_name"] == "test.txt"
    assert chunks[0]["score"] == 0.88


@pytest.mark.asyncio
@patch("app.services.rag.embed_text", new_callable=AsyncMock, return_value=[0.0] * 1536)
async def test_retrieve_chunks_empty(mock_emb):
    from app.services.rag import retrieve_chunks

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    chunks = await retrieve_chunks(db, "вопрос без ответа")
    assert chunks == []


@pytest.mark.asyncio
@patch("app.services.rag.embed_text", new_callable=AsyncMock, return_value=[0.0] * 1536)
@patch("app.services.rag.AsyncOpenAI")
async def test_stream_rag_answer_yields_sources_and_done(mock_openai_cls, mock_emb):
    from app.services.rag import stream_rag_answer

    # Mock chunk retrieval
    row = {"id": "c1", "chunk_text": "Архивный текст", "filename": "doc.txt", "score": 0.9}
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row]
    db.execute = AsyncMock(return_value=mock_result)

    # Mock streaming response
    async def fake_stream_context():
        mock_stream = MagicMock()

        async def aiter():
            event = MagicMock()
            event.choices = [MagicMock()]
            event.choices[0].delta.content = "Ответ"
            yield event

        mock_stream.__aiter__ = lambda self: aiter()
        return mock_stream

    mock_client = MagicMock()
    mock_client.chat.completions.stream.return_value.__aenter__ = AsyncMock(return_value=fake_stream_context())
    mock_client.chat.completions.stream.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_openai_cls.return_value = mock_client

    events = []
    async for line in stream_rag_answer(db, "Вопрос", []):
        events.append(line)

    types = [__import__("json").loads(e[6:])["type"] for e in events if e.startswith("data:")]
    assert "sources" in types
    assert "done" in types
