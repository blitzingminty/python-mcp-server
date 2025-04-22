from typing import Any, Dict
from mcp.server.fastmcp import Context
from .mcp_server_core import mcp_instance, get_session
from .mcp_db_helpers_project import (
    create_project_in_db,
    update_project_in_db,
    delete_project_in_db,
    set_active_project_in_db,
)

@mcp_instance.tool()
async def list_projects(ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    # Implement actual logic to list projects
    projects = []  # Replace with actual query
    return {"projects": projects}

@mcp_instance.tool()
async def create_project(name: str, description: str, ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    project = await create_project_in_db(session=session, name=name, description=description)
    return {"project": project}

@mcp_instance.tool()
async def get_project(project_id: int, ctx: Context[Any, Any]) -> Dict[str, Any]:
    session = await get_session(ctx)
    # Implement logic to get project by ID
    project = None  # Replace with actual query
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
