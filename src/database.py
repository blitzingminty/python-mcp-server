# src/database.py

import logging
from typing import AsyncGenerator # Use AsyncGenerator for dependency typing
from fastapi import Request # Import Request for dependency injection

# --- REMOVED create_async_engine, sessionmaker FROM HERE ---
# --- They are now created dynamically in the lifespan manager ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import event
from sqlalchemy.engine import Engine # Keep for type hinting if needed elsewhere

from .config import settings # Import settings from config.py

logger = logging.getLogger(__name__)

# --- REMOVED MODULE-LEVEL DEBUG LOG ---
# logger.info(f"DATABASE_URL from settings: {settings.DATABASE_URL}")

# --- REMOVED MODULE-LEVEL ENGINE CREATION ---
# engine = create_async_engine(...)

# Base class for declarative models - REMAINS HERE
Base = declarative_base()

# --- SQLite PRAGMA enforcement - REMAINS HERE ---
# This function will be attached to the engine instance inside the lifespan manager
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Execute PRAGMA foreign_keys=ON for SQLite connections."""
    # Check if the database driver is SQLite
    # We don't have 'engine' globally anymore, so we check the dialect name from the connection's engine
    # However, a more robust way is to check the dbapi_connection type if possible,
    # or rely on the lifespan manager attaching this only if it creates an SQLite engine.
    # Let's assume the lifespan attaches it correctly.
    # A simpler check might involve checking the dbapi_connection class name.
    driver_name = dbapi_connection.__class__.__module__.split('.')[0] # e.g., 'sqlite3' or 'psycopg2'
    if driver_name == 'sqlite3':
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()
            logger.debug("PRAGMA foreign_keys=ON executed for new SQLite connection.")
        except Exception as e:
            # Log error if PRAGMA execution fails
            logger.error(f"Failed to execute PRAGMA foreign_keys=ON: {e}", exc_info=True)

# --- REMOVED MODULE-LEVEL SESSION FACTORY CREATION ---
# AsyncSessionFactory = sessionmaker(...)

# --- MODIFIED Dependency for FastAPI ---
# It now gets the factory from app.state
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session obtained from
    the factory stored in the application state during lifespan startup.
    Ensures the session is closed even if errors occur.
    """
    session_factory = getattr(request.app.state, 'db_session_factory', None)
    if not session_factory:
        logger.critical("Database session factory not found in application state! Lifespan likely failed.")
        # Depending on desired behavior, you might raise an HTTP exception here
        raise RuntimeError("Database is not configured. Check server logs.") # Or HTTPException

    async with session_factory() as session:
        try:
            yield session
        except Exception:
            logger.error("Rolling back database session due to exception.", exc_info=True)
            await session.rollback()
            raise
        finally:
            # Session is automatically closed by the async context manager 'async with'
            pass

# --- REMOVED Optional init_db() function ---
# This logic is now handled by the lifespan manager.

# --- REMOVED __main__ example block ---