import logging
from contextlib import asynccontextmanager
from mcp.server.fastmcp import Context
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db_session

logger = logging.getLogger(__name__)

@asynccontextmanager
async def managed_mcp_session(ctx: Context):
    """
    Async context manager that handles the lifecycle of an AsyncSession.
    Uses the same pattern as the working project/memory tools by leveraging
    get_db_session() with async for, which properly establishes the greenlet context.

    Args:
        ctx: The FastMCP Context object (required for API compatibility but not used)

    Yields:
        AsyncSession: The database session for use in MCP tools
    """
    async for session in get_db_session():
        try:
            yield session
            # Let the caller handle commit explicitly if needed
        finally:
            # Session is closed automatically by get_db_session
            pass
