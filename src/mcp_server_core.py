import logging
from typing import Any, Dict, AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI

from sqlalchemy.ext.asyncio import AsyncSession

try:
    from mcp.server.fastmcp import FastMCP, Context
except ImportError as e:
    logging.critical(
        f"Failed to import from mcp.server.fastmcp: {e}. Please ensure 'mcp[cli]' is installed correctly."
    )
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
            f"Database table initialization failed during lifespan startup: {e}", exc_info=True
        )
    context_data = {"db_session_factory": AsyncSessionFactory}
    try:
        yield context_data
    finally:
        logger.info("Application lifespan shutdown.")

from typing import Callable, Optional

# --- MCP Instance Creation ---
# Create the FastMCP instance BEFORE importing tool modules that depend on it.
mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=app_lifespan  # Pass the lifespan manager to FastMCP
)
logger.info(
    f"FastMCP instance created: {settings.MCP_SERVER_NAME} v{settings.VERSION} at id {id(mcp_instance)}"
)
if hasattr(mcp_instance, "_tool_manager"):
    logger.info(f"Initial ToolManager instance id: {id(mcp_instance._tool_manager)}")
else:
    logger.warning("FastMCP instance does not have a '_tool_manager' attribute immediately after creation.")

# --- Tool Registration Logging Patches ---
# Patch FastMCP.add_tool for detailed logging
original_add_tool = FastMCP.add_tool

def logged_add_tool(self: Any, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> None:
    """Logs tool registration attempts via FastMCP.add_tool."""
    tool_name = name or getattr(fn, "__name__", "<unknown>")
    logger.info(f"Attempting to register MCP tool via FastMCP.add_tool: '{tool_name}'")
    logger.info(f"Using FastMCP instance at id {id(self)}")
    if hasattr(self, "_tool_manager"):
        logger.info(f"Targeting ToolManager instance at id {id(self._tool_manager)}")
    else:
        logger.warning("'_tool_manager' not found on FastMCP instance during add_tool call.")
    if callable(original_add_tool):
        original_add_tool(self, fn, name=name, description=description)
    else:
        logger.error("original_add_tool is not callable.")
        return
    logger.info(f"Completed call to original FastMCP.add_tool for '{tool_name}'")
    if hasattr(self, "_tool_manager") and hasattr(self._tool_manager, "_tools"):
        tools = getattr(self._tool_manager, "_tools", {})
        logger.info(f"Current tools in ToolManager after adding '{tool_name}': {list(tools.keys())}")
    else:
        logger.warning("Could not verify tools in ToolManager after adding tool.")

FastMCP.add_tool = logged_add_tool
logger.info("Patched FastMCP.add_tool with logging.")

# Patch ToolManager directly for logging (if ToolManager is available)
try:
    from mcp.server.fastmcp.tools.tool_manager import ToolManager
except ImportError:
    ToolManager = None

if ToolManager:
    original_toolmanager_add_tool = ToolManager.add_tool
    original_toolmanager_list_tools = ToolManager.list_tools

    def logged_toolmanager_add_tool(self: Any, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> Any:
        """Logs tool registration via ToolManager.add_tool."""
        tool_name = name or getattr(fn, "__name__", "<unknown>")
        logger.info(f"ToolManager (id: {id(self)}): Adding tool '{tool_name}'")
        tool = original_toolmanager_add_tool(self, fn, name=name, description=description)
        if tool:
            logger.info(f"ToolManager (id: {id(self)}): Successfully added tool '{tool.name}'. Current tools: {list(self._tools.keys())}")
        else:
            logger.warning(f"ToolManager (id: {id(self)}): add_tool returned None for '{tool_name}'.")
        return tool

    def logged_toolmanager_list_tools(self: Any) -> Any:
        """Logs listing of tools via ToolManager.list_tools."""
        logger.info(f"ToolManager (id: {id(self)}): Listing tools...")
        tools = original_toolmanager_list_tools(self)
        tool_names = [getattr(tool, 'name', '<unknown>') for tool in tools]
        logger.info(f"ToolManager (id: {id(self)}): Listed tools: {tool_names}")
        return tools

    ToolManager.add_tool = logged_toolmanager_add_tool
    ToolManager.list_tools = logged_toolmanager_list_tools
    logger.info("Patched ToolManager.add_tool and ToolManager.list_tools with logging.")
else:
    logger.warning("ToolManager not found or imported, skipping direct patching.")

# Patch FastMCP.list_tools for logging (check if method exists)
original_list_tools = getattr(FastMCP, "list_tools", None)
if original_list_tools is not None and callable(original_list_tools):
    async def logged_list_tools(self: FastMCP) -> Any:
        """Logs listing of tools via FastMCP.list_tools."""
        potential = await original_list_tools(self)
        tools = potential if potential is not None else []
        logger.info(f"Listing MCP tools: {[tool.name for tool in tools]}")
        return tools

    FastMCP.list_tools = logged_list_tools
    logger.info("Patched FastMCP.list_tools with logging.")
else:
    async def dummy_list_tools(self: FastMCP) -> Any:
        logger.info("FastMCP.list_tools method not found; returning empty list.")
        return []
    FastMCP.list_tools = dummy_list_tools
    logger.info("Assigned dummy FastMCP.list_tools with logging.")

# --- Import Tool Modules ---
# Import tool modules AFTER mcp_instance is created and patches are applied.
logger.info("Importing MCP tool modules to trigger registration...")
try:
    import src.mcp_project_tools  # noqa: F401 - Import executes the module code
    logger.info("Successfully imported src.mcp_project_tools")
except ImportError as e:
    logger.error(f"Failed to import src.mcp_project_tools: {e}", exc_info=True)
except Exception as e:
    logger.error(f"An unexpected error occurred during import of src.mcp_project_tools: {e}", exc_info=True)

try:
    import src.mcp_server  # noqa: F401 - Assuming this also contains tools
    logger.info("Successfully imported src.mcp_server")
except ImportError as e:
    logger.error(f"Failed to import src.mcp_server: {e}", exc_info=True)
except Exception as e:
    logger.error(f"An unexpected error occurred during import of src.mcp_server: {e}", exc_info=True)

logger.info("Finished importing MCP tool modules.")

# Remove get_session from mcp_server_core to break circular import
# Instead, move get_session to a new module (e.g., src/mcp_db_helpers.py)
# For now, comment out get_session to avoid circular import issues.
# async def get_session(ctx: Context[Any, Any]) -> AsyncSession:
#     try:
#         session_factory = ctx.request_context.lifespan_context["db_session_factory"]
#         return session_factory()
#     except KeyError:
#         logger.error("Database session factory not found in lifespan context.")
#         raise RuntimeError("Server configuration error: DB Session Factory missing.")
#     except AttributeError:
#         logger.error("Context structure unexpected. Cannot find lifespan context or session factory.")
#         raise RuntimeError("Server configuration error: Context structure invalid.")
