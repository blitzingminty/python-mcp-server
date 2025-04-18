# src/web_routes.py

import logging
# import httpx # Commented out as likely unused now
from typing import Optional, Dict, Union, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func # Needed for counts
from .database import get_db_session # Removed unused AsyncSessionFactory
from .models import Document, Project, MemoryEntry, MemoryEntryRelation # , DocumentVersion
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus

# --- Import all necessary DB helpers ---
from .mcp_db_helpers_project import create_project_in_db, update_project_in_db, delete_project_in_db, set_active_project_in_db
from .mcp_db_helpers_document import (
    add_document_in_db,
    update_document_in_db,
    delete_document_in_db,
    add_tag_to_document_db,
    remove_tag_from_document_db,
    add_document_version_db,
    get_document_version_content_db
)
from .mcp_db_helpers_memory import (
    get_memory_entry_db,
    add_memory_entry_db,
    update_memory_entry_db,
    delete_memory_entry_db,
    add_tag_to_memory_entry_db,
    remove_tag_from_memory_entry_db
)
# TODO: Add/confirm imports for link/unlink helpers if they exist, otherwise use direct logic below
# link_memory_entry_to_document, # Example if helper exists
# unlink_memory_entry_from_document, # Example if helper exists

# Removed duplicate private imports of mcp_db_helpers_memory to avoid conflicts and Pylance errors


