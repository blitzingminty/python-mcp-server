import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from .models import Project

logger = logging.getLogger(__name__)

async def create_project_in_db( # type: ignore
    session: AsyncSession, name: str, path: str, description: Optional[str], is_active: bool
) -> Project:
    logger.debug(f"Helper: Creating project '{name}' in DB.")
    new_project = Project(name=name, path=path, description=description, is_active=is_active)
    session.add(new_project)
    await session.flush()
    await session.refresh(new_project)
    logger.debug(f"Helper: Project created with ID {new_project.id}")
    return new_project

async def update_project_in_db( # type: ignore
    session: AsyncSession, project_id: int, name: Optional[str] = None,
    description: Optional[str] = None, path: Optional[str] = None, is_active: Optional[bool] = None
) -> Optional[Project]:
    logger.debug(f"Helper: Updating project ID {project_id} in DB.")
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for update.")
        return None
    update_data: dict[str, Optional[object]] = {"name": name, "description": description, "path": path, "is_active": is_active}
    updated = False
    for key, value in update_data.items():
        if value is not None and getattr(project, key) != value:
            setattr(project, key, value)
            updated = True
    if updated:
        logger.debug(f"Helper: Applying updates to project {project_id}.")
        await session.flush()
        await session.refresh(project)
    else:
        logger.debug(f"Helper: No changes detected for project {project_id}.")
    return project

async def delete_project_in_db(session: AsyncSession, project_id: int) -> bool: # type: ignore
    logger.debug(f"Helper: Deleting project ID {project_id} from DB.")
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for deletion.")
        return True
    try:
        await session.delete(project)
        await session.flush()
        logger.info(f"Helper: Project ID {project_id} deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting project {project_id}: {e}", exc_info=True)
        return False

async def set_active_project_in_db(session: AsyncSession, project_id: int) -> Optional[Project]: # type: ignore
    logger.debug(f"Helper: Setting project ID {project_id} as active in DB.")
    project_to_activate = await session.get(Project, project_id)
    if project_to_activate is None:
        logger.warning(f"Helper: Project ID {project_id} not found to activate.")
        return None
    stmt = select(Project).where(Project.is_active == True, Project.id != project_id)
    result = await session.execute(stmt)
    currently_active_projects = result.scalars().all()
    updated = False
    for proj in currently_active_projects:
        logger.debug(f"Helper: Deactivating currently active project ID: {proj.id}")
        proj.is_active = False
        updated = True
    if not project_to_activate.is_active:
        logger.debug(f"Helper: Activating project ID: {project_id}")
        project_to_activate.is_active = True
        updated = True
    else:
        logger.debug(f"Helper: Project ID: {project_id} was already active.")
    if updated:
        await session.flush()
        await session.refresh(project_to_activate)
    else:
        logger.debug(f"Helper: No change in active state for project {project_id}.")
    return project_to_activate
