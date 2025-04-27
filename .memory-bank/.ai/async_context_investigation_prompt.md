# AI Assistance Request

## Task Description
The project is experiencing a persistent "greenlet_spawn has not been called" async context error during the execution of document-related MCP tools, specifically during update operations. This error indicates improper async context propagation when using SQLAlchemy's async ORM with FastAPI and FastMCP.

## Relevant Memory Bank Context
- MCP server core setup includes FastMCP with detailed logging and proper lifespan management.
- Document MCP tools have been refactored to align session management with working project and memory tools.
- Duplicate function declarations in document tools have been removed.
- Helper functions for document database operations are correctly implemented with async SQLAlchemy.
- Configuration uses SQLite with aiosqlite driver and standard FastAPI/Uvicorn setup.
- Memory and project tools function correctly with the same async session pattern.
- The error persists only in document tools, suggesting an issue with async event loop integration or context propagation.

## Specific Instructions
- Analyze the interaction between FastMCP, FastAPI, and SQLAlchemy async ORM in the context of this project.
- Identify potential causes for the "greenlet_spawn" async context error during document tool execution.
- Provide detailed recommendations or code-level solutions to ensure proper async context propagation.
- Suggest any necessary changes to MCP server setup, tool implementation, or environment configuration.
- Include references to relevant documentation or known issues with these technologies.
- Format the response as a detailed technical report with actionable steps.

## Relevant Source Code
```python
# src/mcp_document_tools.py
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

import logging
from src.mcp_server_core import mcp_instance
from typing import Any, Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from src.mcp_db_helpers_document import list_documents_in_db
from src.database import get_db_session

@asynccontextmanager
async def get_session_from_factory():
    async for session in get_db_session():
        yield session

@mcp_instance.tool(name="list_documents", description="List all documents")
async def list_documents(project_id: int | None = None):
    logger.info(f"MCP Tool 'list_documents' called for project_id: {project_id}.")
    async with get_session_from_factory() as session:
        documents = await list_documents_in_db(session, project_id=project_id)
        document_list = []
        for doc in documents:
            document_list.append({
                "id": doc.id,
                "project_id": doc.project_id,
                "name": doc.name,
                "path": doc.path,
                "type": doc.type,
                "version": doc.version,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
                "tags": [tag.name for tag in doc.tags]
            })
        logger.info(f"MCP Tool 'list_documents' returning {len(document_list)} documents.")
        return {"documents": document_list}

from src.mcp_db_helpers_document import add_document_in_db

@mcp_instance.tool(name="create_document", description="Create a new document")
async def create_document(project_id: int, name: str, path: str, content: str, type: str, version: str = "1.0.0"):
    logger.info(f"MCP Tool 'create_document' called for project_id: {project_id}, name: {name}.")
    async with get_session_from_factory() as session:
        document = await add_document_in_db(session, project_id=project_id, name=name, path=path, content=content, type=type, version=version)
        if document:
            await session.commit()
            logger.info(f"MCP Tool 'create_document' successfully created document ID: {document.id}.")
            return {
                "status": "created",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags]
                }
            }
        else:
            logger.error(f"MCP Tool 'create_document' failed to create document for project_id: {project_id}, name: {name}.")
            return {"status": "error", "message": "Failed to create document"}

from src.mcp_db_helpers_document import get_document_in_db

@mcp_instance.tool(name="get_document", description="Retrieve details for a document")
async def get_document(document_id: int):
    logger.info(f"MCP Tool 'get_document' called for document_id: {document_id}.")
    async with get_session_from_factory() as session:
        document = await get_document_in_db(session, document_id=document_id)
        if document:
            logger.info(f"MCP Tool 'get_document' found document ID: {document_id}.")
            return {
                "status": "success",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "content": document.content,
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags],
                    "versions": [{"id": v.id, "version": v.version, "created_at": v.created_at.isoformat()} for v in document.versions]
                }
            }
        else:
            logger.warning(f"MCP Tool 'get_document' document ID {document_id} not found.")
            return {"status": "error", "message": f"Document ID {document_id} not found."}

from src.mcp_db_helpers_document import update_document_in_db

@mcp_instance.tool(name="update_document", description="Update an existing document")
async def update_document(document_id: int, name: str | None = None, path: str | None = None, type: str | None = None):
    logger.info(f"MCP Tool 'update_document' called for document_id: {document_id} with data: name={name}, path={path}, type={type}.")
    async with get_session_from_factory() as session:
        document = await update_document_in_db(session, document_id=document_id, name=name, path=path, type=type)
        if document:
            await session.commit()
            logger.info(f"MCP Tool 'update_document' successfully updated document ID: {document_id}.")
            return {
                "status": "updated",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags]
                }
            }
        else:
            logger.warning(f"MCP Tool 'update_document' document ID {document_id} not found or no changes made.")
            return {"status": "error", "message": f"Document ID {document_id} not found or no changes made."}

from src.mcp_db_helpers_document import delete_document_in_db

@mcp_instance.tool(name="delete_document", description="Delete a document")
async def delete_document(document_id: int):
    logger.info(f"MCP Tool 'delete_document' called for document_id: {document_id}.")
    async with get_session_from_factory() as session:
        success = await delete_document_in_db(session, document_id=document_id)
        if success:
            await session.commit()
            logger.info(f"MCP Tool 'delete_document' successfully deleted document ID: {document_id}.")
            return {"status": "deleted", "document_id": document_id}
        else:
            logger.error(f"MCP Tool 'delete_document' failed to delete document ID: {document_id}.")
            return {"status": "error", "message": f"Failed to delete document ID {document_id}."}
```

