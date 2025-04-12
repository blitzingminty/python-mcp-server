# src/mcp_server_instance.py
# Defines the FastMCP server instance and its handlers.

import logging,time
from typing import Any, Dict, Optional, List, AsyncIterator
from contextlib import asynccontextmanager
import datetime


# --- SQLAlchemy Imports ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

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
# Import DB components needed for lifespan and handlers
# Add Base, engine if needed for lifespan init
from .database import AsyncSessionFactory, Base, engine


from .models import Project, Document, DocumentVersion, MemoryEntry, Tag, MemoryEntryRelation # Add MemoryEntryRelation

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


@mcp_instance.tool()
async def create_project(
    name: str,
    path: str,
    description: Optional[str] = None,
    is_active: bool = False,
    ctx: Context = None  # Context needs to be last if optional, or use **kwargs
) -> Dict[str, Any]:
    """Creates a new project in the database."""
    logger.info(
        f"Handling create_project request: name='{name}', path='{path}'")
    if not ctx:
        logger.error("Context (ctx) argument missing in create_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        new_project = Project(
            name=name,
            path=path,
            description=description,
            is_active=is_active
            # created_at/updated_at have defaults
        )
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                session.add(new_project)
                # We need to flush to get the ID before commit (if needed immediately)
                # await session.flush()
                # Or commit and then refresh/re-select if ID needed in response
            # Commit happens automatically when 'async with session.begin()' exits without error
            # To get the generated ID and defaults, expire and refresh
            await session.refresh(new_project, attribute_names=['id', 'created_at', 'updated_at'])

        logger.info(f"Project created successfully with ID: {new_project.id}")
        return {
            "message": "Project created successfully",
            "project": {
                "id": new_project.id,
                "name": new_project.name,
                "description": new_project.description,
                "path": new_project.path,
                "is_active": new_project.is_active,
                "created_at": new_project.created_at.isoformat() if new_project.created_at else None,
                "updated_at": new_project.updated_at.isoformat() if new_project.updated_at else None,
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error creating project: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error creating project: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


# --- Placeholder Tool/Resource Handlers from before (can be filled in later) ---

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
    ctx: Context = None  # Context needs to be last if optional, or use **kwargs
) -> Dict[str, Any]:
    """Updates fields for a specific project."""
    logger.info(f"Handling update_project request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in update_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                project = await session.get(Project, project_id)

                if project is None:
                    logger.warning(
                        f"Project with ID {project_id} not found for update.")
                    # Rollback happens automatically when exiting 'async with session.begin()' due to error
                    return {"error": f"Project with ID {project_id} not found"}

                update_data = {
                    "name": name, "description": description, "path": path, "is_active": is_active
                }
                updated = False
                for key, value in update_data.items():
                    if value is not None:
                        if getattr(project, key) != value:
                            setattr(project, key, value)
                            updated = True

                if not updated:
                    logger.info(
                        f"No fields provided to update for project {project_id}.")
                    # Still return success, but maybe indicate no change?
                    # For simplicity, return current state. Refresh might not be needed.
                    # await session.refresh(project) # Refresh if defaults could change
                    return {
                        "message": "No update needed for project",
                        "project": {
                            "id": project.id,
                            "name": project.name,
                            "description": project.description,
                            "path": project.path,
                            "is_active": project.is_active,
                            "created_at": project.created_at.isoformat() if project.created_at else None,
                            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                        }  # Return current state
                    }

                # updated_at should be handled by onupdate=func.now() in the model
                logger.info(f"Updating project ID: {project_id}")
                # Add project back to session - usually automatic if fetched via session.get
                # session.add(project)
                # Flush to ensure update happens before refresh, then refresh to get new updated_at
                await session.flush()
                await session.refresh(project, attribute_names=["updated_at"])

            # Transaction commits here if no exceptions
            logger.info(f"Project {project_id} updated successfully.")
            return {
                "message": "Project updated successfully",
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
            f"Database error updating project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error updating project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def delete_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Deletes a specific project by its ID."""
    logger.info(f"Handling delete_project request for ID: {project_id}")
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                project = await session.get(Project, project_id)

                if project is None:
                    logger.warning(
                        f"Project with ID {project_id} not found for deletion.")
                    return {"error": f"Project with ID {project_id} not found"}

                logger.info(
                    f"Deleting project ID: {project_id} ('{project.name}')")
                await session.delete(project)
            # Commit happens automatically

        logger.info(f"Project {project_id} deleted successfully.")
        return {"message": f"Project ID {project_id} deleted successfully"}

    except SQLAlchemyError as e:
        logger.error(
            f"Database error deleting project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error deleting project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def set_active_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Sets a specific project as active, deactivating all others."""
    logger.info(f"Handling set_active_project request for ID: {project_id}")
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                # Get the project to activate
                project_to_activate = await session.get(Project, project_id)

                if project_to_activate is None:
                    logger.warning(
                        f"Project with ID {project_id} not found to activate.")
                    return {"error": f"Project with ID {project_id} not found"}

                # Find currently active projects (excluding the target one if it's already active)
                stmt = select(Project).where(Project.is_active ==
                                             True, Project.id != project_id)
                result = await session.execute(stmt)
                currently_active_projects = result.scalars().all()

                # Deactivate others
                for proj in currently_active_projects:
                    logger.info(
                        f"Deactivating currently active project ID: {proj.id}")
                    proj.is_active = False
                    # session.add(proj) # Often implicit

                # Activate the target project
                if not project_to_activate.is_active:
                    logger.info(f"Activating project ID: {project_id}")
                    project_to_activate.is_active = True
                    # session.add(project_to_activate) # Often implicit
                else:
                    logger.info(
                        f"Project ID: {project_id} was already active.")

            # Commit happens automatically

        logger.info(f"Project {project_id} is now the active project.")
        # Return the activated project details
        return {
            "message": f"Project ID {project_id} set as active",
            "project": {
                "id": project_to_activate.id,
                "name": project_to_activate.name,
                "is_active": project_to_activate.is_active,
            }
        }

    except SQLAlchemyError as e:
        logger.error(
            f"Database error setting active project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error setting active project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def add_document(
    project_id: int,
    name: str,
    path: str,
    content: str,
    type: str,  # e.g., 'text/plain', 'markdown', 'python'
    version: str = "1.0.0",  # Default version for initial add
    ctx: Context = None
) -> Dict[str, Any]:
    """Adds a new document to a specified project."""
    logger.info(
        f"Handling add_document request for project ID: {project_id}, name: {name}")
    if not ctx:
        logger.error("Context (ctx) argument missing in add_document call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                # Verify project exists
                project = await session.get(Project, project_id)
                if project is None:
                    logger.warning(
                        f"Project with ID {project_id} not found for adding document.")
                    return {"error": f"Project with ID {project_id} not found"}

                # Create the new document
                new_document = Document(
                    project_id=project_id,
                    name=name,
                    path=path,
                    content=content,
                    type=type,
                    version=version  # Store initial version on document too
                )
                session.add(new_document)

                # Optionally, create an initial DocumentVersion entry as well
                # Flush to get the new_document.id
                await session.flush()
                new_version = DocumentVersion(
                    document_id=new_document.id,
                    content=content,
                    version=version
                )
                session.add(new_version)

                # Refresh to get generated IDs/defaults
                await session.refresh(new_document)
                await session.refresh(new_version)

            # Commit happens automatically

        logger.info(
            f"Document '{name}' (ID: {new_document.id}) added successfully to project {project_id}.")
        return {
            "message": "Document added successfully",
            "document": {
                "id": new_document.id,
                "project_id": new_document.project_id,
                "name": new_document.name,
                "path": new_document.path,
                "type": new_document.type,
                "version": new_document.version,
                "created_at": new_document.created_at.isoformat() if new_document.created_at else None,
                "updated_at": new_document.updated_at.isoformat() if new_document.updated_at else None,
                "initial_version_id": new_version.id  # Include ID of the version created
            }
        }
    except SQLAlchemyError as e:
        logger.error(
            f"Database error adding document to project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error adding document to project {project_id}: {e}", exc_info=True)
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


@mcp_instance.resource("document_version://{version_id}") # Use version ID
async def get_document_version_content(version_id: int) -> Dict[str, Any]:
    """Resource handler to get the content of a specific document version by its ID."""
    start_time = time.time() # <-- Start timer
    logger.info(f"Handling get_document_version_content resource request for version ID: {version_id}")
    session: Optional[AsyncSession] = None
    try:
        session = AsyncSessionFactory()
        logger.debug(f"Session created for get_document_version_content {version_id}")

        # Fetch the specific version, need to load related document for mime_type
        stmt = select(DocumentVersion).options(
            selectinload(DocumentVersion.document)
            ).where(DocumentVersion.id == version_id)
        result = await session.execute(stmt)
        version = result.scalar_one_or_none()
        # version = await session.get(DocumentVersion, version_id, options=[selectinload(DocumentVersion.document)]) # Alternative

        if version is None:
            logger.warning(f"DocumentVersion with ID {version_id} not found for resource request.")
            return {"error": f"DocumentVersion {version_id} not found"}

        if version.document is None:
             logger.error(f"DocumentVersion {version_id} has no associated document loaded.")
             return {"error": f"Data integrity error for version {version_id}"}

        logger.info(f"Found document version '{version.version}' (ID: {version_id}), returning content.")
        end_time = time.time() # <-- End timer
        logger.info(f"get_document_version_content for version {version_id} took {end_time - start_time:.4f} seconds.") # <-- Log duration

        # Return content from the specific version, and mime_type from the parent document
        return {
            "content": version.content,
            "mime_type": version.document.type,
            "version_string": version.version, # Include the version string itself
            "document_id": version.document_id # Include parent document ID
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error getting document version {version_id}: {e}", exc_info=True)
        return {"error": f"Database error getting document version content"}
    except Exception as e:
        logger.error(f"Unexpected error getting document version {version_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error processing resource"}
    finally:
        if session:
            await session.close()
            logger.debug(f"Session closed for get_document_version_content {version_id}")






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
    content: Optional[str] = None,
    type: Optional[str] = None,
    version: Optional[str] = None,  # If provided, creates a new version
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Updates fields for a specific document.
    If content or version is provided, a new DocumentVersion is created,
    and the main document record's content/version is updated.
    """
    logger.info(f"Handling update_document request for ID: {document_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in update_document call.")
        return {"error": "Internal server error: Context missing."}

    if content is not None and version is None:
        logger.warning(
            f"Content update provided for doc {document_id} but no new version string was specified.")
        # Decide on behavior: reject, auto-increment, or use default? Let's reject for now.
        return {"error": "Version must be specified when updating content."}

    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                document = await session.get(Document, document_id)

                if document is None:
                    logger.warning(
                        f"Document with ID {document_id} not found for update.")
                    return {"error": f"Document with ID {document_id} not found"}

                updated_fields = False
                new_version_id = None

                # Handle content/version update -> creates new DocumentVersion
                if content is not None and version is not None:
                    logger.info(
                        f"Updating content and version for doc {document_id} to version '{version}'")
                    # Create new version record
                    new_version = DocumentVersion(
                        document_id=document.id,
                        content=content,
                        version=version
                    )
                    session.add(new_version)
                    # Update main document record
                    document.content = content
                    document.version = version
                    updated_fields = True
                    # Flush to get the ID if needed for the response
                    await session.flush()
                    await session.refresh(new_version)
                    new_version_id = new_version.id
                elif version is not None and document.version != version:
                    # Allow updating only version string if desired, maybe without new content record?
                    # For simplicity now, let's assume version only changes with content.
                    # If you want to allow changing *only* version string, add logic here.
                    logger.info(
                        f"Updating version string for doc {document_id} to '{version}' (content not changed).")
                    document.version = version
                    updated_fields = True

                # Update other fields if provided and different
                if name is not None and document.name != name:
                    document.name = name
                    updated_fields = True
                if path is not None and document.path != path:
                    document.path = path
                    updated_fields = True
                if type is not None and document.type != type:
                    document.type = type
                    updated_fields = True

                if not updated_fields:
                    logger.info(
                        f"No fields provided or values matched current state for document {document_id}.")
                    # Ensure we return fresh data
                    await session.refresh(document)
                    return {
                        "message": "No update applied to document",
                        # Return current state
                        "document": {
                            "id": document.id, "project_id": document.project_id, "name": document.name,
                            "path": document.path, "type": document.type, "version": document.version,
                            "created_at": document.created_at.isoformat() if document.created_at else None,
                            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
                        }
                    }

                logger.info(f"Updating document ID: {document_id}")
                # updated_at handled by onupdate
                await session.flush()
                await session.refresh(document)

            # Transaction commits here
            logger.info(f"Document {document_id} updated successfully.")
            response_doc = {
                "id": document.id, "project_id": document.project_id, "name": document.name,
                "path": document.path, "type": document.type, "version": document.version,
                "created_at": document.created_at.isoformat() if document.created_at else None,
                "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            }
            if new_version_id:
                response_doc["new_version_id"] = new_version_id

            return {
                "message": "Document updated successfully",
                "document": response_doc
            }

    except SQLAlchemyError as e:
        logger.error(
            f"Database error updating document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error updating document {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def delete_document(document_id: int, ctx: Context) -> Dict[str, Any]:
    """Deletes a specific document by its ID and its associated versions."""
    logger.info(f"Handling delete_document request for ID: {document_id}")
    try:
        async with await get_session(ctx) as session:
            async with session.begin():  # Use transaction
                document = await session.get(Document, document_id)

                if document is None:
                    logger.warning(
                        f"Document with ID {document_id} not found for deletion.")
                    return {"error": f"Document with ID {document_id} not found"}

                logger.info(
                    f"Deleting document ID: {document_id} ('{document.name}')")
                await session.delete(document)
                # Cascaded delete for DocumentVersions should happen automatically
                # due to `cascade="all, delete-orphan"` in Document.versions relationship.
            # Commit happens automatically

        logger.info(f"Document {document_id} deleted successfully.")
        return {"message": f"Document ID {document_id} deleted successfully"}

    except SQLAlchemyError as e:
        logger.error(
            f"Database error deleting document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error deleting document {document_id}: {e}", exc_info=True)
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

                logger.info(f"Updating memory entry ID: {memory_entry_id}")
                await session.flush()
                await session.refresh(entry)  # Get updated timestamp etc.

            # Transaction commits here
            logger.info(
                f"Memory entry {memory_entry_id} updated successfully.")
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


@mcp_instance.tool()
async def delete_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    """Deletes a specific memory entry by its ID."""
    logger.info(
        f"Handling delete_memory_entry request for ID: {memory_entry_id}")
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
        await session.flush()
        await session.refresh(tag)
        logger.info(f"Tag '{tag_name}' created.")
    return tag

@mcp_instance.tool()
async def add_tag_to_document(document_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    """Adds a tag to a specific document."""
    logger.info(f"Handling add_tag_to_document request for doc ID: {document_id}, tag: {tag_name}")
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Use selectinload to efficiently load tags if checking for existence
                stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()
                # document = await session.get(Document, document_id, options=[selectinload(Document.tags)]) # Alternative get with options

                if document is None:
                    logger.warning(f"Document {document_id} not found for adding tag.")
                    return {"error": f"Document {document_id} not found"}

                tag = await _get_or_create_tag(session, tag_name)

                if tag in document.tags:
                    logger.info(f"Tag '{tag_name}' already exists on document {document_id}.")
                    return {"message": "Tag already exists on document"}
                else:
                    document.tags.add(tag)
                    logger.info(f"Tag '{tag_name}' added to document {document_id}.")
                    # Flush may be needed if using the relationship immediately after
                    # await session.flush()

            # Commit successful
        return {"message": f"Tag '{tag_name}' added to document {document_id}"}
    except SQLAlchemyError as e:
        logger.error(f"Database error adding tag to document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error adding tag to document {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def remove_tag_from_document(document_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    """Removes a tag from a specific document."""
    logger.info(f"Handling remove_tag_from_document request for doc ID: {document_id}, tag: {tag_name}")
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                # Load the document and its tags efficiently
                stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()

                if document is None:
                    logger.warning(f"Document {document_id} not found for removing tag.")
                    return {"error": f"Document {document_id} not found"}

                # Find the tag object within the document's tags
                tag_to_remove = None
                for tag in document.tags:
                    if tag.name == tag_name:
                        tag_to_remove = tag
                        break

                if tag_to_remove:
                    document.tags.remove(tag_to_remove)
                    logger.info(f"Tag '{tag_name}' removed from document {document_id}.")
                    # Optionally, check if the tag is now orphaned and delete it if desired
                    # This requires checking relationships from the Tag side.
                else:
                    logger.warning(f"Tag '{tag_name}' not found on document {document_id}.")
                    return {"message": "Tag not found on document"}

            # Commit successful
        return {"message": f"Tag '{tag_name}' removed from document {document_id}"}
    except SQLAlchemyError as e:
        logger.error(f"Database error removing tag from document {document_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error removing tag from document {document_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def list_tags_for_document(document_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all tags associated with a specific document."""
    logger.info(f"Handling list_tags_for_document request for doc ID: {document_id}")
    tag_names = []
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


# --- Keep other handlers ---









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

# --- TODO: Add other Project CRUD tools ---
# @mcp_instance.tool() def get_project(project_id: int, ctx: Context) -> Dict: ...
# @mcp_instance.tool() def update_project(project_id: int, name: Optional[str], ..., ctx: Context) -> Dict: ...
# @mcp_instance.tool() def delete_project(project_id: int, ctx: Context) -> Dict: ...
# @mcp_instance.tool() def set_active_project(project_id: int, ctx: Context) -> Dict: ...
