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
    logging.critical(f"Failed to import from mcp.server.fastmcp: {e}. Please ensure 'mcp[cli]' is installed correctly.")
    raise

# --- Project Imports ---
from .config import settings
# Import DB components needed for lifespan and handlers
from .database import AsyncSessionFactory, Base, engine # Add Base, engine if needed for lifespan init
from .models import Project # Import the Project model

logger = logging.getLogger(__name__)


# --- Lifespan Management for Database ---

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """
    Manage application lifecycle, providing database access.
    Provides the AsyncSessionFactory via context.
    """
    logger.info("Application lifespan startup...")
    # Optionally create tables here if not using migrations or --init-db
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    #     logger.info("Database tables checked/created.")

    # Provide the session factory in the context
    context_data = {"db_session_factory": AsyncSessionFactory}
    try:
        yield context_data
    finally:
        # Cleanup on shutdown (e.g., close engine if needed)
        # await engine.dispose() # Typically needed if engine created here
        logger.info("Application lifespan shutdown.")


# --- Create the FastMCP Instance ---
# Pass the lifespan manager to the constructor
mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    lifespan=app_lifespan
)
logger.info(f"FastMCP instance created with lifespan: {settings.MCP_SERVER_NAME} v{settings.VERSION}")


# --- Helper to get session from context ---
async def get_session(ctx: Context) -> AsyncSession:
    """Gets an async session from the lifespan context."""
    try:
        session_factory = ctx.request_context.lifespan_context["db_session_factory"]
        return session_factory()
    except KeyError:
        logger.error("Database session factory not found in lifespan context.")
        # Depending on MCP SDK, raise a specific MCPError or standard exception
        raise RuntimeError("Server configuration error: DB Session Factory missing.")
    except AttributeError:
         logger.error("Context structure unexpected. Cannot find lifespan context or session factory.")
         raise RuntimeError("Server configuration error: Context structure invalid.")

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
    ctx: Context = None # Context needs to be last if optional, or use **kwargs
) -> Dict[str, Any]:
    """Creates a new project in the database."""
    logger.info(f"Handling create_project request: name='{name}', path='{path}'")
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
            async with session.begin(): # Use transaction
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