# --- End Add ---

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Root Route (Dashboard) ---
@router.get("/", response_class=HTMLResponse, name="ui_root")
async def ui_root(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Serves the main dashboard/index page of the UI with entity counts."""
    logger.info("Web UI root requested")

    # --- TEMPORARY LOGGING ---
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request Scheme: {request.url.scheme}")
    logger.info(f"Request Host: {request.url.hostname}")
    logger.info(f"Request Port: {request.url.port}")
    logger.info(f"Request Headers: {request.headers}")
    try:
        test_url = request.url_for('ui_list_projects')
        logger.info(f"Generated URL for ui_list_projects: {test_url}")
    except Exception as e:
        logger.error(f"Could not generate URL for ui_list_projects: {e}")
    # --- END TEMPORARY LOGGING ---


    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")

    project_count: int | str = 0
    document_count: int | str = 0
    memory_entry_count: int | str = 0
    error_message = None

    try:
        project_count_result = await db.execute(select(func.count(Project.id)))
        project_count = project_count_result.scalar_one_or_none() or 0

        document_count_result = await db.execute(select(func.count(Document.id)))
        document_count = document_count_result.scalar_one_or_none() or 0

        memory_entry_count_result = await db.execute(select(func.count(MemoryEntry.id)))
        memory_entry_count = memory_entry_count_result.scalar_one_or_none() or 0

        logger.info(f"Dashboard counts: Projects={project_count}, Docs={document_count}, Memory={memory_entry_count}")

    except Exception as e:
        logger.error(f"Failed to fetch counts for dashboard: {e}", exc_info=True)
        error_message = "Could not load counts."
        project_count = 'N/A'
        document_count = 'N/A'
        memory_entry_count = 'N/A'

    context_data: Dict[str, Union[int, str, None]] = {
        "page_title": "MCP Server Dashboard",
        "welcome_message": "Welcome to the MCP Server Maintenance UI!",
        "project_count": project_count,
        "document_count": document_count,
        "memory_entry_count": memory_entry_count,
        "error": error_message
    }
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "data": context_data}
    )

# --- Project Routes ---
@router.get("/projects", response_class=HTMLResponse, name="ui_list_projects")
async def list_projects_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches projects from DB and renders the projects list page."""
    logger.info("Web UI projects list requested")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
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
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
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
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    project = await db.get(Project, project_id)
    if project is None: raise HTTPException(status_code=404, detail=f"Project with ID {project_id} not found")
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
        if created_project: new_project_id = created_project.id; logger.info(f"Project created directly via web route, ID: {new_project_id}")
    except SQLAlchemyError as e: error_message = f"Database error creating project: {e}"; logger.error(f"Database error creating project via web route: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Unexpected error in create_project_web: {e}", exc_info=True)
    if new_project_id is not None: return RedirectResponse(request.url_for('ui_view_project', project_id=new_project_id), status_code=303)
    else: error_param = f"?error={quote_plus(error_message or 'Unknown error')}"; return RedirectResponse(str(request.url_for('ui_new_project')) + error_param, status_code=303)

@router.get("/projects/{project_id}", response_class=HTMLResponse, name="ui_view_project")
async def view_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific project AND its related items, renders its detail page."""
    logger.info(f"Web UI project detail requested for ID: {project_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    project = None
    error_message = request.query_params.get("error")
    try:
        stmt = select(Project).options(selectinload(Project.documents), selectinload(Project.memory_entries)).where(Project.id == project_id)
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None: error_message = f"Project with ID {project_id} not found."; logger.warning(error_message); raise HTTPException(status_code=404, detail=error_message)
        else:
            if project.memory_entries: project.memory_entries.sort(key=lambda me: me.updated_at, reverse=True)
            logger.info(f"Found project '{project.name}' with {len(project.documents)} documents and {len(project.memory_entries)} memory entries for detail view.")
    except SQLAlchemyError as e: error_message = error_message or f"Database error fetching project details: {e}"; logger.error(f"Database error fetching project {project_id} for web UI: {e}", exc_info=True); raise HTTPException(status_code=500, detail=error_message)
    except HTTPException: raise
    except Exception as e: error_message = error_message or f"An unexpected server error occurred: {e}"; logger.error(f"Unexpected error fetching project {project_id} for web UI: {e}", exc_info=True); raise HTTPException(status_code=500, detail=error_message)
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
        if updated_project is None: error_message = f"Project with ID {project_id} not found."; logger.warning(f"Update failed via web route: {error_message}")
        else: logger.info(f"Project {project_id} updated successfully via web route.")
    except SQLAlchemyError as e: error_message = f"Database error updating project: {e}"; logger.error(f"Database error updating project {project_id} via web route: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Unexpected error in update_project_web for ID {project_id}: {e}", exc_info=True)
    if updated_project is not None and error_message is None: return RedirectResponse(request.url_for('ui_view_project', project_id=project_id), status_code=303)
    else: error_param = f"?error={quote_plus(error_message or 'Unknown error during update.')}"; return RedirectResponse(str(request.url_for('ui_edit_project', project_id=project_id)) + error_param, status_code=303)

@router.post("/projects/{project_id}/delete", name="ui_delete_project")
async def delete_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles the deletion of a project."""
    logger.info(f"Web UI delete_project form submitted for ID: {project_id}")
    error_message = None
    try:
        async with db.begin():
            deleted = await delete_project_in_db(session=db, project_id=project_id)
            if not deleted: error_message = f"Failed to delete project {project_id} (DB error)."; logger.error(f"{error_message} (Helper returned False)"); raise SQLAlchemyError(error_message)
        logger.info(f"Project {project_id} deleted successfully via web route.")
    except SQLAlchemyError as e: error_message = error_message or f"Database error deleting project {project_id}: {e}"; logger.error(error_message, exc_info=True)
    except Exception as e: error_message = f"Error deleting project {project_id}: {e}"; logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_list_projects')
    if error_message: logger.info(f"Redirecting to project list with error indication for project {project_id}") # redirect_url += f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/projects/{project_id}/activate", name="ui_activate_project")
async def activate_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles setting a project as active."""
    logger.info(f"Web UI activate_project request for ID: {project_id}")
    error_message = None
    try:
        async with db.begin():
            activated_project = await set_active_project_in_db(session=db, project_id=project_id)
            if activated_project is None: error_message = f"Project {project_id} not found to activate."; logger.warning(error_message); raise ValueError(error_message)
        logger.info(f"Project {project_id} activated successfully via web route.")
    except (SQLAlchemyError, ValueError) as e: error_message = error_message or f"Error activating project {project_id}: {e}"; logger.error(error_message, exc_info=True)
    except Exception as e: error_message = f"Unexpected error activating project {project_id}: {e}"; logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_list_projects')
    if error_message: logger.info(f"Redirecting to project list with error indication for project {project_id}") # redirect_url += f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

# --- Document Routes ---
@router.get("/documents", response_class=HTMLResponse, name="ui_list_documents_all")
async def list_all_documents_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches ALL documents across projects and renders the documents list page."""
    logger.info("Web UI list all documents requested")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    documents = []
    error_message = request.query_params.get("error")
    try:
        stmt = select(Document).options(selectinload(Document.project)).order_by(Document.project_id, Document.name)
        result = await db.execute(stmt)
        documents = result.scalars().all()
        logger.info(f"Found {len(documents)} total documents.")
    except SQLAlchemyError as e: error_message = error_message or f"Database error fetching documents: {e}"; logger.error(f"Database error fetching all documents: {e}", exc_info=True)
    except Exception as e: error_message = error_message or f"Unexpected server error: {e}"; logger.error(f"Unexpected error fetching all documents: {e}", exc_info=True)
    context_data: Dict[str, Any] = {"page_title": "All Documents", "documents": documents, "error": error_message}
    return templates.TemplateResponse("documents_list.html", {"request": request, "data": context_data})

@router.get("/documents/{doc_id}", response_class=HTMLResponse, name="ui_view_document")
async def view_document_web(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific document and its related items, renders its detail page."""
    logger.info(f"Web UI document detail requested for ID: {doc_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    document = None
    error_message = request.query_params.get("error")
    try:
        stmt = select(Document).options(selectinload(Document.tags), selectinload(Document.versions)).where(Document.id == doc_id)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None: error_message = f"Document with ID {doc_id} not found."; logger.warning(error_message); raise HTTPException(status_code=404, detail=error_message)
        else: logger.info(f"Found document '{document.name}' (ID: {doc_id})")
    except SQLAlchemyError as e: error_message = error_message or f"Error fetching document details: {e}"; logger.error(f"Database error fetching document {doc_id}: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Database error fetching document details.")
    except HTTPException: raise
    except Exception as e: error_message = error_message or f"Unexpected server error: {e}"; logger.error(f"Unexpected error fetching document {doc_id}: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Unexpected server error.")
    context_data: Dict[str, Any] = {"page_title": f"Document: {document.name}" if document else "Document Not Found", "document": document, "error": error_message}
    return templates.TemplateResponse("document_detail.html", {"request": request, "data": context_data})

@router.get("/projects/{project_id}/documents/new", response_class=HTMLResponse, name="ui_new_document")
async def new_document_form(project_id: int, request: Request):
    """Displays the form to create a new document for a specific project."""
    logger.info(f"Web UI new document form requested for project ID: {project_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    context_data: Dict[str, Any] = {
        "page_title": "Add New Document",
        "form_action": request.url_for('ui_create_document', project_id=project_id),
        "cancel_url": request.url_for('ui_view_project', project_id=project_id),
        "project_id": project_id,
        "error": request.query_params.get("error")
    }
    return templates.TemplateResponse("document_form.html", {"request": request, "data": context_data})

@router.post("/projects/{project_id}/documents", name="ui_create_document")
async def create_document_web(
    project_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    name: str = Form(...), path: str = Form(...), type: str = Form(...), content: str = Form(...), version: str = Form("1.0.0")
):
    """Handles the submission of the new document form."""
    logger.info(f"Web UI create_document form submitted for project {project_id}: name='{name}'")
    error_message = None; new_document_id = None; added_document = None
    redirect_url_on_error = str(request.url_for('ui_new_document', project_id=project_id))

    # --- Pre-check if project exists ---
    project = await db.get(Project, project_id)
    if project is None:
        error_message = f"Project with ID {project_id} not found."
        logger.warning(error_message)
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(redirect_url_on_error + error_param, status_code=303)

    try:
        async with db.begin():
            added_document = await add_document_in_db(session=db, project_id=project_id, name=name, path=path, content=content, type=type, version=version if version else "1.0.0")
            # If helper returns None now, it implies a DB issue within the helper, not a missing project
            if added_document is None:
                error_message = "Database error adding document (helper returned None)."
                logger.error(f"Add document failed: {error_message}")
                raise ValueError(error_message) # Raise to trigger rollback and outer handler

        new_document_id = added_document.id
        logger.info(f"Document created directly via web route, ID: {new_document_id}")
    except (SQLAlchemyError, ValueError) as e: # Catches ValueError raised above
        error_message = error_message or f"Error adding document: {e}"
        logger.error(f"Error in create_document_web for project {project_id}: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error in create_document_web for project {project_id}: {e}", exc_info=True)

    # --- Redirect logic ---
    if new_document_id is not None and error_message is None:
        return RedirectResponse(request.url_for('ui_view_document', doc_id=new_document_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error adding document.')}"
        return RedirectResponse(redirect_url_on_error + error_param, status_code=303)

@router.get("/documents/{doc_id}/edit", response_class=HTMLResponse, name="ui_edit_document")
async def edit_document_form(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Displays the form pre-filled for editing document metadata."""
    logger.info(f"Web UI edit document form requested for ID: {doc_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    document = await db.get(Document, doc_id)
    if document is None: raise HTTPException(status_code=404, detail=f"Document with ID {doc_id} not found")
    context_data = {
        "page_title": f"Edit Document: {document.name}",
        "form_action": request.url_for('ui_update_document', doc_id=doc_id),
        "cancel_url": request.url_for('ui_view_document', doc_id=doc_id),
        "error": request.query_params.get("error"), "document": document, "is_edit_mode": True
    }
    return templates.TemplateResponse("document_form.html", {"request": request, "data": context_data})

@router.post("/documents/{doc_id}/edit", name="ui_update_document")
async def update_document_web(
    doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    name: str = Form(...), path: str = Form(...), type: str = Form(...)
):
    """Handles the submission of the edit document form (metadata only)."""
    logger.info(f"Web UI update_document form submitted for ID: {doc_id}")
    error_message = None; updated_document = None
    try:
        async with db.begin():
             updated_document = await update_document_in_db(session=db, document_id=doc_id, name=name, path=path, type=type)
             if updated_document is None: error_message = f"Document with ID {doc_id} not found."; logger.warning(f"Update failed: {error_message}"); raise ValueError(error_message)
        logger.info(f"Document {doc_id} metadata updated successfully via web route.")
    except (SQLAlchemyError, ValueError) as e: error_message = error_message or f"Database error updating document: {e}"; logger.error(f"Error updating document {doc_id} via web: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Error updating document {doc_id} via web: {e}", exc_info=True)
    if updated_document is not None and error_message is None: return RedirectResponse(request.url_for('ui_view_document', doc_id=doc_id), status_code=303)
    else: error_param = f"?error={quote_plus(error_message or 'Unknown error during update.')}"; return RedirectResponse(str(request.url_for('ui_edit_document', doc_id=doc_id)) + error_param, status_code=303)

@router.post("/documents/{doc_id}/delete", name="ui_delete_document")
async def delete_document_web(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles the deletion of a document."""
    logger.info(f"Web UI delete_document form submitted for ID: {doc_id}")
    project_id_to_redirect = None; error_message = None
    try:
        doc_to_delete = await db.get(Document, doc_id)
        if doc_to_delete:
            project_id_to_redirect = doc_to_delete.project_id; logger.debug(f"Document {doc_id} belongs to project {project_id_to_redirect}. Attempting delete.")
            async with db.begin():
                deleted = await delete_document_in_db(session=db, document_id=doc_id)
                if not deleted: error_message = f"Failed to delete document {doc_id} (DB error)."; logger.error(f"{error_message} (Helper returned False)"); raise SQLAlchemyError(error_message)
            logger.info(f"Document {doc_id} committed for deletion via web route.")
        else: logger.warning(f"Document {doc_id} not found for deletion. Assuming success for redirect.")
    except SQLAlchemyError as e: error_message = error_message or f"Database error deleting document {doc_id}: {e}"; logger.error(error_message, exc_info=True)
    except Exception as e: error_message = f"Error deleting document {doc_id}: {e}"; logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_view_project', project_id=project_id_to_redirect) if project_id_to_redirect else request.url_for('ui_list_projects')
    if error_message: logger.warning(f"Redirecting after delete failure for doc {doc_id}: {error_message}") # redirect_url += f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/documents/{doc_id}/tags/add", name="ui_add_tag_to_document")
async def add_tag_to_document_web(
    doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session), tag_name: str = Form(...)
):
    """Handles adding a tag to a document via web form."""
    logger.info(f"Web UI add tag '{tag_name}' request for document ID: {doc_id}")
    error_message = None
    redirect_url = request.url_for('ui_view_document', doc_id=doc_id)

    # --- Pre-check if document exists ---
    doc = await db.get(Document, doc_id)
    if doc is None:
        error_message = f"Document {doc_id} not found."
        logger.warning(error_message)
        redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
        return RedirectResponse(redirect_url, status_code=303)

    if not tag_name or tag_name.isspace():
        error_message = "Tag name cannot be empty."
    else:
        try:
            async with db.begin():
                success = await add_tag_to_document_db(session=db, document_id=doc_id, tag_name=tag_name.strip())
                if not success:
                    # We know the doc exists from the check above, so failure means DB error in helper
                    error_message = f"Failed to add tag '{tag_name}' (DB error)."
                    logger.error(f"{error_message} (add_tag_to_document_db returned False)")
                    raise ValueError(error_message) # Raise to trigger rollback and outer handler
            logger.info(f"Tag '{tag_name}' added/associated with document {doc_id} via web.")
        except (SQLAlchemyError, ValueError) as e: # Catches ValueError raised above
            error_message = error_message or f"Error adding tag: {e}"
            logger.error(f"Error adding tag '{tag_name}' to doc {doc_id} via web: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error adding tag '{tag_name}' to doc {doc_id} via web: {e}", exc_info=True)

    # --- Redirect logic ---
    if error_message:
        redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/documents/{doc_id}/tags/remove", name="ui_remove_tag_from_document")
async def remove_tag_from_document_web(
    doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session), tag_name: str = Form(...)
):
    """Handles removing a tag from a document via web form."""
    logger.info(f"Web UI remove tag '{tag_name}' request for document ID: {doc_id}")
    error_message = None
    if not tag_name: error_message = "Tag name not provided for removal."
    else:
        try:
            async with db.begin():
                success = await remove_tag_from_document_db(session=db, document_id=doc_id, tag_name=tag_name)
                if not success: error_message = f"Failed to remove tag '{tag_name}' due to database error."; raise SQLAlchemyError(error_message)
            logger.info(f"Tag '{tag_name}' removed/disassociated from document {doc_id} via web.")
        except SQLAlchemyError as e: error_message = error_message or f"Database error removing tag: {e}"; logger.error(f"Error removing tag '{tag_name}' from doc {doc_id} via web: {e}", exc_info=True)
        except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Error removing tag '{tag_name}' from doc {doc_id} via web: {e}", exc_info=True)
    redirect_url = request.url_for('ui_view_document', doc_id=doc_id)
    if error_message: redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.get("/versions/{version_id}", response_class=HTMLResponse, name="ui_view_version")
async def view_document_version_web(version_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific document version and renders its detail page."""
    logger.info(f"Web UI document version detail requested for Version ID: {version_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    version = None; error_message = None
    try:
        version = await get_document_version_content_db(session=db, version_id=version_id)
        if version is None: error_message = f"Document Version with ID {version_id} not found."; logger.warning(error_message); raise HTTPException(status_code=404, detail=error_message)
        else: logger.info(f"Found document version '{version.version}' (ID: {version_id}) for doc ID {version.document_id}")
    except SQLAlchemyError as e: error_message = f"Error fetching document version details: {e}"; logger.error(f"Database error fetching document version {version_id}: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Database error fetching version details.")
    except HTTPException: raise
    except Exception as e: error_message = f"Unexpected server error: {e}"; logger.error(f"Unexpected error fetching document version {version_id}: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Unexpected server error.")
    context_data = {"page_title": f"Version {version.version} of Document {version.document.name}" if version and version.document else "Version Not Found", "version": version, "error": error_message}
    return templates.TemplateResponse("version_detail.html", {"request": request, "data": context_data})

@router.get("/documents/{doc_id}/new_version", response_class=HTMLResponse, name="ui_new_version_form")
async def new_document_version_form(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Displays the form to create a new version of a document."""
    logger.info(f"Web UI new version form requested for document ID: {doc_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    document = await db.get(Document, doc_id)
    if document is None: raise HTTPException(status_code=404, detail=f"Document with ID {doc_id} not found")
    context_data = {
        "page_title": f"Create New Version for '{document.name}'",
        "form_action": request.url_for('ui_create_version', doc_id=doc_id),
        "cancel_url": request.url_for('ui_view_document', doc_id=doc_id),
        "document": document,
        "error": request.query_params.get("error")
    }
    return templates.TemplateResponse("version_form.html", {"request": request, "data": context_data})

@router.post("/documents/{doc_id}/versions", name="ui_create_version")
async def create_document_version_web(
    doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    version_string: str = Form(...), content: str = Form(...)
):
    """Handles submission of the new document version form."""
    logger.info(f"Web UI create new version submitted for document {doc_id}: version='{version_string}'")
    error_message = None; updated_doc = None; new_version = None
    if not version_string or version_string.isspace(): error_message = "Version string cannot be empty."
    if error_message: error_param = f"?error={quote_plus(error_message)}"; return RedirectResponse(str(request.url_for('ui_new_version_form', doc_id=doc_id)) + error_param, status_code=303)
    try:
        async with db.begin():
            updated_doc, new_version = await add_document_version_db(session=db, document_id=doc_id, content=content, version_string=version_string.strip())
            if updated_doc is None or new_version is None: error_message = f"Failed to add version '{version_string}'. Document {doc_id} not found or DB error occurred."; logger.error(f"Create version failed: {error_message}"); raise ValueError(error_message)
        logger.info(f"Version '{new_version.version}' (ID: {new_version.id}) created for document {doc_id} via web.")
    except ValueError as ve: error_message = str(ve); logger.warning(f"Validation error creating version for doc {doc_id}: {error_message}", exc_info=False) # Don't need full stack for validation error
    except SQLAlchemyError as e: error_message = f"Database error creating version: {e}"; logger.error(f"Database error creating version for doc {doc_id}: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Unexpected error creating version for doc {doc_id}: {e}", exc_info=True)
    if updated_doc is not None and new_version is not None and error_message is None: return RedirectResponse(request.url_for('ui_view_document', doc_id=doc_id), status_code=303)
    else: error_param = f"?error={quote_plus(error_message or 'Unknown error creating version.')}"; return RedirectResponse(str(request.url_for('ui_new_version_form', doc_id=doc_id)) + error_param, status_code=303)


# --- Memory Entry Routes ---
@router.get("/memory", response_class=HTMLResponse, name="ui_list_memory_entries_all")
async def list_all_memory_entries_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches ALL memory entries across projects and renders the list page."""
    logger.info("Web UI list all memory entries requested")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    memory_entries = []; error_message = request.query_params.get("error")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.project)).order_by(MemoryEntry.updated_at.desc())
        result = await db.execute(stmt)
        memory_entries = result.scalars().all(); logger.info(f"Found {len(memory_entries)} total memory entries.")
    except SQLAlchemyError as e: error_message = error_message or f"Database error fetching entries: {e}"; logger.error(f"Database error fetching all memory entries: {e}", exc_info=True)
    except Exception as e: error_message = error_message or f"Unexpected server error: {e}"; logger.error(f"Unexpected error fetching all memory entries: {e}", exc_info=True)
    context_data: Dict[str, Any] = {"page_title": "All Memory Entries", "memory_entries": memory_entries, "error": error_message}
    return templates.TemplateResponse("memory_entries_list.html", {"request": request, "data": context_data})

# Replace existing view_memory_entry_web function
@router.get("/memory/{entry_id}", response_class=HTMLResponse, name="ui_view_memory_entry")
async def view_memory_entry_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session)
):
    """Fetches a specific memory entry, its relationships, and available linkable items."""
    logger.info(f"Web UI memory entry detail requested for ID: {entry_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")

    error_message = request.query_params.get("error")
    entry = None
    available_documents = []
    available_memory_entries = [] # Initialize available memory entries list

    try:
        entry = await get_memory_entry_db(session=db, entry_id=entry_id)
        if entry is None:
            error_message = f"Memory Entry with ID {entry_id} not found."
            raise HTTPException(status_code=404, detail=error_message)
        logger.info(f"Found memory entry '{entry.title}' (ID: {entry_id})")

        # --- Query for available documents and memory entries in the same project ---
        if entry.project_id:
            # Documents
            doc_stmt = select(Document).where(Document.project_id == entry.project_id).order_by(Document.name)
            doc_results = await db.execute(doc_stmt)
            available_documents = doc_results.scalars().all()
            logger.debug(f"Found {len(available_documents)} documents in project {entry.project_id} for potential linking.")

            # --- ADDED: Query for other memory entries ---
            mem_stmt = select(MemoryEntry).where(
                MemoryEntry.project_id == entry.project_id,
                MemoryEntry.id != entry_id # Exclude the current entry
            ).order_by(MemoryEntry.title)
            mem_results = await db.execute(mem_stmt)
            available_memory_entries = mem_results.scalars().all()
            logger.debug(f"Found {len(available_memory_entries)} other memory entries in project {entry.project_id} for potential linking.")
            # --- END ADDED ---

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching memory entry {entry_id} or related data: {e}", exc_info=True)
        error_message = error_message or f"Database error fetching data: {e}"
        raise HTTPException(status_code=500, detail=error_message)
    except HTTPException:
         raise # Re-raise 404
    except Exception as e:
         logger.error(f"Unexpected error fetching memory entry {entry_id}: {e}", exc_info=True)
         error_message = error_message or f"Unexpected server error: {e}"
         raise HTTPException(status_code=500, detail=error_message)

    # Format related data (keep existing formatting)
    tags = sorted([tag.name for tag in entry.tags]) if entry.tags else []
    linked_docs = [{"id": doc.id, "name": doc.name} for doc in entry.documents] if entry.documents else []
    # Ensure titles are present or default for relations display
    relations_from = [{"relation_id": rel.id, "type": rel.relation_type, "target_id": rel.target_memory_entry_id, "target_title": rel.target_entry.title if rel.target_entry else "N/A"} for rel in entry.source_relations] if entry.source_relations else []
    relations_to = [{"relation_id": rel.id, "type": rel.relation_type, "source_id": rel.source_memory_entry_id, "source_title": rel.source_entry.title if rel.source_entry else "N/A"} for rel in entry.target_relations] if entry.target_relations else []


    context_data = {
        "page_title": f"Memory Entry: {entry.title}",
        "entry": entry,
        "tags": tags,
        "linked_documents": linked_docs,
        "relations_from": relations_from,
        "relations_to": relations_to,
        "available_documents": available_documents,
        "available_memory_entries": available_memory_entries, # --- ADDED: Pass available entries ---
        "error": error_message
    }
    return templates.TemplateResponse(
        "memory_detail.html",
        {"request": request, "data": context_data}
    )

@router.get("/projects/{project_id}/memory/new", response_class=HTMLResponse, name="ui_new_memory_entry")
async def new_memory_entry_form(project_id: int, request: Request):
    """Displays the form to create a new memory entry."""
    logger.info(f"Web UI new memory entry form requested for project ID: {project_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    context_data = {
        "page_title": "Add New Memory Entry",
        "form_action": request.url_for('ui_create_memory_entry', project_id=project_id),
        "cancel_url": request.url_for('ui_view_project', project_id=project_id),
        "project_id": project_id, "error": request.query_params.get("error")
    }
    return templates.TemplateResponse("memory_form.html", {"request": request, "data": context_data})

@router.post("/projects/{project_id}/memory", name="ui_create_memory_entry")
async def create_memory_entry_web(
    project_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    title: str = Form(...), type: str = Form(...), content: str = Form(...)
):
    """Handles submission of the new memory entry form."""
    logger.info(f"Web UI create memory entry submitted for project {project_id}: title='{title}'")
    error_message = None; new_entry = None; new_entry_id = None
    redirect_url_on_error = str(request.url_for('ui_new_memory_entry', project_id=project_id))

    # --- Pre-check if project exists ---
    project = await db.get(Project, project_id)
    if project is None:
        error_message = f"Project with ID {project_id} not found."
        logger.warning(error_message)
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(redirect_url_on_error + error_param, status_code=303)

    try:
        async with db.begin():
            new_entry = await add_memory_entry_db(session=db, project_id=project_id, title=title, type=type, content=content)
            # If helper returns None now, it implies a DB issue within the helper, not a missing project
            if new_entry is None:
                error_message = "Database error adding memory entry (helper returned None)."
                logger.error(f"Add memory entry failed: {error_message}")
                raise ValueError(error_message) # Raise to trigger rollback and outer handler

        new_entry_id = new_entry.id
        logger.info(f"Memory entry created via web route, ID: {new_entry_id}")
    except (SQLAlchemyError, ValueError) as e: # Catches ValueError raised above
        error_message = error_message or f"Error adding memory entry: {e}"
        logger.error(f"Error in create_memory_entry_web for project {project_id}: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error in create_memory_entry_web for project {project_id}: {e}", exc_info=True)

    # --- Redirect logic ---
    if new_entry_id is not None and error_message is None:
        return RedirectResponse(request.url_for('ui_view_memory_entry', entry_id=new_entry_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error adding memory entry.')}"
        return RedirectResponse(redirect_url_on_error + error_param, status_code=303)

@router.get("/memory/{entry_id}/edit", response_class=HTMLResponse, name="ui_edit_memory_entry")
async def edit_memory_entry_form(entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Displays the form pre-filled for editing an existing memory entry."""
    logger.info(f"Web UI edit memory entry form requested for ID: {entry_id}")
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Server configuration error")
    entry = await db.get(MemoryEntry, entry_id)
    if entry is None: raise HTTPException(status_code=404, detail=f"Memory Entry with ID {entry_id} not found")
    context_data = {
        "page_title": f"Edit Memory Entry: {entry.title}",
        "form_action": request.url_for('ui_update_memory_entry', entry_id=entry_id),
        "cancel_url": request.url_for('ui_view_memory_entry', entry_id=entry_id),
        "error": request.query_params.get("error"), "entry": entry, "is_edit_mode": True
    }
    return templates.TemplateResponse("memory_form.html", {"request": request, "data": context_data})

@router.post("/memory/{entry_id}/edit", name="ui_update_memory_entry")
async def update_memory_entry_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    title: str = Form(...), type: str = Form(...), content: str = Form(...)
):
    """Handles submission of the edit memory entry form."""
    logger.info(f"Web UI update memory entry submitted for ID: {entry_id}")
    error_message = None; updated_entry = None
    try:
        async with db.begin():
            updated_entry = await update_memory_entry_db(session=db, entry_id=entry_id, title=title, type=type, content=content)
            if updated_entry is None: error_message = f"Memory Entry with ID {entry_id} not found."; logger.warning(f"Update failed: {error_message}"); raise ValueError(error_message)
        logger.info(f"Memory entry {entry_id} updated successfully via web route.")
    except (SQLAlchemyError, ValueError) as e: error_message = error_message or f"Database error updating memory entry: {e}"; logger.error(f"Error updating memory entry {entry_id} via web: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Error updating memory entry {entry_id} via web: {e}", exc_info=True)
    if updated_entry is not None and error_message is None: return RedirectResponse(request.url_for('ui_view_memory_entry', entry_id=entry_id), status_code=303)
    else: error_param = f"?error={quote_plus(error_message or 'Unknown error during update.')}"; return RedirectResponse(str(request.url_for('ui_edit_memory_entry', entry_id=entry_id)) + error_param, status_code=303)

@router.post("/memory/{entry_id}/delete", name="ui_delete_memory_entry")
async def delete_memory_entry_web(entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles deletion of a memory entry."""
    logger.info(f"Web UI delete memory entry request for ID: {entry_id}")
    error_message = None; project_id_to_redirect = None
    try:
        async with db.begin():
            deleted, project_id = await delete_memory_entry_db(session=db, entry_id=entry_id)
            project_id_to_redirect = project_id
            if not deleted:
                error_message = f"Memory Entry {entry_id} not found." if project_id is None else f"Database error deleting memory entry {entry_id}."
                logger.error(f"Deletion failed: {error_message}"); raise SQLAlchemyError(error_message)
        logger.info(f"Memory entry {entry_id} deleted successfully via web route.")
    except SQLAlchemyError as e: error_message = error_message or f"Database error during deletion: {e}"; logger.error(error_message, exc_info=True)
    except Exception as e: error_message = f"Error deleting memory entry {entry_id}: {e}"; logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_view_project', project_id=project_id_to_redirect) if project_id_to_redirect else request.url_for('ui_list_projects')
    if error_message: logger.warning(f"Redirecting after delete failure for memory entry {entry_id}: {error_message}") # redirect_url += f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/memory/{entry_id}/tags/add", name="ui_add_tag_to_memory_entry")
async def add_tag_to_memory_entry_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session), tag_name: str = Form(...)
):
    """Handles adding a tag to a memory entry."""
    logger.info(f"Web UI add tag '{tag_name}' request for memory entry ID: {entry_id}")
    error_message = None
    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)

    # --- Pre-check if memory entry exists ---
    entry = await db.get(MemoryEntry, entry_id)
    if entry is None:
        error_message = f"Memory Entry {entry_id} not found."
        logger.warning(error_message)
        redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
        return RedirectResponse(redirect_url, status_code=303)

    if not tag_name or tag_name.isspace():
        error_message = "Tag name cannot be empty."
    else:
        try:
            async with db.begin():
                success = await add_tag_to_memory_entry_db(session=db, entry_id=entry_id, tag_name=tag_name.strip())
                if not success:
                    # We know the entry exists from the check above, so failure means DB error in helper
                    error_message = f"Failed to add tag '{tag_name}' (DB error)."
                    logger.error(f"{error_message} (add_tag_to_memory_entry_db returned False)")
                    raise ValueError(error_message) # Raise to trigger rollback and outer handler
            logger.info(f"Tag '{tag_name}' added/associated with memory entry {entry_id} via web.")
        except (SQLAlchemyError, ValueError) as e: # Catches ValueError raised above
            error_message = error_message or f"Error adding tag: {e}"
            logger.error(f"Error adding tag '{tag_name}' to memory {entry_id} via web: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error adding tag '{tag_name}' to memory {entry_id} via web: {e}", exc_info=True)

    # --- Redirect logic ---
    if error_message:
        redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/memory/{entry_id}/tags/remove", name="ui_remove_tag_from_memory_entry")
async def remove_tag_from_memory_entry_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session), tag_name: str = Form(...)
):
    """Handles removing a tag from a memory entry."""
    logger.info(f"Web UI remove tag '{tag_name}' request for memory entry ID: {entry_id}")
    error_message = None
    if not tag_name: error_message = "Tag name not provided for removal."
    else:
        try:
            async with db.begin():
                success = await remove_tag_from_memory_entry_db(session=db, entry_id=entry_id, tag_name=tag_name)
                if not success: error_message = f"Failed to remove tag '{tag_name}' due to database error."; raise SQLAlchemyError(error_message)
            logger.info(f"Tag '{tag_name}' removed/disassociated from memory entry {entry_id} via web.")
        except SQLAlchemyError as e: error_message = error_message or f"Database error removing tag: {e}"; logger.error(f"Error removing tag '{tag_name}' from memory {entry_id} via web: {e}", exc_info=True)
        except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Error removing tag '{tag_name}' from memory {entry_id} via web: {e}", exc_info=True)
    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)
    if error_message: redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

