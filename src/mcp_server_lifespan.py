import logging
from typing import Any, Dict, AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .database import AsyncSessionFactory, Base, engine
from .config import settings

logger = logging.getLogger(__name__)

from fastapi import FastAPI

@asynccontextmanager
async def fastapi_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI-compatible lifespan function.
    Initializes database tables and stores session factory in app.state.
    """
    logger.info("FastAPI lifespan startup...")
    try:
        async with engine.begin() as conn:
            logger.info("Initializing database tables (if they don't exist)...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialization check complete.")
    except Exception as e:
        logger.critical(
            f"Database table initialization failed during FastAPI lifespan startup: {e}", exc_info=True)
    app.state.db_session_factory = AsyncSessionFactory
    yield
    logger.info("FastAPI lifespan shutdown.")

@asynccontextmanager
async def mcp_lifespan(server: Any) -> AsyncIterator[Dict[str, Any]]:
    """
    MCP server lifespan function.
    Provides db_session_factory in context.
    """
    logger.info("MCP lifespan startup...")
    context_data = {"db_session_factory": AsyncSessionFactory}
    yield context_data
    logger.info("MCP lifespan shutdown.")

mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=mcp_lifespan
)

logger.info(
    f"FastMCP instance created with lifespan: {settings.MCP_SERVER_NAME} v{settings.VERSION}"
)
