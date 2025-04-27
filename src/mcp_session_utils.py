import logging
from contextlib import asynccontextmanager
from mcp.server.fastmcp import Context
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def get_session_from_mcp_context(ctx: Context) -> AsyncSession:
    """
    Retrieve an AsyncSession instance from the MCP context.
    Extracts the 'db_session_factory' from ctx.request_context.lifespan_context,
    and calls it to create a new AsyncSession.
    Raises a RuntimeError if the session factory is missing or an error occurs.
    """
    try:
        session_factory = ctx.request_context.lifespan_context["db_session_factory"]
        session = session_factory()
        return session
    except KeyError as e:
        logger.error(f"DB session factory not found in MCP context: {e}", exc_info=True)
        raise RuntimeError("DB Session Factory missing in MCP context")
    except Exception as e:
        logger.error(f"Error obtaining DB session from MCP context: {e}", exc_info=True)
        raise

@asynccontextmanager
async def managed_mcp_session(ctx: Context):
    """
    Async context manager that handles the lifecycle of an AsyncSession.
    It uses get_session_from_mcp_context to acquire the session, yields it for use,
    commits the transaction if no exception occurs, rolls back on errors, and
    ensures the session is closed.
    """
    session = await get_session_from_mcp_context(ctx)
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error("Error during session operation", exc_info=True)
        raise
    finally:
        await session.close()
