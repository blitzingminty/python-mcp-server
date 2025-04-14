# src/mcp_server_instance.py
# Defines the FastMCP server instance and its handlers.


import logging,time
from typing import Any, Dict, Optional, List, AsyncIterator
from contextlib import asynccontextmanager
import datetime


# --- SQLAlchemy Imports ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Added IntegrityError
from sqlalchemy.orm import selectinload

from .database import AsyncSessionFactory, Base, engine, get_db_session # Ensure get_db_session is imported if needed elsewhere, though not directly here for the tool

# Import Tag model
from .models import Project, Document, DocumentVersion, MemoryEntry, Tag, MemoryEntryRelation # Add MemoryEntryRelation

# --- SDK Imports ---
try:
    from mcp.server.fastmcp import FastMCP, Context
    # Import specific MCP types if needed for error handling or complex returns
    # from mcp import types as mcp_types
except ImportError as e:
    logging.critical(
        f"Failed to import from mcp.server.fastmcp: {e}. Please ensure 'mcp[cli]' is installed correctly.")
    raise

# --- Project Imports ---
from .config import settings
# Removed duplicate model import here

logger = logging.getLogger(__name__)


# --- Lifespan Management for Database ---

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
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
async def get_session(ctx: Context) -> AsyncSession:
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


# --- Existing DB Helper Functions ---

# --- Helper to get or create a tag (from previous MCP tool implementation) ---
async def _get_or_create_tag(session: AsyncSession, tag_name: str) -> Tag:
    """Helper function to get a Tag or create it if it doesn't exist."""
    stmt = select(Tag).where(Tag.name == tag_name)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if tag is None:
        logger.info(f"Tag '{tag_name}' not found, creating...")
        tag = Tag(name=tag_name)
        session.add(tag)
        # Flush to ensure the tag is persisted before associating
        # Needed if using the tag object immediately in the same transaction
        try:
            await session.flush()
            await session.refresh(tag) # Refresh after potential creation
            logger.info(f"Tag '{tag_name}' created or retrieved.")
        except IntegrityError: # Handle potential race condition if tag was created concurrently
            logger.warning(f"Tag '{tag_name}' likely created concurrently, retrieving existing.")
            await session.rollback() # Rollback the failed add
            # Fetch the now existing tag
            stmt = select(Tag).where(Tag.name == tag_name)
            result = await session.execute(stmt)
            tag = result.scalar_one() # Should exist now
        except SQLAlchemyError as e:
            logger.error(f"Database error getting/creating tag '{tag_name}': {e}", exc_info=True)
            raise # Re-raise other SQLAlchemy errors
    return tag


async def _create_project_in_db(
    session: AsyncSession,
    name: str,
    path: str,
    description: Optional[str],
    is_active: bool
) -> Project: # Return the created Project model instance
    """Core logic to create a project in the database."""
    logger.debug(f"Helper: Creating project '{name}' in DB.")
    new_project = Project(
        name=name,
        path=path,
        description=description,
        is_active=is_active
    )
    # Add to session (will be handled within transaction by caller)
    session.add(new_project)
    # Flush within the caller's transaction to get ID/defaults before returning object
    await session.flush()
    await session.refresh(new_project) # Refresh to get defaults like created_at
    logger.debug(f"Helper: Project created with ID {new_project.id}")
    return new_project

