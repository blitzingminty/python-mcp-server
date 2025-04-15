# src/database.py

import logging # Add logging import
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event # <--- Import event listener
from sqlalchemy.engine import Engine # <--- Import Engine for type hinting
from .config import settings # Import settings from config.py

logger = logging.getLogger(__name__) # <--- Add logger

logger.info(f"DATABASE_URL from settings: {settings.DATABASE_URL}")

# Create an asynchronous engine instance based on the DATABASE_URL from settings
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development", # Log SQL queries in development
    future=True
)

# --- Add SQLite PRAGMA enforcement ---
# This is crucial for ON DELETE CASCADE to work with SQLite
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Execute PRAGMA foreign_keys=ON for SQLite connections."""
    # Check if the driver is SQLite
    if engine.dialect.name == "sqlite":
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()
            logger.debug("PRAGMA foreign_keys=ON executed for new SQLite connection.")
        except Exception as e:
            # Log error if PRAGMA execution fails
            logger.error(f"Failed to execute PRAGMA foreign_keys=ON: {e}", exc_info=True)
    # For other database types, this listener does nothing

# --- End SQLite PRAGMA enforcement ---


# Create an asynchronous session factory
AsyncSessionFactory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for declarative models
Base = declarative_base()

# --- Dependency for FastAPI (keep as is) ---
async def get_db_session() -> AsyncSession:
    """
    FastAPI dependency that yields an async database session.
    Ensures the session is closed even if errors occur.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            pass # Session closed automatically by context manager

# --- Optional: Function to initialize database (keep as is) ---
async def init_db():
    """
    Initializes the database by creating all tables defined by models
    inheriting from Base. Use with caution, consider Alembic for production.
    """
    async with engine.begin() as conn:
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
    