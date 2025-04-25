# AI Assistance Request

## Task Description
Refactor the MCP server initialization and tool registration in the python-mcp-server project to resolve a circular import issue. The circular import occurs between `src/mcp_server_core.py` and `src/mcp_project_tools.py` because `mcp_instance` is imported during module initialization, causing import errors and preventing MCP tools from being registered.

## Relevant Memory Bank Context
**From `activeContext.md`:**
- MCP tools are not being returned to clients because they are not registered on the MCP server instance.
- The root cause is the import and instance creation order causing circular imports.
- An implementation plan was created to consolidate MCP instance creation and tool imports.
- Attempted refactor caused a circular import error.

## Relevant Source Code Excerpts

### src/mcp_server_core.py (partial)
```python
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

from typing import Callable, Optional, Any

# Import MCP tool modules here to ensure registration before MCP instance creation
import src.mcp_project_tools  # noqa: F401
import src.mcp_server  # noqa: F401

# Add logging to FastMCP add_tool method to trace tool registration
original_add_tool = FastMCP.add_tool

def logged_add_tool(self: Any, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> Any:
    tool_name = name or getattr(fn, "__name__", "<unknown>")
    logger.info(f"Registering MCP tool: {tool_name}")
    logger.info(f"Using ToolManager instance at {id(self._tool_manager)}")
    # Call the original add_tool method
    original_add_tool(self, fn, name=name, description=description)
    # After adding the tool, log the current tools in the ToolManager
    if hasattr(self, "_tool_manager"):
        tools = getattr(self._tool_manager, "_tools", {})
        logger.info(f"Current tools in ToolManager after adding: {list(tools.keys())}")
    else:
        logger.warning("No _tool_manager attribute found on FastMCP instance after adding tool.")
    return None

FastMCP.add_tool = logged_add_tool

# Patch FastMCP to add logging for tool listing
original_list_tools = getattr(FastMCP, "list_tools", None)

import asyncio

# Patch ToolManager methods for logging
try:
    from mcp.server.fastmcp.tools.tool_manager import ToolManager
except ImportError:
    ToolManager = None

if ToolManager:
    original_toolmanager_add_tool = ToolManager.add_tool
    original_toolmanager_list_tools = ToolManager.list_tools

    def logged_toolmanager_add_tool(self, fn, name=None, description=None):
        tool = original_toolmanager_add_tool(self, fn, name=name, description=description)
        if tool is not None:
            logger.info(f"ToolManager: Added tool '{tool.name}'")
        else:
            logger.warning("ToolManager: Added tool is None")
        return tool

    def logged_toolmanager_list_tools(self):
        tools = original_toolmanager_list_tools(self)
        logger.info(f"ToolManager: Listing tools: {[tool.name for tool in tools]}")
        return tools

    ToolManager.add_tool = logged_toolmanager_add_tool
    ToolManager.list_tools = logged_toolmanager_list_tools

async def logged_list_tools(self):
    tools = []
    if original_list_tools:
        tools = await original_list_tools(self)
    logger.info(f"Listing MCP tools: {[tool.name for tool in tools]}")

    # Inspect internal tool registry directly
    internal_tools = getattr(self, "_tools", None)
    if internal_tools is not None:
        logger.info(f"Internal _tools attribute keys: {list(internal_tools.keys())}")
    else:
        # Try to find ToolManager attribute
        tool_manager = None
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if attr and attr.__class__.__name__ == "ToolManager":
                tool_manager = attr
                break
        if tool_manager:
            logger.info(f"Found ToolManager attribute '{attr_name}' with tools: {list(tool_manager._tools.keys())}")
        else:
            logger.warning("No internal _tools attribute or ToolManager found on FastMCP instance.")

    # Additional introspection: log all attributes and their types
    logger.info("FastMCP instance attributes and types:")
    for attr_name in dir(self):
        try:
            attr = getattr(self, attr_name)
            logger.info(f" - {attr_name}: {type(attr)}")
        except Exception as e:
            logger.warning(f" - {attr_name}: <error accessing attribute: {e}>")

    return tools

if original_list_tools:
    FastMCP.list_tools = logged_list_tools

mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=app_lifespan
)
logger.info(
    f"FastMCP instance created with lifespan: {settings.MCP_SERVER_NAME} v{settings.VERSION}"
)
```

### src/mcp_project_tools.py (partial)
```python
from typing import Any, Dict
from mcp.server.fastmcp import Context
from .mcp_server_core import mcp_instance, get_session
from .mcp_db_helpers_project import (
    create_project_in_db,
    list_projects_in_db,
    get_project_in_db,
    update_project_in_db,
    delete_project_in_db,
    set_active_project_in_db,
)
from .models import Project

@mcp_instance.tool()
async def list_projects(ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    projects = await list_projects_in_db(session)
    return {"projects": projects}

@mcp_instance.tool()
async def create_project(name: str, description: str, path: str, is_active: bool, ctx: Context[Any, Any]) -> Dict[str, Project]:
    session = await get_session(ctx)
    project = await create_project_in_db(session=session, name=name, path=path, description=description, is_active=is_active)
    return {"project": project}

@mcp_instance.tool()
async def get_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    project = await get_project_in_db(session, project_id)
    return {"project": project}

@mcp_instance.tool()
async def update_project(project_id: int, name: str, description: str, ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    project = await update_project_in_db(session=session, project_id=project_id, name=name, description=description)
    return {"project": project}

@mcp_instance.tool()
async def delete_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    success = await delete_project_in_db(session=session, project_id=project_id)
    return {"success": success}

@mcp_instance.tool()
async def set_active_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    success = await set_active_project_in_db(session=session, project_id=project_id)
    return {"success": success}
```

## Expected Output
- Refactored Python code files with circular import resolved.
- Explanation of the refactor approach.
- Confirmation steps to verify the fix.

## Request
Please assist with the refactor to resolve the circular import and ensure MCP tools are properly registered and discoverable.
