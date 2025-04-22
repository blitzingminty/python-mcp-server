import logging
from typing import Any, Dict, AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI

from sqlalchemy.ext.asyncio import AsyncSession

try:
    from mcp.server.fastmcp import FastMCP, Context
except ImportError as e:
    logging.critical(
        f"Failed to import from mcp.server.fastmcp: {e}. Please ensure 'mcp[cli]' is installed correctly.")
    raise

from .config import settings
from .database import AsyncSessionFactory, Base, engine

logger = logging.getLogger(__name__)

@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[Dict[str, Any]]:
    logger.info("Application lifespan startup...")
    try:
        async with engine.begin() as conn:
            logger.info("Initializing database tables (if they don't exist)...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialization check complete.")
    except Exception as e:
        logger.critical(
            f"Database table initialization failed during lifespan startup: {e}", exc_info=True)

    context_data = {"db_session_factory": AsyncSessionFactory}
    try:
        yield context_data
    finally:
        logger.info("Application lifespan shutdown.")

mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=app_lifespan
)
logger.info(
    f"FastMCP instance created with lifespan: {settings.MCP_SERVER_NAME} v{settings.VERSION}"
)

async def get_session(ctx: Context[Any, Any]) -> AsyncSession:
    try:
        session_factory = ctx.request_context.lifespan_context["db_session_factory"]
        return session_factory()
    except KeyError:
        logger.error("Database session factory not found in lifespan context.")
        raise RuntimeError(
            "Server configuration error: DB Session Factory missing.")
    except AttributeError:
        logger.error(
            "Context structure unexpected. Cannot find lifespan context or session factory.")
        raise RuntimeError(
            "Server configuration error: Context structure invalid.")
