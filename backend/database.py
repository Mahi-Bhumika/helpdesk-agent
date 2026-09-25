import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Check that .env (locally) or the platform's "
        "Environment Variables (Render/Vercel) actually define it, and that the "
        "key name is exactly 'DATABASE_URL=' with no typo or missing prefix."
    )

# SQL_ECHO=true (env var) turns on verbose per-statement logging for local
# debugging. Left off by default so production logs on Render's free tier
# aren't flooded with every query.
_echo = os.getenv("SQL_ECHO", "false").lower() == "true"

engine = create_async_engine(
    DATABASE_URL,
    echo=_echo,
    connect_args={"statement_cache_size": 0},  # required: Supabase's PgBouncer pooler
                                                # doesn't support asyncpg's prepared-statement caching
    pool_pre_ping=True,   # validates a connection is still alive before handing it out —
                          # fixes the stale-idle-connection 500 found in Week 4
    pool_recycle=1800,    # belt-and-suspenders alongside pre_ping: proactively recycles
                          # connections older than 30 min rather than only checking on use
)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session