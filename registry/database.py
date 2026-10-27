import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# In Docker, we connect to the 'postgres' container via internal DNS
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://blastuser:blastpass@postgres:5432/blastradius")

# echo=True prints the generated SQL to the terminal. Great for debugging, disable in prod.
engine = create_async_engine(DATABASE_URL, echo=True)

# AsyncSessionMaker generates new database sessions for our API endpoints
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    """Dependency injection for FastAPI endpoints to get a database session."""
    async with AsyncSessionLocal() as session:
        yield session