async def _update_project_in_db(
    session: AsyncSession,
    project_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    path: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Project | None: # Return updated Project or None if not found
    """Core logic to update a project in the database."""
    logger.debug(f"Helper: Updating project ID {project_id} in DB.")
    # Fetch the project first
    project = await session.get(Project, project_id)

    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for update.")
        return None # Indicate not found

    update_data = {
        "name": name, "description": description, "path": path, "is_active": is_active
    }
    updated = False
    for key, value in update_data.items():
        # Only update if the value is provided (not None) AND different from current value
        if value is not None and getattr(project, key) != value:
            setattr(project, key, value)
            updated = True

    if updated:
        logger.debug(f"Helper: Applying updates to project {project_id}.")
        # Ensure changes are flushed to DB within the caller's transaction
        await session.flush()
        await session.refresh(project) # Refresh to get updated timestamp etc.
    else:
        logger.debug(f"Helper: No changes detected for project {project_id}.")

    return project # Return the project object (updated or unchanged)

async def _delete_project_in_db(session: AsyncSession, project_id: int) -> bool:
    """
    Core logic to delete a project from the database.
    Returns True if deletion was successful or project didn't exist,
    False if a database error occurred during delete.
    """
    logger.debug(f"Helper: Deleting project ID {project_id} from DB.")
    project = await session.get(Project, project_id)

    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for deletion.")
        return True # Treat as success from caller's perspective (it's gone)

    try:
        await session.delete(project)
        await session.flush() # Ensure delete operation is executed within the transaction
        logger.info(f"Helper: Project ID {project_id} deleted.")
        return True
    except SQLAlchemyError as e:
        # Log the error, caller might handle transaction rollback
        logger.error(f"Helper: Database error deleting project {project_id}: {e}", exc_info=True)
        # Re-raise to ensure transaction rollback? Or return False?
        # Let's return False, caller handles redirect.
        return False

async def _set_active_project_in_db(session: AsyncSession, project_id: int) -> Project | None:
    """
    Core logic to set a project as active, deactivating others.
    Returns the activated project object if successful, None if the project wasn't found.
    Raises SQLAlchemyError on database issues during update.
    """
    logger.debug(f"Helper: Setting project ID {project_id} as active in DB.")
    # Get the project to activate
    project_to_activate = await session.get(Project, project_id)

    if project_to_activate is None:
        logger.warning(f"Helper: Project ID {project_id} not found to activate.")
        return None # Indicate not found

    # Find and deactivate currently active projects (if any)
    stmt = select(Project).where(Project.is_active == True, Project.id != project_id)
    result = await session.execute(stmt)
    currently_active_projects = result.scalars().all()

    updated = False
    for proj in currently_active_projects:
        logger.debug(f"Helper: Deactivating currently active project ID: {proj.id}")
        proj.is_active = False
        updated = True

    # Activate the target project if it's not already active
    if not project_to_activate.is_active:
        logger.debug(f"Helper: Activating project ID: {project_id}")
        project_to_activate.is_active = True
        updated = True
    else:
         logger.debug(f"Helper: Project ID: {project_id} was already active.")

    if updated:
        # Ensure changes are flushed within the caller's transaction
        await session.flush()
        # Refresh the specifically activated project if needed (e.g., to get updated_at)
        await session.refresh(project_to_activate)
    else:
        logger.debug(f"Helper: No change in active state for project {project_id}.")

    return project_to_activate # Return the target project object

async def _add_document_in_db(
    session: AsyncSession,
    project_id: int,
    name: str,
    path: str,
    content: str,
    type: str,
    version: str = "1.0.0" # Default version if not specified
) -> Document | None: # Return Document object or None if project not found
    """Core logic to add a document and its initial version to the database."""
    logger.debug(f"Helper: Adding document '{name}' to project {project_id}.")

    # Check if project exists
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project {project_id} not found for adding document.")
        return None # Indicate project not found

    # Create the new document
    new_document = Document(
        project_id=project_id,
        name=name,
        path=path,
        content=content, # Store initial content on document record
        type=type,
        version=version # Store initial version on document record
    )
    session.add(new_document)

    # Flush to get the new_document.id for the version record
    await session.flush()

    # Create the initial DocumentVersion entry
    new_version_entry = DocumentVersion(
        document_id=new_document.id,
        content=content,
        version=version
    )
    session.add(new_version_entry)

    # Refresh document to get defaults (like created_at) before returning
    await session.refresh(new_document)
    # We might also want the version ID, refresh it too
    await session.refresh(new_version_entry) # Add this line if needed

    logger.info(f"Helper: Document '{name}' (ID: {new_document.id}) added to project {project_id}.")
    # Optionally attach the initial version ID to the returned object if needed,
    # but the main function just needs the Document object.
    # setattr(new_document, 'initial_version_id', new_version_entry.id) # Example
    return new_document

async def _update_document_in_db(
    session: AsyncSession,
    document_id: int,
    name: Optional[str] = None,
    path: Optional[str] = None,
    type: Optional[str] = None,
    # Removed content and version - handle content updates separately maybe
) -> Document | None: # Return updated Document or None if not found
    """
    Core logic to update a document's metadata in the database.
    Does NOT handle content/version updates currently.
    """
    logger.debug(f"Helper: Updating metadata for document ID {document_id} in DB.")
    # Fetch the document first
    document = await session.get(Document, document_id)

    if document is None:
        logger.warning(f"Helper: Document ID {document_id} not found for update.")
        return None # Indicate not found

    update_data = {"name": name, "path": path, "type": type}
    updated = False
    for key, value in update_data.items():
        # Only update if the value is provided (not None) AND different from current value
        if value is not None and getattr(document, key) != value:
            setattr(document, key, value)
            updated = True

    if updated:
        logger.debug(f"Helper: Applying metadata updates to document {document_id}.")
        # Ensure changes are flushed to DB within the caller's transaction
        # updated_at should be handled by the model's onupdate
        await session.flush()
        await session.refresh(document) # Refresh to get updated timestamp etc.
    else:
        logger.debug(f"Helper: No metadata changes detected for document {document_id}.")

    return document # Return the document object (updated or unchanged)

async def _delete_document_in_db(session: AsyncSession, document_id: int) -> bool:
    """
    Core logic to delete a document from the database.
    Assumes cascade delete handles associated versions/tags appropriately.
    Returns True if deletion was successful or document didn't exist,
    False if a database error occurred during delete.
    """
    logger.debug(f"Helper: Deleting document ID {document_id} from DB.")
    # Load document with tags to allow cascade to work correctly before delete
    doc = await session.get(Document, document_id, options=[selectinload(Document.tags), selectinload(Document.versions)])

    if doc is None:
        logger.warning(f"Helper: Document ID {document_id} not found for deletion.")
        return True # Treat as success from caller's perspective (it's gone)

    try:
        await session.delete(doc)
        await session.flush() # Ensure delete operation is executed within the transaction
        logger.info(f"Helper: Document ID {document_id} ('{doc.name}') deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting document {document_id}: {e}", exc_info=True)
        return False


# --- NEW HELPER FUNCTION: Add Tag to Document ---
async def _add_tag_to_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool:
    """
    Core logic to add a tag to a document in the database.
    Returns True on success or if the tag already exists, False on document not found or DB error.
    """
    logger.debug(f"Helper: Adding tag '{tag_name}' to document ID {document_id} in DB.")
    try:
        # Fetch the document, eagerly loading tags to check for existence
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for adding tag '{tag_name}'.")
            return False # Indicate document not found

        # Use helper to get or create the tag
        tag = await _get_or_create_tag(session, tag_name)

        # Check if the tag is already associated
        if tag in document.tags:
            logger.info(f"Helper: Tag '{tag_name}' already exists on document {document_id}.")
            return True # Indicate success (already present)
        else:
            # Add the tag to the document's tag collection
            document.tags.add(tag)
            # Flush to ensure the association is persisted within the transaction
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' added to document {document_id}.")
            return True # Indicate success

    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False # Indicate database error
    except Exception as e:
        # Catch potential non-SQLAlchemy errors from _get_or_create_tag or elsewhere
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False # Indicate other error


# --- NEW HELPER FUNCTION: Remove Tag from Document ---
async def _remove_tag_from_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool:
    """
    Core logic to remove a tag from a document in the database.
    Returns True on success or if tag/document wasn't found, False on DB error.
    """
    logger.debug(f"Helper: Removing tag '{tag_name}' from document ID {document_id} in DB.")
    try:
        # Fetch the document, eagerly loading tags to find the one to remove
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for removing tag '{tag_name}'.")
            return True # Indicate success (document is gone, so tag is effectively removed)

        # Find the tag object within the document's current tags
        tag_to_remove = None
        for tag in document.tags:
            if tag.name == tag_name:
                tag_to_remove = tag
                break

        if tag_to_remove:
            # Remove the tag from the document's tag collection
            document.tags.remove(tag_to_remove)
            # Flush to ensure the association is removed within the transaction
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' removed from document {document_id}.")
            # Optionally check here if the Tag object itself should be deleted if orphaned
            return True # Indicate success
        else:
            logger.info(f"Helper: Tag '{tag_name}' was not found on document {document_id}.")
            return True # Indicate success (tag wasn't there anyway)

    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False # Indicate database error
    except Exception as e:
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False # Indicate other error

# --- Define MCP Tools using Decorators ---


@mcp_instance.tool()
async def list_projects(ctx: Context) -> Dict[str, Any]:
    """Lists all projects in the database."""
    logger.info("Handling list_projects request...")
    projects_data = []
    try:
        async with await get_session(ctx) as session:
            stmt = select(Project).order_by(Project.name)
            result = await session.execute(stmt)
            projects = result.scalars().all()
            for proj in projects:
                projects_data.append({
                    "id": proj.id,
                    "name": proj.name,
                    "description": proj.description,
                    "path": proj.path,
                    "is_active": proj.is_active,
                    "created_at": proj.created_at.isoformat() if proj.created_at else None,
                    "updated_at": proj.updated_at.isoformat() if proj.updated_at else None,
                })
        logger.info(f"Found {len(projects_data)} projects.")
        return {"projects": projects_data}
    except SQLAlchemyError as e:
        logger.error(f"Database error listing projects: {e}", exc_info=True)
        # Return an MCP-compatible error structure if possible
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing projects: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- MODIFIED MCP TOOL ---
@mcp_instance.tool()
async def create_project(
    name: str,
    path: str,
    description: Optional[str] = None,
    is_active: bool = False,
    ctx: Context = None  # Context is required by FastMCP to call the tool
) -> Dict[str, Any]:
    """Creates a new project in the database (MCP Tool Wrapper)."""
    logger.info(f"Handling create_project MCP tool request: name='{name}'")
    if not ctx:
        logger.error("Context (ctx) argument missing in create_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        # Get session using the context helper
        async with await get_session(ctx) as session:
            # Use a transaction
            async with session.begin():
                # Call the refactored helper function
                created_project = await _create_project_in_db(
                    session=session,
                    name=name,
                    path=path,
                    description=description,
                    is_active=is_active
                )

        # Format the success response for the MCP client
        logger.info(f"Project created successfully via MCP tool with ID: {created_project.id}")
        return {
            "message": "Project created successfully",
            "project": {
                "id": created_project.id,
                "name": created_project.name,
                "description": created_project.description,
                "path": created_project.path,
                "is_active": created_project.is_active,
                "created_at": created_project.created_at.isoformat() if created_project.created_at else None,
                "updated_at": created_project.updated_at.isoformat() if created_project.updated_at else None,
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error creating project via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error creating project via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def get_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Gets details for a specific project by its ID."""
    logger.info(f"Handling get_project request for ID: {project_id}")
    try:
        async with await get_session(ctx) as session:
            # Use session.get for efficient primary key lookup
            project = await session.get(Project, project_id)

            if project is None:
                logger.warning(f"Project with ID {project_id} not found.")
                return {"error": f"Project with ID {project_id} not found"}

            logger.info(f"Found project: {project.name}")
            return {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "path": project.path,
                    "is_active": project.is_active,
                    "created_at": project.created_at.isoformat() if project.created_at else None,
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                }
            }
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error getting project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def update_project(
    project_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    path: Optional[str] = None,
    is_active: Optional[bool] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """Updates fields for a specific project (MCP Tool Wrapper)."""
    logger.info(f"Handling update_project MCP tool request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in update_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session: # Get session via context
            async with session.begin(): # Use transaction
                # Call the refactored helper function
                updated_project = await _update_project_in_db(
                    session=session,
                    project_id=project_id,
                    name=name,
                    description=description,
                    path=path,
                    is_active=is_active
                )

        if updated_project is None:
             # Project not found by helper
             logger.warning(f"MCP Tool: Project with ID {project_id} not found for update.")
             return {"error": f"Project with ID {project_id} not found"}

        # Format the success response for the MCP client
        logger.info(f"Project {project_id} updated successfully via MCP tool.")
        return {
            "message": "Project updated successfully",
            "project": {
                 "id": updated_project.id,
                "name": updated_project.name,
                "description": updated_project.description,
                "path": updated_project.path,
                "is_active": updated_project.is_active,
                "created_at": updated_project.created_at.isoformat() if updated_project.created_at else None,
                 "updated_at": updated_project.updated_at.isoformat() if updated_project.updated_at else None,
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error updating project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error updating project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def delete_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Deletes a specific project by its ID (MCP Tool Wrapper)."""
    logger.info(f"Handling delete_project MCP tool request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in delete_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session: # Get session via context
             async with session.begin(): # Use transaction
                deleted = await _delete_project_in_db(session, project_id)

        if deleted:
            logger.info(f"Project {project_id} deleted successfully via MCP tool.")
            return {"message": f"Project ID {project_id} deleted successfully"}
        else:
            # This case might be hard to reach if helper re-raises,
            # but good practice to handle.
            logger.error(f"MCP Tool: Failed to delete project {project_id} due to database error during delete.")
            # Error already logged by helper
            return {"error": "Database error during project deletion"}

    except SQLAlchemyError as e:
        # Catch errors during session/transaction setup or commit
        logger.error(f"Database error processing delete_project tool for {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing delete_project tool for {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def set_active_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Sets a specific project as active, deactivating all others (MCP Tool Wrapper)."""
    logger.info(f"Handling set_active_project MCP tool request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in set_active_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session: # Get session via context
            async with session.begin(): # Use transaction
                # Call the refactored helper function
                activated_project = await _set_active_project_in_db(session, project_id)

        if activated_project is None:
             # Project not found by helper
             logger.warning(f"MCP Tool: Project with ID {project_id} not found to activate.")
             return {"error": f"Project with ID {project_id} not found"}

        # Format the success response for the MCP client
        logger.info(f"Project {project_id} is now the active project (via MCP tool).")
        return {
             "message": f"Project ID {project_id} set as active",
            "project": { # Return some basic info
                "id": activated_project.id,
                "name": activated_project.name,
                "is_active": activated_project.is_active,
                # Add other fields if needed by MCP clients
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error setting active project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error setting active project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def add_document(
    project_id: int,
    name: str,
    path: str,
    content: str,
    type: str,
    version: str = "1.0.0", # Default version for initial add
    ctx: Context = None
) -> Dict[str, Any]:
    """Adds a new document to a specified project (MCP Tool Wrapper)."""
    logger.info(f"Handling add_document MCP tool request for project ID: {project_id}, name: {name}")
    if not ctx:
        logger.error("Context (ctx) argument missing in add_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session: # Get session via context
            async with session.begin(): # Use transaction
                # Call the refactored helper function
                added_document = await _add_document_in_db(
                    session=session,
                    project_id=project_id,
                    name=name,
                    path=path,
                    content=content,
                    type=type,
                    version=version
                )

        if added_document is None:
             # Project not found by helper
             logger.warning(f"MCP Tool: Project with ID {project_id} not found for adding document.")
             return {"error": f"Project with ID {project_id} not found"}

        # Format the success response for the MCP client
        logger.info(f"Document '{name}' (ID: {added_document.id}) added successfully via MCP tool.")
        return {
            "message": "Document added successfully",
            "document": { # Return basic info
                 "id": added_document.id,
                "project_id": added_document.project_id,
                "name": added_document.name,
                "path": added_document.path,
                "type": added_document.type,
                "version": added_document.version,
                 "created_at": added_document.created_at.isoformat() if added_document.created_at else None,
                "updated_at": added_document.updated_at.isoformat() if added_document.updated_at else None,
                # Add initial_version_id if needed
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error adding document to project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error adding document to project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_documents_for_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all documents associated with a specific project."""
    logger.info(
        f"Handling list_documents_for_project request for project ID: {project_id}")
    documents_data = []
    try:
        async with await get_session(ctx) as session:
            # Verify project exists first (optional, but good practice)
            project = await session.get(Project, project_id)
            if project is None:
                logger.warning(
                    f"Project with ID {project_id} not found for listing documents.")
                return {"error": f"Project with ID {project_id} not found"}

            # Query documents for the project
            stmt = select(Document).where(Document.project_id ==
                                          project_id).order_by(Document.name)
            result = await session.execute(stmt)
            documents = result.scalars().all()
            for doc in documents:
                documents_data.append({
                    "id": doc.id,
                     "project_id": doc.project_id,
                    "name": doc.name,
                    "path": doc.path,
                    "type": doc.type,
                    "version": doc.version,  # Current version stored on Document
                     "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                })
        logger.info(
            f"Found {len(documents_data)} documents for project {project_id}.")
        return {"documents": documents_data}
    except SQLAlchemyError as e:
        logger.error(
            f"Database error listing documents for project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error listing documents for project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_document_versions(document_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all historical versions available for a specific document."""
    start_time = time.time() # <-- Start timer
    logger.info(f"Handling list_document_versions request for document ID: {document_id}")
    versions_data = []
    try:
        async with await get_session(ctx) as session:
             # Fetch the document and eagerly load its versions, ordered
             # Order by created_at descending to get newest first, or version string if comparable
             stmt = select(Document).options(
                 selectinload(Document.versions)
             ).where(Document.id == document_id)
             result = await session.execute(stmt)
             document = result.scalar_one_or_none()

             if document is None:
                 logger.warning(f"Document {document_id} not found for listing versions.")
                 return {"error": f"Document {document_id} not found"}

             # Sort versions here if not done in the query's order_by
             # sorted_versions = sorted(document.versions, key=lambda v: v.created_at, reverse=True)
             sorted_versions = sorted(document.versions, key=lambda v: v.id) # Sort by ID for consistency maybe

             for version in sorted_versions:
                 versions_data.append({
                     "version_id": version.id, # The unique ID of the version record
                     "document_id": version.document_id,
                      "version_string": version.version, # The version name/number (e.g., "1.0.0", "2.1")
                     "created_at": version.created_at.isoformat() if version.created_at else None,
                     # Optionally add a flag if this is the 'current' version on the parent Document
                     "is_current": version.version == document.version
                 })

        logger.info(f"Found {len(versions_data)} versions for document {document_id}.")
        end_time = time.time() # <-- End timer
        logger.info(f"list_document_versions for doc {document_id} took {end_time - start_time:.4f} seconds.") # <-- Log duration
        return {"versions": versions_data}

    except SQLAlchemyError as e:
        logger.error(f"Database error listing versions for document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing versions for document {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool() # Changed from .resource("document_version://{version_id}")
async def get_document_version_content(version_id: int, ctx: Context = None) -> Dict[str, Any]: # Added ctx
    """Tool handler to get the content of a specific document version by its ID.""" # Docstring updated
    logger.info(f"Handling get_document_version_content TOOL request for version ID: {version_id}")
    if not ctx:
        # Although marked optional, tools should receive ctx from FastMCP
        logger.error("Context (ctx) argument missing in get_document_version_content call.")
        return {"error": "Internal server error: Context missing."}
    try:
        # Use the get_session helper now that ctx is available
        async with await get_session(ctx) as session:
            logger.debug(f"Session obtained for get_document_version_content {version_id}")
            # Fetch the specific version, need to load related document for mime_type
            stmt = select(DocumentVersion).options(
                selectinload(DocumentVersion.document) # Eager load parent document
            ).where(DocumentVersion.id == version_id)
            result = await session.execute(stmt)
            version = result.scalar_one_or_none()
            # Alternatively: version = await session.get(DocumentVersion, version_id, options=[selectinload(DocumentVersion.document)])

            if version is None:
                logger.warning(f"DocumentVersion with ID {version_id} not found for tool request.")
                return {"error": f"DocumentVersion {version_id} not found"}

            if version.document is None:
                logger.error(f"DocumentVersion {version_id} has no associated document loaded.")
                return {"error": f"Data integrity error for version {version_id}"}

            logger.info(f"Found document version '{version.version}' (ID: {version_id}), returning content.")
            # Return result wrapped in a "result" key for tool convention
            return {
                "result": { # <-- Wrap result for tool
                    "content": version.content,
                    "mime_type": version.document.type,
                    "version_string": version.version,
                    "document_id": version.document_id
                }
            }
    except SQLAlchemyError as e:
        logger.error(f"Database error getting document version {version_id}: {e}", exc_info=True)
        return {"error": f"Database error getting document version content"}
    except Exception as e:
        logger.error(f"Unexpected error getting document version {version_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error processing tool"}


@mcp_instance.resource("document://{document_id}") # Define URI pattern
async def get_document_content(document_id: int) -> Dict[str, Any]: # No ctx here
    """Resource handler to get the content of a specific document."""
    logger.info(f"Handling get_document_content resource request for document ID: {document_id}")
    # Create session directly from the imported factory
    session: Optional[AsyncSession] = None # Define session variable outside try
    try:
        session = AsyncSessionFactory() # Create a new session
        logger.debug(f"Session created for get_document_content {document_id}")
        document = await session.get(Document, document_id)

        if document is None:
            logger.warning(f"Document with ID {document_id} not found for resource request.")
            return {"error": f"Document {document_id} not found"}

        logger.info(f"Found document '{document.name}', returning content.")
        # Resources typically return content and mime_type
        return {
            "content": document.content,
            "mime_type": document.type
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error getting document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error getting document content"}
    except Exception as e:
        logger.error(f"Unexpected error getting document {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error processing resource"}
    finally:
        # Ensure the session is closed if it was successfully created
        if session:
            await session.close()
            logger.debug(f"Session closed for get_document_content {document_id}")


@mcp_instance.tool()
async def update_document(
    document_id: int,
    name: Optional[str] = None,
    path: Optional[str] = None,
    content: Optional[str] = None, # Keep content/version args for MCP compatibility
    type: Optional[str] = None,
    version: Optional[str] = None, # If provided, creates a new version
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Updates fields for a specific document (MCP Tool Wrapper).
    If content or version is provided, attempts to create a new DocumentVersion.
    Otherwise, updates metadata fields (name, path, type).
    """
    logger.info(f"Handling update_document MCP tool request for ID: {document_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in update_document call.")
        return {"error": "Internal server error: Context missing."}

    # --- Logic to handle content/version update (Creating new DocumentVersion) ---
    # This part requires careful implementation: check version conflicts, etc.
    # For now, we'll focus the helper and web route on metadata only.
    # We *could* call the helper first for metadata, then handle versioning.
    if content is not None and version is not None:
        logger.warning(f"MCP Tool: Content/version update for doc {document_id} requested - NOT YET FULLY IMPLEMENTED IN HELPER/WEB UI.")
        # --- Placeholder for future implementation ---
        # 1. Check if version already exists?
        # 2. Create new DocumentVersion record
        # 3. Update main Document record's content and version fields
        # 4. Handle potential errors
        # --- End Placeholder ---
        # For now, return an error or unimplemented message for the MCP client
        return {"error": "Content/version updates via this tool are not fully implemented yet."}
        # OR proceed to update metadata only if that's desired alongside versioning later

    # --- Logic to handle metadata update ---
    try:
        async with await get_session(ctx) as session: # Get session via context
            async with session.begin(): # Use transaction
                # Call the refactored helper function for metadata
                updated_document = await _update_document_in_db(
                    session=session,
                    document_id=document_id,
                    name=name,
                    path=path,
                    type=type
                )

        if updated_document is None:
             # Project not found by helper
             logger.warning(f"MCP Tool: Document with ID {document_id} not found for metadata update.")
             return {"error": f"Document with ID {document_id} not found"}

        # Format the success response for the MCP client
        logger.info(f"Document {document_id} metadata updated successfully via MCP tool.")
        response_doc = {
            "id": updated_document.id, "project_id": updated_document.project_id,
            "name": updated_document.name, "path": updated_document.path,
            "type": updated_document.type, "version": updated_document.version, # Reflect current version
            "created_at": updated_document.created_at.isoformat() if updated_document.created_at else None,
            "updated_at": updated_document.updated_at.isoformat() if updated_document.updated_at else None,
        }
        return {
            "message": "Document metadata updated successfully",
            "document": response_doc
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error updating document {document_id} metadata via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error updating document {document_id} metadata via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def delete_document(document_id: int, ctx: Context) -> Dict[str, Any]:
    """Deletes a specific document by its ID and its associated versions (MCP Tool Wrapper)."""
    logger.info(f"Handling delete_document MCP tool request for ID: {document_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in delete_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session: # Get session via context
            async with session.begin(): # Use transaction
                deleted = await _delete_document_in_db(session, document_id)

        if deleted:
            logger.info(f"Document {document_id} deleted successfully via MCP tool.")
            return {"message": f"Document ID {document_id} deleted successfully"}
        else:
            logger.error(f"MCP Tool: Failed to delete document {document_id} due to database error during delete.")
            return {"error": "Database error during document deletion"}

    except SQLAlchemyError as e:
        logger.error(f"Database error processing delete_document tool for {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing delete_document tool for {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Add the following Memory Entry Tools ---

@mcp_instance.tool()
async def add_memory_entry(
    project_id: int,
    type: str,  # e.g., 'note', 'chat_snippet', 'user_preference'
    title: str,
    content: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """Adds a new memory entry to a specified project."""
    logger.info(
        f"Handling add_memory_entry request for project ID: {project_id}, title: {title}")
    if not ctx:
        logger.error(
            "Context (ctx) argument missing in add_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                # Verify project exists
                project = await session.get(Project, project_id)
                if project is None:
                    logger.warning(
                        f"Project with ID {project_id} not found for adding memory entry.")
                    return {"error": f"Project with ID {project_id} not found"}

                # Create the new memory entry
                new_entry = MemoryEntry(
                    project_id=project_id,
                    type=type,
                    title=title,
                    content=content
                    # created_at/updated_at have defaults
                )
                session.add(new_entry)
                # Refresh to get generated ID and defaults
                await session.flush()
                await session.refresh(new_entry)

            # Commit happens automatically

        logger.info(
            f"Memory entry '{title}' (ID: {new_entry.id}) added successfully to project {project_id}.")
        return {
             "message": "Memory entry added successfully",
            "memory_entry": {
                "id": new_entry.id,
                "project_id": new_entry.project_id,
                "type": new_entry.type,
                "title": new_entry.title,
                 # Avoid sending potentially large content back unless necessary
                # "content": new_entry.content,
                "created_at": new_entry.created_at.isoformat() if new_entry.created_at else None,
                "updated_at": new_entry.updated_at.isoformat() if new_entry.updated_at else None,
            }
        }
    except SQLAlchemyError as e:
         logger.error(
            f"Database error adding memory entry to project {project_id}: {e}", exc_info=True)
         return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error adding memory entry to project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_memory_entries(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all memory entries associated with a specific project."""
    logger.info(
        f"Handling list_memory_entries request for project ID: {project_id}")
    entries_data = []
    try:
        async with await get_session(ctx) as session:
            # Verify project exists first
            project = await session.get(Project, project_id)
            if project is None:
                 logger.warning(
                    f"Project with ID {project_id} not found for listing memory entries.")
                 return {"error": f"Project with ID {project_id} not found"}

            # Query memory entries for the project
            stmt = select(MemoryEntry).where(MemoryEntry.project_id ==
                                              project_id).order_by(MemoryEntry.updated_at.desc())
            result = await session.execute(stmt)
            entries = result.scalars().all()
            for entry in entries:
                 entries_data.append({
                    "id": entry.id,
                    "project_id": entry.project_id,
                    "type": entry.type,
                    "title": entry.title,
                    # "content": entry.content, # Maybe only return summary/preview?
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                })
        logger.info(
            f"Found {len(entries_data)} memory entries for project {project_id}.")
        return {"memory_entries": entries_data}
    except SQLAlchemyError as e:
        logger.error(
            f"Database error listing memory entries for project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error listing memory entries for project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def get_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    """Gets details for a specific memory entry by its ID."""
    logger.info(f"Handling get_memory_entry request for ID: {memory_entry_id}")
    try:
        async with await get_session(ctx) as session:
            entry = await session.get(MemoryEntry, memory_entry_id)

            if entry is None:
                logger.warning(
                    f"MemoryEntry with ID {memory_entry_id} not found.")
                return {"error": f"MemoryEntry with ID {memory_entry_id} not found"}

            logger.info(f"Found memory entry: {entry.title}")
            # Return the full entry data, including content
            return {
                "memory_entry": {
                     "id": entry.id,
                    "project_id": entry.project_id,
                    "type": entry.type,
                    "title": entry.title,
                    "content": entry.content,  # Include content for get
                     "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                    # TODO: Add related documents, tags, relations later
                }
             }
    except SQLAlchemyError as e:
        logger.error(
            f"Database error getting memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error getting memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Corrected Indentation ---
@mcp_instance.tool()
async def update_memory_entry(
    memory_entry_id: int,
    type: Optional[str] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """Updates fields for a specific memory entry."""
    logger.info(
        f"Handling update_memory_entry request for ID: {memory_entry_id}")
    if not ctx:
        logger.error(
            "Context (ctx) argument missing in update_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                entry = await session.get(MemoryEntry, memory_entry_id)

                if entry is None:
                    logger.warning(
                        f"MemoryEntry with ID {memory_entry_id} not found for update.")
                    return {"error": f"MemoryEntry with ID {memory_entry_id} not found"}

                # Collect fields to update
                update_data = {"type": type,
                               "title": title, "content": content}
                updated = False
                for key, value in update_data.items():
                    if value is not None and getattr(entry, key) != value:
                        setattr(entry, key, value)
                        # Ensure this line is indented correctly under the 'if'
                        updated = True

                if not updated:
                    logger.info(
                        f"No fields provided or values matched current state for memory entry {memory_entry_id}.")
                    await session.refresh(entry)
                    return {
                        "message": "No update applied to memory entry",
                         "memory_entry": {
                            "id": entry.id,
                            "title": entry.title,
                             "project_id": entry.project_id,
                            "type": entry.type,
                            "created_at": entry.created_at.isoformat() if entry.created_at else None,
                            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                        }  # Return current state (content omitted for brevity)
                    }
                # This block executes only if 'updated' is True
                logger.info(f"Updating memory entry ID: {memory_entry_id}")
                await session.flush()
                await session.refresh(entry)  # Get updated timestamp etc.

            # Transaction commits here (if successful)
            logger.info(
                f"Memory entry {memory_entry_id} updated successfully.")
            # This return is outside the 'async with session.begin()'
            # but inside 'async with await get_session(ctx) as session:'
            # Indentation needs care if restructuring
            # Assuming it should return the updated entry state after successful commit:
            return {
                "message": "Memory entry updated successfully",
                 "memory_entry": {
                    "id": entry.id, "project_id": entry.project_id, "type": entry.type,
                    "title": entry.title,  # "content": entry.content, # Maybe omit content?
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                }
            }

    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error updating memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}
# --- End Corrected Indentation ---


@mcp_instance.tool()
async def delete_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    """Deletes a specific memory entry by its ID."""
    logger.info(
        f"Handling delete_memory_entry request for ID: {memory_entry_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in delete_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                entry = await session.get(MemoryEntry, memory_entry_id)

                if entry is None:
                    logger.warning(
                         f"MemoryEntry with ID {memory_entry_id} not found for deletion.")
                    return {"error": f"MemoryEntry with ID {memory_entry_id} not found"}

                logger.info(
                    f"Deleting memory entry ID: {memory_entry_id} ('{entry.title}')")
                await session.delete(entry)
                 # Cascaded deletes for relations/tags should happen automatically if configured correctly in model/DB
            # Commit happens automatically

        logger.info(f"Memory entry {memory_entry_id} deleted successfully.")
        return {"message": f"Memory entry ID {memory_entry_id} deleted successfully"}

    except SQLAlchemyError as e:
        logger.error(
            f"Database error deleting memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error deleting memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Add the following Tagging Tools ---

# --- MODIFIED MCP TOOL: Use DB Helper ---
@mcp_instance.tool()
async def add_tag_to_document(document_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    """Adds a tag to a specific document (MCP Tool Wrapper)."""
    logger.info(f"Handling MCP tool add_tag_to_document request for doc ID: {document_id}, tag: {tag_name}")
    if not ctx:
        logger.error("Context (ctx) argument missing in add_tag_to_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Call the refactored database helper function
                success = await _add_tag_to_document_db(session, document_id, tag_name)

            # Check the result from the helper
            if success:
                logger.info(f"MCP Tool: Tag '{tag_name}' added/already present on document {document_id}.")
                # Message adjusted to reflect it might have existed
                return {"message": f"Tag '{tag_name}' associated with document {document_id}"}
            else:
                # Helper returned False, likely document not found or DB error (already logged by helper)
                logger.error(f"MCP Tool: Failed to add tag '{tag_name}' to document {document_id}.")
                # Determine specific error? For now, generic failure. Helper logs specifics.
                # Check if doc exists first to provide better error?
                doc_exists = await session.get(Document, document_id) # This needs to be outside the transaction begin() block
                if doc_exists is None:
                     return {"error": f"Document {document_id} not found"}
                else:
                     return {"error": f"Database error adding tag '{tag_name}' to document {document_id}"}

    except SQLAlchemyError as e: # Catch errors during session/transaction setup/commit
        logger.error(f"Database error processing add_tag_to_document tool for {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing add_tag_to_document tool for {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- MODIFIED MCP TOOL: Use DB Helper ---
@mcp_instance.tool()
async def remove_tag_from_document(document_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    """Removes a tag from a specific document (MCP Tool Wrapper)."""
    logger.info(f"Handling MCP tool remove_tag_from_document request for doc ID: {document_id}, tag: {tag_name}")
    if not ctx:
        logger.error("Context (ctx) argument missing in remove_tag_from_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Call the refactored database helper function
                success = await _remove_tag_from_document_db(session, document_id, tag_name)

            # Check the result from the helper
            if success:
                # Helper returns True if removed OR if tag/doc wasn't found
                logger.info(f"MCP Tool: Tag '{tag_name}' removed or was not present on document {document_id}.")
                return {"message": f"Tag '{tag_name}' disassociated from document {document_id}"}
            else:
                # Helper returned False, indicating a database error during removal (already logged by helper)
                logger.error(f"MCP Tool: Failed to remove tag '{tag_name}' from document {document_id} due to DB error.")
                return {"error": f"Database error removing tag '{tag_name}' from document {document_id}"}

    except SQLAlchemyError as e: # Catch errors during session/transaction setup/commit
        logger.error(f"Database error processing remove_tag_from_document tool for {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing remove_tag_from_document tool for {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_tags_for_document(document_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all tags associated with a specific document."""
    logger.info(f"Handling list_tags_for_document request for doc ID: {document_id}")
    tag_names = []
    if not ctx:
        logger.error("Context (ctx) argument missing in list_tags_for_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
             # Load the document and its tags efficiently
             stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
             result = await session.execute(stmt)
             document = result.scalar_one_or_none()

             if document is None:
                 logger.warning(f"Document {document_id} not found for listing tags.")
                 return {"error": f"Document {document_id} not found"}

             tag_names = sorted([tag.name for tag in document.tags]) # Get names from Tag objects

        logger.info(f"Found {len(tag_names)} tags for document {document_id}.")
        return {"tags": tag_names}
    except SQLAlchemyError as e:
        logger.error(f"Database error listing tags for document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing tags for document {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Add the following Memory Entry Tagging Tools ---

@mcp_instance.tool()
async def add_tag_to_memory_entry(memory_entry_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    """Adds a tag to a specific memory entry."""
    logger.info(f"Handling add_tag_to_memory_entry request for entry ID: {memory_entry_id}, tag: {tag_name}")
    if not ctx:
        logger.error("Context (ctx) argument missing in add_tag_to_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Use selectinload to efficiently load tags if checking for existence
                stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == memory_entry_id)
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()

                if entry is None:
                    logger.warning(f"MemoryEntry {memory_entry_id} not found for adding tag.")
                    return {"error": f"MemoryEntry {memory_entry_id} not found"}

                # Use the helper to get or create the tag
                tag = await _get_or_create_tag(session, tag_name)

                if tag in entry.tags:
                    logger.info(f"Tag '{tag_name}' already exists on memory entry {memory_entry_id}.")
                    return {"message": "Tag already exists on memory entry"}
                else:
                    entry.tags.add(tag) # Add the Tag object to the relationship set
                    logger.info(f"Tag '{tag_name}' added to memory entry {memory_entry_id}.")

            # Commit successful
        return {"message": f"Tag '{tag_name}' added to memory entry {memory_entry_id}"}
    except SQLAlchemyError as e:
        logger.error(f"Database error adding tag to memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error adding tag to memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def remove_tag_from_memory_entry(memory_entry_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    """Removes a tag from a specific memory entry."""
    logger.info(f"Handling remove_tag_from_memory_entry request for entry ID: {memory_entry_id}, tag: {tag_name}")
    if not ctx:
        logger.error("Context (ctx) argument missing in remove_tag_from_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Load the entry and its tags efficiently
                stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == memory_entry_id)
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()

                if entry is None:
                    logger.warning(f"MemoryEntry {memory_entry_id} not found for removing tag.")
                    return {"error": f"MemoryEntry {memory_entry_id} not found"}

                # Find the tag object within the entry's tags
                tag_to_remove = None
                for tag in entry.tags:
                    if tag.name == tag_name:
                        tag_to_remove = tag
                        break

                if tag_to_remove:
                    entry.tags.remove(tag_to_remove) # Remove Tag object from relationship set
                    logger.info(f"Tag '{tag_name}' removed from memory entry {memory_entry_id}.")
                else:
                    logger.warning(f"Tag '{tag_name}' not found on memory entry {memory_entry_id}.")
                    return {"message": "Tag not found on memory entry"}

            # Commit successful
        return {"message": f"Tag '{tag_name}' removed from memory entry {memory_entry_id}"}
    except SQLAlchemyError as e:
         logger.error(f"Database error removing tag from memory entry {memory_entry_id}: {e}", exc_info=True)
         return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error removing tag from memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def list_tags_for_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all tags associated with a specific memory entry."""
    logger.info(f"Handling list_tags_for_memory_entry request for entry ID: {memory_entry_id}")
    tag_names = []
    if not ctx:
        logger.error("Context (ctx) argument missing in list_tags_for_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
             # Load the entry and its tags efficiently
             stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == memory_entry_id)
             result = await session.execute(stmt)
             entry = result.scalar_one_or_none()

             if entry is None:
                  logger.warning(f"MemoryEntry {memory_entry_id} not found for listing tags.")
                  return {"error": f"MemoryEntry {memory_entry_id} not found"}

             tag_names = sorted([tag.name for tag in entry.tags]) # Get names from Tag objects

        logger.info(f"Found {len(tag_names)} tags for memory entry {memory_entry_id}.")
        return {"tags": tag_names}
    except SQLAlchemyError as e:
         logger.error(f"Database error listing tags for memory entry {memory_entry_id}: {e}", exc_info=True)
         return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing tags for memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Add the following Relationship Management Tools ---

@mcp_instance.tool()
async def link_memory_entry_to_document(memory_entry_id: int, document_id: int, ctx: Context) -> Dict[str, Any]:
    """Links an existing Memory Entry to an existing Document."""
    logger.info(f"Handling link_memory_entry_to_document request for entry ID: {memory_entry_id} and doc ID: {document_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in link_memory_entry_to_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Fetch both objects, load the relationship collection for checking
                entry_stmt = select(MemoryEntry).options(selectinload(MemoryEntry.documents)).where(MemoryEntry.id == memory_entry_id)
                entry_res = await session.execute(entry_stmt)
                entry = entry_res.scalar_one_or_none()

                document = await session.get(Document, document_id)

                if entry is None:
                    return {"error": f"MemoryEntry {memory_entry_id} not found"}
                if document is None:
                    return {"error": f"Document {document_id} not found"}

                # Check if the relationship already exists
                if document in entry.documents:
                     logger.info(f"Document {document_id} is already linked to MemoryEntry {memory_entry_id}.")
                     return {"message": "Link already exists"}
                else:
                    # Append the Document object to the MemoryEntry's documents collection
                    entry.documents.append(document)
                     # SQLAlchemy handles the insert into the association table
                    logger.info(f"Linked Document {document_id} to MemoryEntry {memory_entry_id}.")
                    # session.add(entry) # Usually implicit when modifying loaded object

            # Commit successful
        return {"message": f"Linked document {document_id} to memory entry {memory_entry_id}"}
    except SQLAlchemyError as e:
        logger.error(f"Database error linking memory entry {memory_entry_id} to doc {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error linking memory entry {memory_entry_id} to doc {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_documents_for_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all documents linked to a specific memory entry."""
    logger.info(f"Handling list_documents_for_memory_entry request for entry ID: {memory_entry_id}")
    documents_data = []
    if not ctx:
        logger.error("Context (ctx) argument missing in list_documents_for_memory_entry call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
             # Fetch the entry and eagerly load its linked documents
             stmt = select(MemoryEntry).options(selectinload(MemoryEntry.documents)).where(MemoryEntry.id == memory_entry_id)
             result = await session.execute(stmt)
             entry = result.scalar_one_or_none()

             if entry is None:
                 logger.warning(f"MemoryEntry {memory_entry_id} not found for listing documents.")
                 return {"error": f"MemoryEntry {memory_entry_id} not found"}

             for doc in entry.documents: # Iterate through the loaded documents relationship
                 documents_data.append({
                      "id": doc.id,
                     "name": doc.name,
                     "path": doc.path,
                     "type": doc.type,
                      "version": doc.version,
                     "created_at": doc.created_at.isoformat() if doc.created_at else None,
                     "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                 })

        logger.info(f"Found {len(documents_data)} linked documents for memory entry {memory_entry_id}.")
        return {"linked_documents": documents_data}
    except SQLAlchemyError as e:
        logger.error(f"Database error listing documents for memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing documents for memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def link_memory_entries(
    source_memory_entry_id: int,
    target_memory_entry_id: int,
    relation_type: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """Creates a relationship link between two memory entries."""
    logger.info(f"Handling link_memory_entries request from {source_memory_entry_id} to {target_memory_entry_id} (type: {relation_type})")
    if not ctx:
         logger.error("Context (ctx) argument missing in link_memory_entries call.")
         return {"error": "Internal server error: Context missing."}
    if source_memory_entry_id == target_memory_entry_id:
         return {"error": "Cannot link a memory entry to itself"}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Verify both entries exist
                source_entry = await session.get(MemoryEntry, source_memory_entry_id)
                target_entry = await session.get(MemoryEntry, target_memory_entry_id)

                if source_entry is None:
                    return {"error": f"Source MemoryEntry {source_memory_entry_id} not found"}
                if target_entry is None:
                    return {"error": f"Target MemoryEntry {target_memory_entry_id} not found"}

                # Check if this specific relationship already exists (optional, depends on requirements)
                # stmt_exists = select(MemoryEntryRelation).where(
                #     MemoryEntryRelation.source_memory_entry_id == source_memory_entry_id,
                #     MemoryEntryRelation.target_memory_entry_id == target_memory_entry_id,
                #     MemoryEntryRelation.relation_type == relation_type
                # )
                # existing_relation = await session.scalar(stmt_exists)
                # if existing_relation:
                #     logger.info("Relationship already exists.")
                #     return {"message": "Relationship already exists", "relation_id": existing_relation.id}


                 # Create the new relationship entry
                new_relation = MemoryEntryRelation(
                    source_memory_entry_id=source_memory_entry_id,
                    target_memory_entry_id=target_memory_entry_id,
                    relation_type=relation_type
                 )
                session.add(new_relation)
                await session.flush() # Ensure ID is available
                await session.refresh(new_relation)

            # Commit successful
        logger.info(f"Linked MemoryEntry {source_memory_entry_id} to {target_memory_entry_id}. Relation ID: {new_relation.id}")
        return {
             "message": "Memory entries linked successfully",
             "relation": {
                 "id": new_relation.id,
                 "source_id": new_relation.source_memory_entry_id,
                 "target_id": new_relation.target_memory_entry_id,
                 "type": new_relation.relation_type,
                 "created_at": new_relation.created_at.isoformat() if new_relation.created_at else None,
             }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error linking memory entries {source_memory_entry_id} -> {target_memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error linking memory entries {source_memory_entry_id} -> {target_memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_related_memory_entries(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists memory entries related TO and FROM the specified memory entry."""
    logger.info(f"Handling list_related_memory_entries request for entry ID: {memory_entry_id}")
    relations_from = []
    relations_to = []
    if not ctx:
        logger.error("Context (ctx) argument missing in list_related_memory_entries call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
              # Fetch the entry and eagerly load its relations
             # We need to load the related entries themselves via the relation object
             stmt = select(MemoryEntry).options(
                 selectinload(MemoryEntry.source_relations).options(selectinload(MemoryEntryRelation.target_entry)),
                 selectinload(MemoryEntry.target_relations).options(selectinload(MemoryEntryRelation.source_entry))
             ).where(MemoryEntry.id == memory_entry_id)
             result = await session.execute(stmt)
             entry = result.scalar_one_or_none()

             if entry is None:
                 logger.warning(f"MemoryEntry {memory_entry_id} not found for listing relations.")
                 return {"error": f"MemoryEntry {memory_entry_id} not found"}

              # Relations *from* this entry (entry is the source)
             for rel in entry.source_relations:
                 if rel.target_entry: # Check if target entry loaded correctly
                     relations_from.append({
                         "relation_id": rel.id,
                         "relation_type": rel.relation_type,
                         "target_entry_id": rel.target_memory_entry_id,
                         "target_entry_title": rel.target_entry.title, # Access related object
                         "created_at": rel.created_at.isoformat() if rel.created_at else None,
                     })

             # Relations *to* this entry (entry is the target)
             for rel in entry.target_relations:
                 if rel.source_entry: # Check if source entry loaded correctly
                     relations_to.append({
                         "relation_id": rel.id,
                         "relation_type": rel.relation_type,
                         "source_entry_id": rel.source_memory_entry_id,
                         "source_entry_title": rel.source_entry.title, # Access related object
                         "created_at": rel.created_at.isoformat() if rel.created_at else None,
                     })

        logger.info(f"Found {len(relations_from)} outgoing and {len(relations_to)} incoming relations for memory entry {memory_entry_id}.")
        return {
            "relations_from_this": relations_from,
            "relations_to_this": relations_to
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error listing relations for memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing relations for memory entry {memory_entry_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}

# --- Add the following Unlinking Tools ---

@mcp_instance.tool()
async def unlink_memory_entry_from_document(memory_entry_id: int, document_id: int, ctx: Context) -> Dict[str, Any]:
    """Removes the link between a specific Memory Entry and a specific Document."""
    logger.info(f"Handling unlink_memory_entry_from_document request for entry ID: {memory_entry_id} and doc ID: {document_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in unlink_memory_entry_from_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                 # Fetch the Memory Entry and eagerly load its linked documents
                stmt = select(MemoryEntry).options(selectinload(MemoryEntry.documents)).where(MemoryEntry.id == memory_entry_id)
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()

                if entry is None:
                     logger.warning(f"MemoryEntry {memory_entry_id} not found for unlinking document.")
                     return {"error": f"MemoryEntry {memory_entry_id} not found"}

                # Find the specific document within the relationship collection
                document_to_remove = None
                for doc in entry.documents:
                    if doc.id == document_id:
                        document_to_remove = doc
                        break

                if document_to_remove:
                     # Remove the Document object from the collection
                    entry.documents.remove(document_to_remove)
                    # SQLAlchemy handles the deletion from the association table
                    logger.info(f"Unlinked Document {document_id} from MemoryEntry {memory_entry_id}.")
                else:
                    logger.warning(f"Link between MemoryEntry {memory_entry_id} and Document {document_id} not found.")
                    return {"message": "Link not found"}

            # Commit successful
        return {"message": f"Unlinked document {document_id} from memory entry {memory_entry_id}"}
    except SQLAlchemyError as e:
         logger.error(f"Database error unlinking memory entry {memory_entry_id} from doc {document_id}: {e}", exc_info=True)
         return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error unlinking memory entry {memory_entry_id} from doc {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def unlink_memory_entries(relation_id: int, ctx: Context) -> Dict[str, Any]:
    """Removes a specific relationship link between two memory entries using the relation's ID."""
    logger.info(f"Handling unlink_memory_entries request for relation ID: {relation_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in unlink_memory_entries call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin(): # Use transaction
                # Fetch the specific MemoryEntryRelation record by its primary key
                relation = await session.get(MemoryEntryRelation, relation_id)

                if relation is None:
                     logger.warning(f"MemoryEntryRelation with ID {relation_id} not found for deletion.")
                     return {"error": f"Relation with ID {relation_id} not found"}

                logger.info(f"Deleting relation ID: {relation_id} (linking {relation.source_memory_entry_id} -> {relation.target_memory_entry_id})")
                # Delete the relation record itself
                await session.delete(relation)
            # Commit happens automatically

        logger.info(f"Relation {relation_id} deleted successfully.")
        return {"message": f"Relation ID {relation_id} deleted successfully"}

    except SQLAlchemyError as e:
        logger.error(f"Database error deleting relation {relation_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error deleting relation {relation_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Example/Placeholder handlers (can be removed if not needed) ---

@mcp_instance.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kg and height in meters"""
    logger.info(f"Calculating BMI for weight={weight_kg}, height={height_m}")
    if height_m <= 0:
        return 0.0
    return weight_kg / (height_m**2)


@mcp_instance.resource("users://{user_id}/profile")
def get_user_profile(user_id: str) -> str:
    """Dynamic user data"""
    logger.info(f"Fetching profile for user_id: {user_id}")
    # TODO: Fetch actual profile
    return f"Profile data for user {user_id}"
