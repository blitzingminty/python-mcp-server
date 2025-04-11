# src/database.py
# Placeholder for database.py logic

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings # Import settings from config.py

# Create an asynchronous engine instance based on the DATABASE_URL from settings
# Using future=True enables modern SQLAlchemy 2.0 features
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development", # Log SQL queries in development
    future=True
)

# Create an asynchronous session factory
# expire_on_commit=False prevents attributes from expiring after commit,
# useful in async contexts and with FastAPI dependencies.
AsyncSessionFactory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for declarative models
# All your database models will inherit from this class
Base = declarative_base()

# --- Dependency for FastAPI ---
async def get_db_session() -> AsyncSession:
    """
    FastAPI dependency that yields an async database session.
    Ensures the session is closed even if errors occur.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            # Optionally commit here if you want auto-commit behavior
            # await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # No explicit close needed for async context manager `async with`
            pass

# --- Optional: Function to initialize database (create tables) ---
# You might use Alembic for migrations instead for more complex setups
async def init_db():
    """
    Initializes the database by creating all tables defined by models
    inheriting from Base. Use with caution, consider Alembic for production.
    """
    async with engine.begin() as conn:
        # Drop all tables (useful for quick resets in dev, DANGEROUS otherwise)
        # await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables initialized (if not already existing).")

# --- Example Usage (can remove later) ---
if __name__ == "__main__":
    import asyncio

    async def main():
        # Example: Initialize DB (use cautiously)
        # await init_db()

        # Example: Get a session
        async for session in get_db_session():
            print("Successfully obtained DB session.")
            # You could perform queries here, e.g.:
            # result = await session.execute(select(YourModel))
            # items = result.scalars().all()
            print("DB session closed.")
            break # Exit after one iteration for this example

    asyncio.run(main())
    