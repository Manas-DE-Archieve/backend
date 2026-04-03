from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, engine
from app.routers import auth, persons, documents, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and extensions on startup
    await init_db()
    yield


app = FastAPI(
    title="Архивдин Үнү API",
    description="Digital archive of repressed people (1918–1953) with RAG assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(persons.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