```python
# src/mcp_db_helpers_document.py
import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError #, IntegrityError
from sqlalchemy.orm import selectinload

from typing import List # Added List import
from .models import Document, DocumentVersion, Project # Added Project import
#from .database import AsyncSessionFactory

logger = logging.getLogger(__name__)

async def list_documents_in_db(session: AsyncSession, project_id: Optional[int] = None) -> List[Document]: # type: ignore
    """
    Helper to list documents, optionally filtered by project.
    Eagerly loads project and tags for context.
    """
    logger.debug(f"Helper: Listing documents for project {project_id if project_id is not None else 'all'}.")
    try:
        stmt = select(Document).options(selectinload(Document.project), selectinload(Document.tags)).order_by(Document.project_id, Document.name)
        if project_id is not None:
            stmt = stmt.where(Document.project_id == project_id)
        result = await session.execute(stmt)
        documents = result.scalars().all()
        logger.debug(f"Helper: Found {len(documents)} documents.")
        return documents
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error listing documents: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Helper: Unexpected error listing documents: {e}", exc_info=True)
        return []

async def get_document_in_db(session: AsyncSession, document_id: int) -> Optional[Document]: # type: ignore
    """
    Helper to get a single document by ID.
    Eagerly loads project, tags, and versions for context.
    """
    logger.debug(f"Helper: Getting document ID {document_id}.")
    try:
        stmt = select(Document).options(
            selectinload(Document.project),
            selectinload(Document.tags),
            selectinload(Document.versions)
        ).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        if document:
            logger.debug(f"Helper: Found document '{document.name}' (ID: {document_id}).")
        else:
            logger.debug(f"Helper: Document ID {document_id} not found.")
        return document
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error getting document {document_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Helper: Unexpected error getting document {document_id}: {e}", exc_info=True)
        return None


async def add_document_in_db( # type: ignore
    session: AsyncSession, project_id: int, name: str, path: str, content: str,
    type: str, version: str = "1.0.0"
) -> Optional[Document]:
    logger.debug(f"Helper: Adding document '{name}' to project {project_id}.")
    project = await session.get(Project, project_id)  # Fixed: get Project, not column type
    if project is None:
        logger.warning(f"Helper: Project {project_id} not found for adding document.")
        return None
    new_document = Document(project_id=project_id, name=name, path=path, content=content, type=type, version=version)
    session.add(new_document)
    await session.flush()
    new_version_entry = DocumentVersion(document_id=new_document.id, content=content, version=version)
    session.add(new_version_entry)
    await session.refresh(new_document)
    await session.refresh(new_version_entry)
    logger.info(f"Helper: Document '{name}' (ID: {new_document.id}) added to project {project_id}.")
    return new_document

async def update_document_in_db( # type: ignore
    session: AsyncSession, document_id: int, name: Optional[str] = None,
    path: Optional[str] = None, type: Optional[str] = None
) -> Optional[Document]:
    logger.debug(f"Helper: Updating metadata for document ID {document_id} in DB.")
    document = await session.get(Document, document_id)
    if document is None:
        logger.warning(f"Helper: Document ID {document_id} not found for update.")
        return None
    update_data = {"name": name, "path": path, "type": type}
    updated = False
    for key, value in update_data.items():
        if value is not None and getattr(document, key) != value:
            setattr(document, key, value)
            updated = True
    if updated:
        logger.debug(f"Helper: Applying metadata updates to document {document_id}.")
        await session.flush()
        await session.refresh(document)
    else:
        logger.debug(f"Helper: No metadata changes detected for document {document_id}.")
    return document

async def delete_document_in_db(session: AsyncSession, document_id: int) -> bool: # type: ignore
    logger.debug(f"Helper: Deleting document ID {document_id} from DB.")
    doc = await session.get(Document, document_id, options=[selectinload(Document.tags), selectinload(Document.versions)])
    if doc is None:
        logger.warning(f"Helper: Document ID {document_id} not found for deletion.")
        return True
    try:
        await session.delete(doc)
        await session.flush()
        logger.info(f"Helper: Document ID {document_id} ('{doc.name}') deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting document {document_id}: {e}", exc_info=True)
        return False

async def get_document_version_content_db(session: AsyncSession, version_id: int) -> DocumentVersion | None: # type: ignore
    """
    Core logic to get a specific document version object by its ID.
    Eagerly loads the parent document for context (like mime type).
    Returns the DocumentVersion object or None if not found.
    """
    logger.debug(f"Helper: Getting document version content for version ID {version_id} in DB.")
    try:
        # Fetch the specific version, eagerly loading the parent document
        stmt = select(DocumentVersion).options(
            selectinload(DocumentVersion.document) # Eager load parent document
        ).where(DocumentVersion.id == version_id)
        result = await session.execute(stmt)
        version = result.scalar_one_or_none()

        if version is None:
            logger.warning(f"Helper: DocumentVersion ID {version_id} not found.")
            return None # Indicate not found
        elif version.document is None:  # type: ignore[comparison-overlap]
             # This case should be rare if FK constraints are working, but good to check
             logger.error(f"Helper: Data integrity issue - DocumentVersion {version_id} has no associated document.")
             # Treat as not found or raise an internal error? Returning None seems safer.
             return None
        else:
             logger.debug(f"Helper: Found DocumentVersion {version_id} (version string: '{version.version}')")
             return version # Return the found version object

    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error getting document version {version_id}: {e}", exc_info=True)
        # Re-raise or return None? Returning None to indicate failure to retrieve.
        return None
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error getting document version {version_id}: {e}", exc_info=True)
        return None
```

