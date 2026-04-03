from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.embedding import embed_text


async def find_duplicates(
    db: AsyncSession, full_name: str, threshold: float = 0.4, limit: int = 5
) -> List[dict]:
    """
    Two-phase duplicate detection:
    1. Fuzzy name match via pg_trgm (fast)
    2. Semantic similarity via pgvector (precise)
    Returns merged, deduplicated list ranked by best score.
    """
    # Phase 1: trigram similarity
    trgm_result = await db.execute(
        text("""
            SELECT id, full_name, birth_year, region,
                   similarity(full_name, :name) AS score
            FROM persons
            WHERE similarity(full_name, :name) > :threshold
            ORDER BY score DESC
            LIMIT :limit
        """),
        {"name": full_name, "threshold": threshold, "limit": limit}
    )
    trgm_rows = trgm_result.mappings().all()

    # Phase 2: vector similarity
    name_embedding = await embed_text(full_name)
    vec_str = "[" + ",".join(str(v) for v in name_embedding) + "]"
    vec_result = await db.execute(
        text("""
            SELECT id, full_name, birth_year, region,
                   1 - (name_embedding <=> :vec::vector) AS score
            FROM persons
            WHERE name_embedding IS NOT NULL
            ORDER BY name_embedding <=> :vec::vector
            LIMIT :limit
        """),
        {"vec": vec_str, "limit": limit}
    )
    vec_rows = vec_result.mappings().all()

    # Merge and deduplicate, keeping the highest score per id
    merged: dict[str, dict] = {}
    for row in list(trgm_rows) + list(vec_rows):
        pid = str(row["id"])
        score = float(row["score"])
        if pid not in merged or merged[pid]["similarity_score"] < score:
            merged[pid] = {
                "id": row["id"],
                "full_name": row["full_name"],
                "birth_year": row["birth_year"],
                "region": row["region"],
                "similarity_score": round(score, 4),
            }

    candidates = sorted(merged.values(), key=lambda x: x["similarity_score"], reverse=True)
    return candidates[:limit]
