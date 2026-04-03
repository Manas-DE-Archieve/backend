from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import date
from pathlib import Path

from app.database import init_db, AsyncSessionLocal
from app.routers import auth, persons, documents, chat, admin

# CHANGE: Import all models via the __init__.py to ensure they are all
# registered with the SQLAlchemy Base before table creation.
from app.models import Person, Document, Chunk
from app.services.embedding import embed_text, embed_batch
from app.services.chunker import chunk_text
from sqlalchemy import select


async def seed_data_if_needed():
    """Заполняет БД начальными данными из seed.json, если таблица persons пуста."""
    async with AsyncSessionLocal() as db:
        # Проверяем, есть ли уже записи в таблице
        result = await db.execute(select(Person).limit(1))
        if result.first():
            return # База данных не пуста, ничего не делаем

        print("INFO:     Database is empty. Seeding initial persons...")
        try:
            with open("/app/seed.json", "r", encoding="utf-8") as f:
                persons_data = json.load(f)

            for p_data in persons_data:
                p_data.pop('id', None)  # Убираем id из json, т.к. он генерируется БД

                # Преобразуем строковые даты в объекты date
                for key in ['arrest_date', 'sentence_date', 'rehabilitation_date']:
                    if p_data.get(key):
                        p_data[key] = date.fromisoformat(p_data[key])
                    else:
                        p_data[key] = None  # Явно устанавливаем None для пустых значений

                embedding = await embed_text(p_data["full_name"])
                # Убедимся что document_id не вызовет ошибку, т.к. его нет в seed.json
                person = Person(**p_data, name_embedding=embedding, document_id=None)
                db.add(person)

            await db.commit()
            print(f"INFO:     Seeded {len(persons_data)} persons.")
        except Exception as e:
            print(f"ERROR:    Failed to seed persons data: {e}")
            await db.rollback()

async def seed_documents_if_needed():
    """Заполняет БД начальными документами, если таблица documents пуста."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).limit(1))
        if result.first():
            return  # Документы уже есть

        print("INFO:     Documents table is empty. Seeding initial documents...")
        docs_path = Path("/app/test_documents")
        
        if not docs_path.exists():
            print(f"WARNING:  Directory not found: {docs_path.resolve()}, skipping document seeding.")
            return

        files_to_seed = list(docs_path.glob("*.txt"))
        if not files_to_seed:
            print(f"INFO:     No documents to seed in {docs_path.resolve()}.")
            return
            
        try:
            for file_path in files_to_seed:
                content = file_path.read_text(encoding="utf-8")
                filename = file_path.name

                doc = Document(
                    filename=filename,
                    file_type="txt",
                    raw_text=content,
                    uploaded_by=None,
                    status="processed" # Ставим статус, так как для них не запускается AI-экстракция
                )
                db.add(doc)
                await db.flush()  # get doc.id

                chunks_text = chunk_text(content)
                if not chunks_text:
                    continue

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
            print(f"INFO:     Seeded {len(files_to_seed)} documents.")
        except Exception as e:
            print(f"ERROR:    Failed to seed documents: {e}")
            await db.rollback()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and extensions on startup
    await init_db()
    await seed_data_if_needed()
    await seed_documents_if_needed()
    yield


app = FastAPI(
    title="Архивдин Үнү API",
    description="Digital archive of repressed people (1918–1953) with RAG assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(persons.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}