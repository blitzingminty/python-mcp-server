# src/mcp_server_instance.py
# Defines the FastMCP server instance and its handlers.

import logging
from typing import Any, Dict, Optional, List, AsyncIterator
from contextlib import asynccontextmanager
import datetime

# --- SQLAlchemy Imports ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

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
from .models import Project, Document, DocumentVersion # Make sure Document and DocumentVersion are here

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
    type: str, # e.g., 'text/plain', 'markdown', 'python'
    version: str = "1.0.0", # Default version for initial add
    ctx: Context = None
) -> Dict[str, Any]:
    """Adds a new document to a specified project."""
    logger.info(f"Handling add_document request for project ID: {project_id}, name: {name}")
    if not ctx:
         logger.error("Context (ctx) argument missing in add_document call.")
         return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin(): # Use transaction
                # Verify project exists
                project = await session.get(Project, project_id)
                if project is None:
                    logger.warning(f"Project with ID {project_id} not found for adding document.")
                    return {"error": f"Project with ID {project_id} not found"}

                # Create the new document
                new_document = Document(
                    project_id=project_id,
                    name=name,
                    path=path,
                    content=content,
                    type=type,
                    version=version # Store initial version on document too
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

        logger.info(f"Document '{name}' (ID: {new_document.id}) added successfully to project {project_id}.")
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
                "initial_version_id": new_version.id # Include ID of the version created
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error adding document to project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error adding document to project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_documents_for_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    """Lists all documents associated with a specific project."""
    logger.info(f"Handling list_documents_for_project request for project ID: {project_id}")
    documents_data = []
    try:
        async with await get_session(ctx) as session:
            # Verify project exists first (optional, but good practice)
            project = await session.get(Project, project_id)
            if project is None:
                 logger.warning(f"Project with ID {project_id} not found for listing documents.")
                 return {"error": f"Project with ID {project_id} not found"}

            # Query documents for the project
            stmt = select(Document).where(Document.project_id == project_id).order_by(Document.name)
            result = await session.execute(stmt)
            documents = result.scalars().all()
            for doc in documents:
                documents_data.append({
                    "id": doc.id,
                    "project_id": doc.project_id,
                    "name": doc.name,
                    "path": doc.path,
                    "type": doc.type,
                    "version": doc.version, # Current version stored on Document
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                })
        logger.info(f"Found {len(documents_data)} documents for project {project_id}.")
        return {"documents": documents_data}
    except SQLAlchemyError as e:
        logger.error(f"Database error listing documents for project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing documents for project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.resource("document://{document_id}") # Define URI pattern
async def get_document_content(document_id: int) -> Dict[str, Any]: # No ctx here
    """Resource handler to get the content of a specific document."""
    logger.info(f"Handling get_document_content resource request for document ID: {document_id}")
    # TODO: Re-implement database access for resources if context is needed/accessible.
    # For now, return placeholder data to fix startup error.
    if document_id == 1: # Example placeholder condition
        return {
            "content": f"Placeholder content for document {document_id}",
            "mime_type": "text/plain"
        }
    else:
         logger.warning(f"Placeholder: Document with ID {document_id} not found.")
         # Ensure this return is correctly indented within the else block
         return {"error": f"Document {document_id} not found"} # Simple error return     




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
