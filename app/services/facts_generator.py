"""
Generates 0–3 historical facts from a document's text and saves them to the DB.
Used both during upload and by the backfill script.
"""
import json
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import AsyncOpenAI
from app.config import get_settings
from app.models.fact import Fact

settings = get_settings()


async def generate_and_save_facts(
    db: AsyncSession,
    document_id,
    filename: str,
    raw_text: str,
) -> List[Fact]:
    """Generate 0–3 facts from document text and persist them. Idempotent."""

    # Skip if facts already exist for this document
    existing = await db.execute(
        select(Fact).where(Fact.document_id == document_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return []

    snippet = raw_text[:3000].strip()
    if not snippet:
        return []

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = f"""Ты — главный редактор исторического журнала. Твоя задача — найти в архивном документе 1-3 факта, которые ПОРАЖАЮТ воображение или заставляют задуматься.

Избегай сухой статистики типа "в списке 20 человек".
Ищи:
1. Трагедию: (Например, арест в день рождения или арест целой семьи).
2. Абсурд: (Например, обвинение в шпионаже простого пастуха за радиоприемник).
3. Масштаб: (Например, "Черный февраль 1938 года — в этом списке 90% приговорены к высшей мере за одну неделю").
4. Социальный срез: (Кого именно забирали? Учителей, кузнецов, 80-летних стариков?)

Документ: {filename}
Текст: {snippet}

Верни JSON:
{{
  "facts": [
    {{
      "icon": "🎭", 
      "category": "ПАРАДОКС / ТРАГЕДИЯ / МАСШТАБ",
      "title": "Цепляющий заголовок",
      "body": "Эмоциональное, но исторически точное описание."
    }}
  ]
}}
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini", # Рекомендую явно поставить эту модель для надежности
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        
        # Достаем список из ключа 'facts' или ищем любой первый попавшийся список в словаре
        arr = parsed.get("facts", [])
        if not arr and isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    arr = v
                    break
    except Exception as e:
        print(f"WARNING: facts generation failed for '{filename}': {e}")
        return []

    facts = []
    for item in arr[:3]:
        if not item.get("title") or not item.get("body"):
            continue
        fact = Fact(
            document_id=document_id,
            source_filename=filename,
            icon=item.get("icon", "📖"),
            category=item.get("category", "История"),
            title=item["title"],
            body=item["body"],
        )
        db.add(fact)
        facts.append(fact)

    if facts:
        await db.commit()
        print(f"INFO:     Generated {len(facts)} facts from '{filename}'")

    return facts