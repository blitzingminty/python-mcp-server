from typing import Any, Dict, Optional, List

from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from .mcp_server_lifespan import mcp_instance
from .mcp_server_core import get_session
from .mcp_db_helpers_project import (
    create_project_in_db,
    update_project_in_db,
    delete_project_in_db,
    set_active_project_in_db,
)
from .models import Project

import logging

logger = logging.getLogger(__name__)

@mcp_instance.tool()
async def list_projects(ctx: Any) -> Dict[str, Any]:
    logger.info("Handling list_projects request...")
    projects_data: List[Dict[str, Optional[object]]] = []
    if not ctx:
        logger.error("Context (ctx) argument missing in list_projects call.")
        return {"error": "Internal server error: Context missing."}
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
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error listing projects: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def create_project(
    name: str, path: str, description: Optional[str] = None, is_active: bool = False, ctx: Any = None
) -> Dict[str, Any]:
    logger.info(f"Handling create_project MCP tool request: name='{name}'")
    if not ctx:
        logger.error("Context (ctx) argument missing in create_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                created_project = await create_project_in_db(session=session, name=name, path=path, description=description, is_active=is_active)
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
async def get_project(project_id: int, ctx: Any) -> Dict[str, Any]:
    logger.info(f"Handling get_project request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in get_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
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
        logger.error(f"Database error getting project {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error getting project {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def update_project(
    project_id: int, name: Optional[str] = None, description: Optional[str] = None,
    path: Optional[str] = None, is_active: Optional[bool] = None, ctx: Any = None
) -> Dict[str, Any]:
    logger.info(f"Handling update_project MCP tool request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in update_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                updated_project = await update_project_in_db(session=session, project_id=project_id, name=name, description=description, path=path, is_active=is_active)
        if updated_project is None:
            logger.warning(f"MCP Tool: Project with ID {project_id} not found for update.")
            return {"error": f"Project with ID {project_id} not found"}
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
async def delete_project(project_id: int, ctx: Any) -> Dict[str, Any]:
    logger.info(f"Handling delete_project MCP tool request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in delete_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                deleted = await delete_project_in_db(session, project_id)
        if deleted:
            logger.info(f"Project {project_id} deleted successfully via MCP tool.")
            return {"message": f"Project ID {project_id} deleted successfully"}
        else:
            logger.error(f"MCP Tool: Failed to delete project {project_id} due to database error during delete.")
            return {"error": "Database error during project deletion"}
    except SQLAlchemyError as e:
        logger.error(f"Database error processing delete_project tool for {project_id}: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error processing delete_project tool for {project_id}: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def set_active_project(project_id: int, ctx: Any) -> Dict[str, Any]:
    logger.info(f"Handling set_active_project MCP tool request for ID: {project_id}")
    if not ctx:
        logger.error("Context (ctx) argument missing in set_active_project call.")
        return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session(ctx) as session:
            async with session.begin():
                activated_project = await set_active_project_in_db(session, project_id)
        if activated_project is None:
            logger.warning(f"MCP Tool: Project with ID {project_id} not found to activate.")
            return {"error": f"Project with ID {project_id} not found"}
        logger.info(f"Project {project_id} is now the active project (via MCP tool).")
        return {
            "message": f"Project ID {project_id} set as active",
            "project": {
                "id": activated_project.id,
                "name": activated_project.name,
                "is_active": activated_project.is_active
            }
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error setting active project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error setting active project {project_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}
