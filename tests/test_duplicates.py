import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.duplicate import find_duplicates

MOCK_EMBEDDING = [0.1] * 1536


@pytest.mark.asyncio
@patch("app.services.duplicate.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
async def test_no_duplicates_empty_db(mock_emb):
    """With empty DB, find_duplicates returns empty list."""
    db = AsyncMock()
    # Simulate empty results for both trigram and vector queries
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await find_duplicates(db, "Новый Человек")
    assert result == []


@pytest.mark.asyncio
@patch("app.services.duplicate.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
async def test_deduplication_merges_results(mock_emb):
    """Same person appearing in both trgm and vector results is deduplicated."""
    import uuid
    shared_id = uuid.uuid4()

    trgm_row = {"id": shared_id, "full_name": "Алиев Марат", "birth_year": 1900, "region": "Ош", "score": 0.85}
    vec_row = {"id": shared_id, "full_name": "Алиев Марат", "birth_year": 1900, "region": "Ош", "score": 0.90}

    db = AsyncMock()
    call_count = 0

    async def fake_execute(query, params=None):
        nonlocal call_count
        m = MagicMock()
        if call_count == 0:
            m.mappings.return_value.all.return_value = [trgm_row]
        else:
            m.mappings.return_value.all.return_value = [vec_row]
        call_count += 1
        return m

    db.execute = fake_execute

    result = await find_duplicates(db, "Алиев Марат")
    # Should be deduplicated to one entry with the higher score
    assert len(result) == 1
    assert result[0]["similarity_score"] == 0.9


@pytest.mark.asyncio
@patch("app.services.duplicate.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
async def test_threshold_respected(mock_emb):
    """Records below threshold should not be returned by trgm query."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await find_duplicates(db, "ХХХ", threshold=0.9)
    assert result == []