# --- START: Memory-Document Linking Routes (Phase 6) ---
@router.post("/memory/{entry_id}/links/documents", name="ui_link_memory_to_document")
async def link_memory_to_document_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    document_id: int = Form(...) # Get document ID from form select
):
    """Handles linking a selected document to a memory entry."""
    logger.info(f"Web UI: Linking document {document_id} to memory entry {entry_id}")
    error_message = None
    try:
        async with db.begin():
             mem_entry = await db.get(MemoryEntry, entry_id, options=[selectinload(MemoryEntry.documents)])
             doc_to_link = await db.get(Document, document_id)
             if not mem_entry: error_message = f"Memory Entry {entry_id} not found."
             elif not doc_to_link: error_message = f"Document {document_id} not found."
             elif doc_to_link in mem_entry.documents: logger.info("Document already linked.") # Use logger instead of unused message
             else: mem_entry.documents.append(doc_to_link); await db.flush(); logger.info(f"Document '{doc_to_link.name}' linked successfully.") # Use logger
             if error_message: raise ValueError(error_message)
    except (SQLAlchemyError, ValueError) as e: error_message = error_message or f"Error linking document: {e}"; logger.error(f"Error linking doc {document_id} to memory {entry_id}: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Error linking doc {document_id} to memory {entry_id}: {e}", exc_info=True)
    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)
    redirect_url = str(redirect_url)
    if error_message:
        redirect_url += f"?error={quote_plus(error_message)}"
    # elif message: # Optional success flash
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/memory/{entry_id}/links/documents/{doc_id}/unlink", name="ui_unlink_memory_from_document")
async def unlink_memory_from_document_web(
    entry_id: int, doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)
):
    """Handles unlinking a document from a memory entry."""
    logger.info(f"Web UI: Unlinking document {doc_id} from memory entry {entry_id}")
    error_message = None
    try:
        async with db.begin():
             mem_entry = await db.get(MemoryEntry, entry_id, options=[selectinload(MemoryEntry.documents)])
             doc_to_unlink = await db.get(Document, doc_id)
             if not mem_entry: error_message = f"Memory Entry {entry_id} not found."
             elif not doc_to_unlink: error_message = f"Document {doc_id} not found (cannot unlink)."
             elif doc_to_unlink not in mem_entry.documents: logger.info("Link not found.") # Use logger
             else: mem_entry.documents.remove(doc_to_unlink); await db.flush(); logger.info(f"Document '{doc_to_unlink.name}' unlinked successfully.") # Use logger
             if error_message: raise ValueError(error_message)
    except (SQLAlchemyError, ValueError) as e: error_message = error_message or f"Error unlinking document: {e}"; logger.error(f"Error unlinking doc {doc_id} from memory {entry_id}: {e}", exc_info=True)
    except Exception as e: error_message = f"An unexpected error occurred: {e}"; logger.error(f"Error unlinking doc {doc_id} from memory {entry_id}: {e}", exc_info=True)
    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)
    redirect_url = str(redirect_url)
    if error_message:
        redirect_url += f"?error={quote_plus(error_message)}"
    # elif message: # Optional success flash
    return RedirectResponse(redirect_url, status_code=303)
