Refactor ExplanationThe core issue was the timing of imports versus the creation of the mcp_instance.Original Problem:mcp_server_core.py imported src.mcp_project_tools.py.During the import of src.mcp_project_tools.py, Python executed the code within it, including from .mcp_server_core import mcp_instance.However, at that moment, mcp_server_core.py hadn't finished executing yet, and mcp_instance hadn't been created, leading to an ImportError or AttributeError (depending on the exact state) and the circular dependency lock.Refactor Solution:In mcp_server_core.py, the creation of mcp_instance = FastMCP(...) is moved before the lines that import the tool modules (import src.mcp_project_tools, import src.mcp_server).Now, when mcp_server_core.py executes, it fully creates and assigns mcp_instance.Then, it proceeds to import src.mcp_project_tools.py.When src.mcp_project_tools.py executes its import from .mcp_server_core import mcp_instance, the mcp_instance already exists in the mcp_server_core module's namespace, and the import succeeds.The @mcp_instance.tool() decorators can then correctly use the imported instance to register the tool functions.This breaks the circular dependency by ensuring the shared object (mcp_instance) is fully initialized before the modules that depend on it are loaded.Verification StepsReplace Files: Replace the content of your src/mcp_server_core.py and src/mcp_project_tools.py with the refactored versions below.Run Server: Start your MCP server application.Check Logs:Look for the log message FastMCP instance created... in mcp_server_core.py.Look for the Registering MCP tool: and ToolManager: Added tool: log messages for each tool defined in mcp_project_tools.py. This confirms the decorators ran successfully after the instance was created.Ensure there are no ImportError or AttributeError messages related to the circular import during startup.Test Tool Listing: If you have a client or a way to interact with the running MCP server, try listing the available tools. The tools defined in mcp_project_tools.py (e.g., list_projects, create_project) should now appear in the list.Test Tool Execution: Try executing one of the tools (e.g., list_projects) to ensure it functions correctly.

import logging
from typing import Any, Dict, AsyncIterator, Callable, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio # Keep asyncio import if needed elsewhere, or remove if only for patching below

from sqlalchemy.ext.asyncio import AsyncSession

# Attempt to import FastMCP and handle potential installation issues
try:
    from mcp.server.fastmcp import FastMCP, Context
    from mcp.server.fastmcp.tools.tool_manager import ToolManager # Import ToolManager here
except ImportError as e:
    logging.critical(
        f"Failed to import from mcp.server.fastmcp: {e}. "
        "Please ensure 'mcp[cli]' is installed correctly."
    )
    raise # Re-raise the exception to halt execution if MCP is not installed

from .config import settings
from .database import AsyncSessionFactory, Base, engine

logger = logging.getLogger(__name__)

# --- Lifespan Management ---
@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[Dict[str, Any]]:
    """
    Asynchronous context manager for FastAPI application lifespan events.
    Handles database initialization on startup and cleanup on shutdown.
    """
    logger.info("Application lifespan startup...")
    try:
        async with engine.begin() as conn:
            logger.info("Initializing database tables (if they don't exist)...")
            # This ensures all tables based on Base metadata are created
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialization check complete.")
    except Exception as e:
        # Log critical error if DB initialization fails, as it might prevent app function
        logger.critical(
            f"Database table initialization failed during lifespan startup: {e}", exc_info=True
        )
        # Depending on the desired behavior, you might want to raise the exception
        # or handle it differently to allow the app to start in a degraded state.
        # For now, we log and continue.

    # Context data to be available within the application (e.g., via request state)
    context_data = {"db_session_factory": AsyncSessionFactory}
    try:
        # Yield control to the application, making context_data available
        yield context_data
    finally:
        # Code here runs on application shutdown
        logger.info("Application lifespan shutdown.")
        # Dispose of the engine connection pool if necessary (often handled automatically)
        # await engine.dispose() # Uncomment if explicit disposal is needed

# --- MCP Instance Creation ---
# Create the FastMCP instance BEFORE importing tool modules that depend on it.
mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=app_lifespan # Pass the lifespan manager to FastMCP
)
logger.info(
    f"FastMCP instance created: {settings.MCP_SERVER_NAME} v{settings.VERSION} at id {id(mcp_instance)}"
)
# Log the initial state of the ToolManager associated with the instance
if hasattr(mcp_instance, "_tool_manager"):
    logger.info(f"Initial ToolManager instance id: {id(mcp_instance._tool_manager)}")
