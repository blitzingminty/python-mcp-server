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