# --- END: Memory-Document Linking Routes (Phase 6) ---

# --- ADDED for Phase 6: Memory-Memory Linking ---

@router.post("/memory/{entry_id}/links/memory", name="ui_link_memory_to_memory")
async def link_memory_to_memory_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    target_entry_id: int = Form(...),
    relation_type: Optional[str] = Form(None)
):
    """Handles linking another memory entry to the current one."""
    logger.info(f"Web UI: Linking memory entry {target_entry_id} to {entry_id} (type: {relation_type})")
    error_message = None

    if entry_id == target_entry_id:
            error_message = "Cannot link an entry to itself."
    else:
        try:
            async with db.begin():
                # Ideally call helper: from .mcp_server_instance import link_memory_entries
                # Re-implementing logic temporarily
                source_entry = await db.get(MemoryEntry, entry_id)
                target_entry = await db.get(MemoryEntry, target_entry_id)

                if not source_entry: error_message = f"Source Memory Entry {entry_id} not found."
                elif not target_entry: error_message = f"Target Memory Entry {target_entry_id} not found."
                else:
                    # Check if relation already exists (optional)
                    # stmt_exists = select(MemoryEntryRelation).where(...) etc.
                    new_relation = MemoryEntryRelation(
                        source_memory_entry_id=entry_id,
                        target_memory_entry_id=target_entry_id,
                        relation_type=relation_type if relation_type else None # Ensure None not ""
                    )
                    db.add(new_relation)
                    await db.flush()
                    logger.info(f"Linked entry {target_entry_id} to {entry_id}.") # Use logger

                if error_message: raise ValueError(error_message)

        except (SQLAlchemyError, ValueError) as e:
                if not error_message: error_message = f"Error linking memory entries: {e}"
                logger.error(f"Error linking memory {target_entry_id} to {entry_id}: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error linking memory {target_entry_id} to {entry_id}: {e}", exc_info=True)

    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)
    redirect_url = str(redirect_url)
    if error_message:
        redirect_url += f"?error={quote_plus(error_message)}"
    # elif message: # Optional success flash
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/memory/relations/{relation_id}/unlink", name="ui_unlink_memory_relation")
async def unlink_memory_relation_web(
    relation_id: int, request: Request, db: AsyncSession = Depends(get_db_session)
):
    """Handles unlinking two memory entries via the relation ID."""
    logger.info(f"Web UI: Unlinking memory relation ID: {relation_id}")
    error_message = None
    # Determine where to redirect: back to the source entry of the relation
    source_entry_id = None
    redirect_to_memory_list = False

    try:
        async with db.begin():
            # Fetch relation first to get source ID for redirect
            relation = await db.get(MemoryEntryRelation, relation_id)
            if relation:
                source_entry_id = relation.source_memory_entry_id
                logger.info(f"Deleting relation ID: {relation.id} (linking {relation.source_memory_entry_id} -> {relation.target_memory_entry_id})")
                await db.delete(relation)
                await db.flush()
                logger.info("Memory relation unlinked successfully.") # Log instead of unused message
            else:
                # Relation already gone? Treat as success for user.
                logger.warning(f"Relation ID {relation_id} not found for unlinking (already unlinked?).") # Log instead of unused message
                redirect_to_memory_list = True # Cant determine source entry

    except SQLAlchemyError as e:
            error_message = f"Database error unlinking relation: {e}"
            logger.error(f"Error unlinking memory relation {relation_id}: {e}", exc_info=True)
            # Try to fetch source_entry_id even on error for redirect? Risky. Fallback to list.
            redirect_to_memory_list = True
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error unlinking memory relation {relation_id}: {e}", exc_info=True)
        redirect_to_memory_list = True

    # Redirect back to source memory entry page if known, otherwise list page
    if source_entry_id and not redirect_to_memory_list:
            redirect_url = request.url_for('ui_view_memory_entry', entry_id=source_entry_id)
    else:
            redirect_url = request.url_for('ui_list_memory_entries_all') # Fallback

    if error_message:
        redirect_url = str(redirect_url) + "?" + (quote_plus(error_message) if error_message else "")
    # elif message and "successfully" in message: # Optional success flash
    return RedirectResponse(redirect_url, status_code=303)
# --- END ADDED for Phase 6 ---
