#!/usr/bin/env python3
"""
Backfill script: generate facts for all documents that don't have any yet.
Run once:  python scripts/generate_facts.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import AsyncSessionLocal, init_db
from app.models.document import Document
from app.models.fact import Fact
from app.services.facts_generator import generate_and_save_facts


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Find documents with no facts
        docs_result = await db.execute(
            select(Document).where(
                Document.raw_text.isnot(None),
                ~Document.id.in_(select(Fact.document_id).where(Fact.document_id.isnot(None)))
            )
        )
        docs = docs_result.scalars().all()
        print(f"Found {len(docs)} documents without facts.")

        total = 0
        for doc in docs:
            facts = await generate_and_save_facts(db, doc.id, doc.filename, doc.raw_text or "")
            total += len(facts)
            print(f"  [{doc.filename}] → {len(facts)} facts")

        print(f"\nDone. Generated {total} facts total.")


if __name__ == "__main__":
    asyncio.run(main())