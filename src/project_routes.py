import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus
from .database import get_db_session
from .models import Project
from .mcp_db_helpers_project import create_project_in_db, update_project_in_db, delete_project_in_db, set_active_project_in_db

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/projects", response_class=HTMLResponse, name="ui_list_projects")
async def list_projects_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches projects from DB and renders the projects list page."""
    logger.info("Web UI projects list requested")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    projects = []
    error_message = None
    try:
        stmt = select(Project).order_by(Project.name)
        result = await db.execute(stmt)
        projects = result.scalars().all()
    except Exception as e:
        logger.error(f"Failed to fetch projects for web UI: {e}", exc_info=True)
        error_message = f"Error fetching projects: {e}"
    context_data: Dict[str, Any] = {"page_title": "Projects List", "projects": projects, "error": error_message}
    return templates.TemplateResponse("projects.html", {"request": request, "data": context_data})

@router.get("/projects/new", response_class=HTMLResponse, name="ui_new_project")
async def new_project_form(request: Request):
    """Displays the form to create a new project."""
    logger.info("Web UI new project form requested")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    context_data: Dict[str, Any] = {
        "page_title": "Create New Project",
        "form_action": request.url_for('ui_create_project'),
        "error": request.query_params.get("error"),
        "cancel_url": request.url_for('ui_list_projects')
    }
    return templates.TemplateResponse("project_form.html", {"request": request, "data": context_data})

@router.get("/projects/{project_id}/edit", response_class=HTMLResponse, name="ui_edit_project")
async def edit_project_form(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Displays the form pre-filled for editing an existing project."""
    logger.info(f"Web UI edit project form requested for ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project with ID {project_id} not found")
    context_data: Dict[str, Any] = {
        "page_title": f"Edit Project: {project.name}",
        "form_action": request.url_for('ui_update_project', project_id=project_id),
        "cancel_url": request.url_for('ui_view_project', project_id=project_id),
        "error": request.query_params.get("error"),
        "project": project,
        "is_edit_mode": True
    }
    return templates.TemplateResponse("project_form.html", {"request": request, "data": context_data})

@router.post("/projects", name="ui_create_project")
async def create_project_web(
    request: Request, db: AsyncSession = Depends(get_db_session),
    name: str = Form(...), path: str = Form(...), description: Optional[str] = Form(None), is_active: bool = Form(False)
):
    """Handles the submission of the new project form."""
    logger.info(f"Web UI create_project form submitted: name='{name}'")
    error_message = None
    new_project_id = None
    created_project = None
    try:
        async with db.begin():
            created_project = await create_project_in_db(
                session=db, name=name, path=path, description=description if description else None, is_active=is_active
            )
        if created_project:
            new_project_id = created_project.id
            logger.info(f"Project created directly via web route, ID: {new_project_id}")
    except SQLAlchemyError as e:
        error_message = f"Database error creating project: {e}"
        logger.error(f"Database error creating project via web route: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Unexpected error in create_project_web: {e}", exc_info=True)
    if new_project_id is not None:
        return RedirectResponse(request.url_for('ui_view_project', project_id=new_project_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error')}"
        return RedirectResponse(str(request.url_for('ui_new_project')) + error_param, status_code=303)

@router.get("/projects/{project_id}", response_class=HTMLResponse, name="ui_view_project")
async def view_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific project AND its related items, renders its detail page."""
    logger.info(f"Web UI project detail requested for ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    project = None
    error_message = request.query_params.get("error")
    try:
        stmt = select(Project).where(Project.id == project_id)
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            error_message = f"Project with ID {project_id} not found."
            logger.warning(error_message)
            raise HTTPException(status_code=404, detail=error_message)
    except Exception as e:
        error_message = error_message or f"Error fetching project details: {e}"
        logger.error(f"Error fetching project {project_id} for web UI: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)
    context_data: Dict[str, Any] = {"page_title": f"Project: {project.name}" if project else "Project Not Found", "project": project, "error": error_message}
    return templates.TemplateResponse("project_detail.html", {"request": request, "data": context_data})

@router.post("/projects/{project_id}/edit", name="ui_update_project")
async def update_project_web(
    project_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    name: str = Form(...), path: str = Form(...), description: Optional[str] = Form(None), is_active: bool = Form(False)
):
    """Handles the submission of the edit project form."""
    logger.info(f"Web UI update_project form submitted for ID: {project_id}")
    error_message = None
    updated_project = None
    try:
        async with db.begin():
            updated_project = await update_project_in_db(session=db, project_id=project_id, name=name, path=path, description=description if description else None, is_active=is_active)
        if updated_project is None:
            error_message = f"Project with ID {project_id} not found."
            logger.warning(f"Update failed via web route: {error_message}")
    except SQLAlchemyError as e:
        error_message = f"Database error updating project: {e}"
        logger.error(f"Database error updating project {project_id} via web route: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Unexpected error in update_project_web for ID {project_id}: {e}", exc_info=True)
    if updated_project is not None and error_message is None:
        return RedirectResponse(request.url_for('ui_view_project', project_id=project_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error during update.')}"
        return RedirectResponse(str(request.url_for('ui_edit_project', project_id=project_id)) + error_param, status_code=303)

@router.post("/projects/{project_id}/delete", name="ui_delete_project")
async def delete_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles the deletion of a project."""
    logger.info(f"Web UI delete_project form submitted for ID: {project_id}")
    error_message = None
    try:
        async with db.begin():
            deleted = await delete_project_in_db(session=db, project_id=project_id)
            if not deleted:
                error_message = f"Failed to delete project {project_id} (DB error)."
                logger.error(f"{error_message} (Helper returned False)")
                raise SQLAlchemyError(error_message)
        logger.info(f"Project {project_id} deleted successfully via web route.")
    except SQLAlchemyError as e:
        error_message = error_message or f"Database error deleting project {project_id}: {e}"
        logger.error(error_message, exc_info=True)
    except Exception as e:
        error_message = f"Error deleting project {project_id}: {e}"
        logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_list_projects')
    if error_message:
        logger.info(f"Redirecting to project list with error indication for project {project_id}")
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/projects/{project_id}/activate", name="ui_activate_project")
async def activate_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles setting a project as active."""
    logger.info(f"Web UI activate_project request for ID: {project_id}")
    error_message = None
    try:
        async with db.begin():
            activated_project = await set_active_project_in_db(session=db, project_id=project_id)
            if activated_project is None:
                error_message = f"Project {project_id} not found to activate."
                logger.warning(error_message)
                raise ValueError(error_message)
        logger.info(f"Project {project_id} activated successfully via web route.")
    except (SQLAlchemyError, ValueError) as e:
        error_message = error_message or f"Error activating project {project_id}: {e}"
        logger.error(error_message, exc_info=True)
    except Exception as e:
        error_message = f"Unexpected error activating project {project_id}: {e}"
        logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_list_projects')
    if error_message:
        logger.info(f"Redirecting to project list with error indication for project {project_id}")
    return RedirectResponse(redirect_url, status_code=303)
