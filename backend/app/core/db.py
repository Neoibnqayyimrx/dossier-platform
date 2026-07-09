from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# psycopg's async driver; the sync "postgresql+psycopg://" URL from Settings
# still works because SQLAlchemy's async engine talks to it via psycopg's
# AsyncConnection under the hood — we just need the driver installed.
engine = create_async_engine(settings.database_url, echo=settings.app_env == "dev")

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields one session per request, closed afterwards.

    The `yield` (instead of `return`) makes this an async generator — FastAPI
    runs everything before `yield` as setup, hands the session to the route,
    then resumes after the route returns to run cleanup (session close).
    """
    async with async_session_factory() as session:
        yield session
