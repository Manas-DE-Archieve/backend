from typing import List
from functools import lru_cache
import hashlib
import json
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()
_client: AsyncOpenAI | None = None

# Simple in-memory cache: hash(text) → embedding
_embedding_cache: dict[str, List[float]] = {}


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def embed_text(text: str) -> List[float]:
    """Embed a single text string, using cache."""
    key = _cache_key(text)
    if key in _embedding_cache:
        return _embedding_cache[key]
    client = _get_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text
    )
    embedding = response.data[0].embedding
    _embedding_cache[key] = embedding
    return embedding


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts in a single API call, using cache."""
    uncached_indices = []
    uncached_texts = []
    results: List[List[float] | None] = [None] * len(texts)

    for i, text in enumerate(texts):
        key = _cache_key(text)
        if key in _embedding_cache:
            results[i] = _embedding_cache[key]
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    if uncached_texts:
        client = _get_client()
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=uncached_texts
        )
        for j, embedding_obj in enumerate(response.data):
            idx = uncached_indices[j]
            emb = embedding_obj.embedding
            _embedding_cache[_cache_key(uncached_texts[j])] = emb
            results[idx] = emb

    return results  # type: ignore
