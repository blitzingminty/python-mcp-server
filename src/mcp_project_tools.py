from typing import Any, Dict, Optional, cast, cast
from mcp.server.fastmcp import Context
from .mcp_server_core import mcp_instance
from .mcp_db_helpers_project import (
    create_project_in_db,
    list_projects_in_db,
    get_project_in_db,
    update_project_in_db,
    delete_project_in_db,
    set_active_project_in_db,
)
from .models import Project

from src.mcp_db_helpers import get_session
from src.database import get_db_session
from typing import AsyncGenerator
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session_from_factory():
    async for session in get_db_session():
        yield session

@mcp_instance.tool()
async def list_projects() -> Dict[str, Any]:
    async with get_session_from_factory() as session:
        projects = await list_projects_in_db(session)
    return {"projects": projects}

def coerce_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        elif lowered in ("false", "0", "no", "off"):
            return False
    if value is None:
        return False
    raise ValueError(f"Cannot coerce value {value!r} to bool")

@mcp_instance.tool()
async def create_project(name: str, description: str, path: str, is_active: Any) -> Dict[str, Project]:
    is_active_bool = coerce_to_bool(is_active)
    async with get_session_from_factory() as session:
        project = await create_project_in_db(session=session, name=name, path=path, description=description, is_active=is_active_bool)
        await session.commit()
    return {"project": project}

@mcp_instance.tool()
async def get_project(project_id: int) -> Dict[str, Any]:
    async with get_session_from_factory() as session:
        project = await get_project_in_db(session, project_id)
    return {"project": project}

@mcp_instance.tool()
async def update_project(project_id: int, name: str, description: str) -> Dict[str, Any]:
    async with get_session_from_factory() as session:
        project = await update_project_in_db(session=session, project_id=project_id, name=name, description=description)
        await session.commit()
    return {"project": project}

@mcp_instance.tool()
async def delete_project(project_id: int) -> Dict[str, Any]:
    async with get_session_from_factory() as session:
        success = await delete_project_in_db(session=session, project_id=project_id)
        await session.commit()
    return {"success": success}

@mcp_instance.tool()
async def set_active_project(project_id: int) -> Dict[str, Any]:
    async with get_session_from_factory() as session:
        success = await set_active_project_in_db(session=session, project_id=project_id)
        await session.commit()
    return {"success": success}

# Removed duplicate set_active_project definition to fix function declaration obscured error