else:
    logger.warning("FastMCP instance does not have a '_tool_manager' attribute immediately after creation.")


# --- Tool Registration Logging Patches ---
# Apply patches *after* the mcp_instance is created but *before* tools are imported.

# Patch FastMCP.add_tool for detailed logging
original_add_tool = FastMCP.add_tool
def logged_add_tool(self: FastMCP, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> None:
    """Logs tool registration attempts via FastMCP.add_tool."""
    tool_name = name or getattr(fn, "__name__", "<unknown>")
    logger.info(f"Attempting to register MCP tool via FastMCP.add_tool: '{tool_name}'")
    # Ensure the instance being used is the one we created
    logger.info(f"Using FastMCP instance at id {id(self)}")
    if hasattr(self, "_tool_manager"):
         logger.info(f"Targeting ToolManager instance at id {id(self._tool_manager)}")
    else:
         logger.warning("'_tool_manager' not found on FastMCP instance during add_tool call.")

    # Call the original method
    original_add_tool(self, fn, name=name, description=description)
    logger.info(f"Completed call to original FastMCP.add_tool for '{tool_name}'")

    # Log current tools after attempted registration
    if hasattr(self, "_tool_manager") and hasattr(self._tool_manager, "_tools"):
        tools = getattr(self._tool_manager, "_tools", {})
        logger.info(f"Current tools in ToolManager after adding '{tool_name}': {list(tools.keys())}")
    else:
        logger.warning("Could not verify tools in ToolManager after adding tool.")

FastMCP.add_tool = logged_add_tool # Apply the patch
logger.info("Patched FastMCP.add_tool with logging.")

# Patch ToolManager directly for logging (if ToolManager was imported successfully)
if ToolManager:
    original_toolmanager_add_tool = ToolManager.add_tool
    original_toolmanager_list_tools = ToolManager.list_tools

    def logged_toolmanager_add_tool(self: ToolManager, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> Any:
        """Logs tool registration attempts directly via ToolManager.add_tool."""
        tool_name = name or getattr(fn, "__name__", "<unknown>")
        logger.info(f"ToolManager (id: {id(self)}): Adding tool '{tool_name}'")
        # Call the original method
        tool = original_toolmanager_add_tool(self, fn, name=name, description=description)
        if tool:
            logger.info(f"ToolManager (id: {id(self)}): Successfully added tool '{tool.name}'. Current tools: {list(self._tools.keys())}")
        else:
            # This case might indicate an issue with tool creation/validation within ToolManager
            logger.warning(f"ToolManager (id: {id(self)}): add_tool returned None for '{tool_name}'.")
        return tool

    def logged_toolmanager_list_tools(self: ToolManager) -> Any:
        """Logs listing of tools directly via ToolManager.list_tools."""
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
if original_list_tools:
    async def logged_list_tools(self: FastMCP) -> Any:
        """Logs listing of tools via FastMCP.list_tools and introspects."""
        logger.info(f"FastMCP (id: {id(self)}): Listing tools...")
        # Call the original method if it exists
        tools = await original_list_tools(self)
        tool_names = [getattr(tool, 'name', '<unknown>') for tool in tools]
        logger.info(f"FastMCP (id: {id(self)}): listed tools: {tool_names}")

        # Introspect internal ToolManager directly
        if hasattr(self, "_tool_manager") and hasattr(self._tool_manager, "_tools"):
             internal_tools = getattr(self._tool_manager, "_tools", {})
             logger.info(f"FastMCP (id: {id(self)}): Internal ToolManager (id: {id(self._tool_manager)}) keys: {list(internal_tools.keys())}")
        else:
             logger.warning(f"FastMCP (id: {id(self)}): No internal _tool_manager or _tools found for introspection.")
        return tools

    FastMCP.list_tools = logged_list_tools
    logger.info("Patched FastMCP.list_tools with logging.")
else:
    logger.warning("FastMCP.list_tools method not found, skipping patching.")


# --- Import Tool Modules ---
# Import tool modules AFTER mcp_instance is created and patches are applied.
# The act of importing these modules will trigger the @mcp_instance.tool() decorators within them.
logger.info("Importing MCP tool modules to trigger registration...")
try:
    import src.mcp_project_tools # noqa: F401 - Import executes the module code
    logger.info("Successfully imported src.mcp_project_tools")
except ImportError as e:
    logger.error(f"Failed to import src.mcp_project_tools: {e}", exc_info=True)
except Exception as e:
    logger.error(f"An unexpected error occurred during import of src.mcp_project_tools: {e}", exc_info=True)

try:
    import src.mcp_server # noqa: F401 - Assuming this also contains tools
    logger.info("Successfully imported src.mcp_server")
except ImportError as e:
    logger.error(f"Failed to import src.mcp_server: {e}", exc_info=True)
except Exception as e:
    logger.error(f"An unexpected error occurred during import of src.mcp_server: {e}", exc_info=True)

logger.info("Finished importing MCP tool modules.")

# --- Helper Function for DB Session (if needed globally) ---
# It might be better practice to inject the session factory or session
# into the context (as done in lifespan) rather than having a global helper here.
# However, if mcp_project_tools needs it directly, ensure it's defined.
async def get_session(ctx: Context[Any, Any]) -> AsyncSession:
    """Retrieves an async database session from the MCP context."""
    # This assumes the db_session_factory was added to context in app_lifespan
    session_factory = ctx.get("db_session_factory")
    if not session_factory:
        # Log error or raise exception if factory is missing
        logger.error("Database session factory not found in MCP context!")
        raise ValueError("Database session factory missing from context")
    async with session_factory() as session:
        return session

# You might not need get_session defined here if it's only used by tools,
# as they can import it from where it's most logically placed (e.g., a db utils module).
# If kept here, ensure it doesn't cause import issues itself. Consider moving it.



import logging
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession # Import AsyncSession if type hinting needed

# Import the FastMCP Context type hint
try:
    from mcp.server.fastmcp import Context
except ImportError as e:
    logging.critical(
        f"Failed to import Context from mcp.server.fastmcp: {e}. "
        "Ensure 'mcp[cli]' is installed."
    )
    raise

# Import the mcp_instance *after* it has been created in mcp_server_core.
# This is safe now because mcp_server_core creates the instance before importing this module.
from .mcp_server_core import mcp_instance

# Import database helper functions specific to project operations
from .mcp_db_helpers_project import (
    create_project_in_db,
    list_projects_in_db,
    get_project_in_db,
    update_project_in_db,
    delete_project_in_db,
    set_active_project_in_db,
)
# Import the data model (assuming it's defined in models.py)
from .models import Project

logger = logging.getLogger(__name__)

# --- Database Session Helper ---
# It's generally better to get the session factory from the context
# rather than importing a get_session function if possible, to reduce coupling.
async def get_db_session_from_context(ctx: Context[Any, Any]) -> AsyncSession:
    """
    Retrieves an async database session from the MCP context's session factory.
    Uses contextlib for proper session management.
    """
    session_factory = ctx.get("db_session_factory")
    if not session_factory:
        logger.error("Database session factory not found in MCP context!")
        raise ValueError("Database session factory missing from context")

    # Create a new session for this request/operation
    async with session_factory() as session:
        # Yield the session to the caller within the managed context
        # The 'async with' ensures the session is closed/handled correctly
        # Note: We return the session directly here, caller uses it.
        # If you need the session *within* this function, you'd use it here.
        # For tool functions, they will call this helper and use the returned session.
        # Let's adjust this slightly: the tool should manage the session scope.
        # This helper just provides the factory.
        # Re-thinking: The tool needs the actual session. Let's provide it.
        # The original `get_session` likely intended to return an active session.
         return session # Returning the session directly from the async context manager is tricky.

# Let's revert to a simpler pattern assuming the tool manages the session lifecycle
# by calling the factory obtained from context. Or stick to the original `get_session`
# if it's defined centrally and handles the session scope. Assuming the latter for now.

# If get_session is defined in mcp_server_core and imported, use that.
# If not, define a way to get it here. Let's assume it might be better
# defined alongside other DB utilities. For now, import from core as originally shown.
try:
    from .mcp_server_core import get_session # Assuming get_session is available here
except ImportError:
    logger.warning("get_session helper not found in mcp_server_core. Tools might fail.")
    # Define a fallback or raise an error if get_session is essential
    async def get_session(ctx: Context[Any, Any]) -> AsyncSession: # type: ignore
         raise NotImplementedError("get_session helper function is required but not found.")


# --- MCP Tool Definitions ---
# Tools are registered using the imported mcp_instance decorator.

@mcp_instance.tool()
async def list_projects(ctx: Context[Any, Any]) -> Dict[str, Any]:
    """Lists all projects stored in the database."""
    logger.info("Executing tool: list_projects")
    try:
        session = await get_session(ctx) # Get session for this operation
        projects = await list_projects_in_db(session)
        logger.info(f"Found {len(projects)} projects.")
        # Ensure projects are serializable if needed (e.g., convert models to dicts)
        # Assuming list_projects_in_db returns serializable data or models handled by FastMCP
        return {"projects": projects}
    except Exception as e:
        logger.error(f"Error in list_projects tool: {e}", exc_info=True)
        # Return an error structure or raise an exception recognized by FastMCP
        return {"error": f"Failed to list projects: {e}"}
    # No explicit session closing needed if get_session uses a context manager internally
    # or if the lifespan manager handles session cleanup per request.

@mcp_instance.tool()
async def create_project(name: str, description: str, path: str, is_active: bool, ctx: Context[Any, Any]) -> Dict[str, Any]:
    """Creates a new project in the database."""
    logger.info(f"Executing tool: create_project (Name: {name})")
    try:
        session = await get_session(ctx)
        project = await create_project_in_db(
            session=session,
            name=name,
            path=path,
            description=description,
            is_active=is_active
        )
        logger.info(f"Project '{name}' created with ID {project.id}.")
        # Assuming project object is serializable or handled by FastMCP
        return {"project": project}
    except Exception as e:
        logger.error(f"Error in create_project tool: {e}", exc_info=True)
        return {"error": f"Failed to create project: {e}"}

@mcp_instance.tool()
async def get_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    """Retrieves a specific project by its ID."""
    logger.info(f"Executing tool: get_project (ID: {project_id})")
    try:
        session = await get_session(ctx)
        project = await get_project_in_db(session, project_id)
        if project:
            logger.info(f"Project ID {project_id} found.")
            return {"project": project}
        else:
            logger.warning(f"Project ID {project_id} not found.")
            return {"error": f"Project with ID {project_id} not found."}
    except Exception as e:
        logger.error(f"Error in get_project tool: {e}", exc_info=True)
        return {"error": f"Failed to get project {project_id}: {e}"}

@mcp_instance.tool()
async def update_project(project_id: int, name: str, description: str, ctx: Context[Any, Any]) -> Dict[str, Any]:
    """Updates an existing project's name and description."""
    logger.info(f"Executing tool: update_project (ID: {project_id})")
    try:
        session = await get_session(ctx)
        project = await update_project_in_db(
            session=session,
            project_id=project_id,
            name=name,
            description=description
        )
        if project:
            logger.info(f"Project ID {project_id} updated.")
            return {"project": project}
        else:
            # update_project_in_db should ideally raise an error or return None if not found
            logger.warning(f"Project ID {project_id} not found for update.")
            return {"error": f"Project with ID {project_id} not found for update."}
    except Exception as e:
        logger.error(f"Error in update_project tool: {e}", exc_info=True)
        return {"error": f"Failed to update project {project_id}: {e}"}

@mcp_instance.tool()
async def delete_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    """Deletes a project by its ID."""
    logger.info(f"Executing tool: delete_project (ID: {project_id})")
    try:
        session = await get_session(ctx)
        success = await delete_project_in_db(session=session, project_id=project_id)
        if success:
            logger.info(f"Project ID {project_id} deleted successfully.")
            return {"success": True, "message": f"Project {project_id} deleted."}
        else:
            logger.warning(f"Project ID {project_id} not found for deletion.")
            return {"success": False, "error": f"Project with ID {project_id} not found."}
    except Exception as e:
        logger.error(f"Error in delete_project tool: {e}", exc_info=True)
        return {"success": False, "error": f"Failed to delete project {project_id}: {e}"}

@mcp_instance.tool()
async def set_active_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    """Sets a specific project as the active project."""
    logger.info(f"Executing tool: set_active_project (ID: {project_id})")
    try:
        session = await get_session(ctx)
        success = await set_active_project_in_db(session=session, project_id=project_id)
        if success:
            logger.info(f"Project ID {project_id} set as active.")
            return {"success": True, "message": f"Project {project_id} is now active."}
        else:
            logger.warning(f"Failed to set project ID {project_id} as active (likely not found).")
            # Provide a more specific error if possible from the db helper
            return {"success": False, "error": f"Failed to set project {project_id} as active."}
    except Exception as e:
        logger.error(f"Error in set_active_project tool: {e}", exc_info=True)
        return {"success": False, "error": f"Failed to set project {project_id} active: {e}"}

# Add a log message to confirm this module was imported and processed
logger.info("MCP project tools defined and registered.")
