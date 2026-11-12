from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_db_engine(db_url: str | None = None) -> AsyncEngine:
    url = db_url or get_settings().ai_db_url
    return create_async_engine(url, echo=False, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create ai-db tables if they do not exist."""
    import db.models  # noqa: F401 - register SQLModel metadata tables

    target_engine = engine or get_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def dispose_db() -> None:
    """Dispose the shared database engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session

