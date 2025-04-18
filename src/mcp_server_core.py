# src/mcp_server_core.py
# Contains the core FastMCP instance, lifespan management, and session helper.

import logging
from typing import Any, Dict, AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI # Added FastAPI import

# --- SQLAlchemy Imports ---
from sqlalchemy.ext.asyncio import AsyncSession

# --- SDK Imports ---
try:
    from mcp.server.fastmcp import FastMCP, Context
except ImportError as e:
    logging.critical(
        f"Failed to import from mcp.server.fastmcp: {e}. Please ensure 'mcp[cli]' is installed correctly.")
    raise

# --- Project Imports ---
from .config import settings
from .database import AsyncSessionFactory, Base, engine # Import necessary DB components

logger = logging.getLogger(__name__)


# --- Lifespan Management for Database ---

@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[Dict[str, Any]]: # Changed server: FastMCP to app: FastAPI
    """
    Manage application lifecycle, providing database access and ensuring tables exist.
    Provides the AsyncSessionFactory via context.
    """
    logger.info("Application lifespan startup...")
    # --- Ensure tables are created ---
    try:
        async with engine.begin() as conn:
            logger.info(
                "Initializing database tables (if they don't exist)...")
            # Create tables based on models.py
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialization check complete.")
    except Exception as e:
        logger.critical(
            f"Database table initialization failed during lifespan startup: {e}", exc_info=True)
        # Decide whether to raise the error or yield anyway
        # raise # Option 1: Stop server startup if DB init fails
        # Option 2: Log error and continue (server might fail later)

    # Provide the session factory in the context
    context_data = {"db_session_factory": AsyncSessionFactory}
    try:
        yield context_data
    finally:
        logger.info("Application lifespan shutdown.")
        # Optional: Dispose engine if appropriate for your app lifecycle
        # await engine.dispose()


# --- Create the FastMCP Instance ---
# Pass the lifespan manager to the constructor
mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=app_lifespan
)
logger.info(
    f"FastMCP instance created with lifespan: {settings.MCP_SERVER_NAME} v{settings.VERSION}")


# --- Helper to get session from context ---
from typing import Any
...
async def get_session(ctx: Context[Any, Any]) -> AsyncSession:
    """Gets an async session from the lifespan context."""
    try:
        session_factory = ctx.request_context.lifespan_context["db_session_factory"]
        return session_factory()
    except KeyError:
        logger.error("Database session factory not found in lifespan context.")
        # Depending on MCP SDK, raise a specific MCPError or standard exception
        raise RuntimeError(
            "Server configuration error: DB Session Factory missing.")
    except AttributeError:
        logger.error(
            "Context structure unexpected. Cannot find lifespan context or session factory.")
        raise RuntimeError(
            "Server configuration error: Context structure invalid.")

# NOTE: Tool definitions will be imported elsewhere (e.g., in main.py or at the end of this file if preferred)
# to ensure they are registered with this mcp_instance.