```python
# src/mcp_server_core.py
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

logger.info("Finished importing MCP tool modules.")

# Import memory and document tools to register them with the MCP instance
import src.mcp_memory_tools
import src.mcp_document_tools

# --- Tool Registration Logging Patches ---
# Patch FastMCP.add_tool for detailed logging
original_add_tool = FastMCP.add_tool
if original_add_tool is None:
    logger.warning("FastMCP.add_tool is None, skipping patching.")
    def logged_add_tool(self: Any, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> None:
        """Dummy logged_add_tool when original is None."""
        pass
else:
    def logged_add_tool(self: Any, fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> None:
        """Logs tool registration attempts via FastMCP.add_tool."""
        tool_name = name or getattr(fn, "__name__", "<unknown>")
        logger.info(f"Attempting to register MCP tool via FastMCP.add_tool: '{tool_name}'")
        logger.info(f"Using FastMCP instance at id {id(self)}")
        if hasattr(self, "_tool_manager"):
            logger.info(f"Targeting ToolManager instance at id {id(self._tool_manager)}")
        else:
            logger.warning("'_tool_manager' not found on FastMCP instance during add_tool call.")
        original_add_tool(self, fn, name=name, description=description)
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
# Ensure original_list_tools is callable; if not, assign a fallback.
if original_list_tools is None or not callable(original_list_tools):
    async def fallback_list_tools(self: FastMCP) -> Any:
        return []
    original_list_tools = fallback_list_tools

async def logged_list_tools(self: FastMCP) -> Any:
    """Logs listing of tools via FastMCP.list_tools with error handling."""
    try:
        potential = await original_list_tools(self)
    except Exception as e:
        logger.error(f"Error calling original_list_tools: {e}")
        potential = None
    tools = potential if potential is not None else []
    logger.info(f"Listing MCP tools: {[tool.name for tool in tools]}")
    return tools

FastMCP.list_tools = logged_list_tools
logger.info("Patched FastMCP.list_tools with logging.")

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
```

```python
# src/database.py
# src/database.py

import logging # Add logging import
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event # <--- Import event listener
from sqlalchemy.engine import Engine # <--- Import Engine for type hinting
from .config import settings # Import settings from config.py

logger = logging.getLogger(__name__) # <--- Add logger

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
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: ignore[reportGeneralTypeIssues]
AsyncSessionFactory = sessionmaker(
    bind=engine,  # Explicitly specify bind parameter with AsyncEngine
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for declarative models
Base = declarative_base()

# --- Dependency for FastAPI (keep as is) ---
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from typing import AsyncGenerator

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
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
            pass  # Session closed automatically by context manager

# Suppress Pylance false positives for AsyncSession async context manager
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false


## Mandatory Requirements for Gemini
- Provide a comprehensive analysis addressing the async context error.
- Ensure recommendations are compatible with the existing project architecture and dependencies.
- Avoid generic advice; focus on concrete, project-specific solutions.

## Request
Gemini, please assist with the above task. Write your response, adhering strictly to the mandatory requirements
