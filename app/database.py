from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        # Create all new tables
        await conn.run_sync(Base.metadata.create_all)

        # Auto-migrate existing tables (safe to run multiple times)
        migrations = [
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_content_hash
               ON documents(content_hash) WHERE content_hash IS NOT NULL""",
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title TEXT",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                print(f"WARNING: migration skipped: {e}")