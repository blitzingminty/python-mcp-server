# src/web_routes.py

import logging
import httpx # Keep httpx import if needed for other parts, or remove if unused
from typing import Any, Dict, Optional
# Add HTTPException
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload  # Ensure this is imported
from .database import get_db_session
from .models import Document # Keep model imports
from .models import Project
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus

# --- Import the new DB helpers for tags ---
from .mcp_server_instance import (
    _create_project_in_db, _update_project_in_db, _delete_project_in_db,
    _set_active_project_in_db, _add_document_in_db, _update_document_in_db,
    _delete_document_in_db,
    _add_tag_to_document_db,      # <-- Add this import
    _remove_tag_from_document_db  # <-- Add this import
)


# --- Add config import for port ---
from .config import settings
# --- End Add ---

logger = logging.getLogger(__name__)
router = APIRouter()


# Helper function to build MCP endpoint URL (if still needed)
def get_mcp_endpoint_url() -> str:
    # Construct the base URL for the server itself
    base_url = f"http://{settings.SERVER_HOST}:{settings.SERVER_PORT}"
    # Append the MCP mount path and the messages endpoint
    # Add the fixed session ID as a query parameter
    return f"{base_url}/mcp/messages/?session_id=webapp-session"


@router.get("/", response_class=HTMLResponse, name="ui_root")
async def ui_root(request: Request):
    """Serves the main dashboard/index page of the UI."""
    logger.info("Web UI root requested")
    templates = request.app.state.templates
    if not templates:
        return HTMLResponse("Server configuration error: Templates not found.", status_code=500)
    context_data = {
        "page_title": "MCP Server Maintenance",
        "welcome_message": "Welcome to the MCP Server Maintenance UI!"
    }
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "data": context_data}
    )


@router.get("/projects", response_class=HTMLResponse, name="ui_list_projects")
async def list_projects_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches projects from DB and renders the projects list page."""
    logger.info("Web UI projects list requested")
    templates = request.app.state.templates
    if not templates:
        return HTMLResponse("Server configuration error: Templates not found.", status_code=500)
    projects = []
    error_message = None
    try:
        stmt = select(Project).order_by(Project.name)
        result = await db.execute(stmt)
        projects = result.scalars().all()
    except Exception as e:
        logger.error(
            f"Failed to fetch projects for web UI: {e}", exc_info=True)
        error_message = f"Error fetching projects: {e}"
    context_data = {
        "page_title": "Projects List",
        "projects": projects,
        "error": error_message
    }
    return templates.TemplateResponse(
        "projects.html",
        {"request": request, "data": context_data}
    )


# --- ADD NEW ROUTE: Display New Project Form ---
@router.get("/projects/new", response_class=HTMLResponse, name="ui_new_project")
async def new_project_form(request: Request):
    """Displays the form to create a new project."""
    logger.info("Web UI new project form requested")
    templates = request.app.state.templates
    if not templates:
        return HTMLResponse("Server configuration error: Templates not found.", status_code=500)

    context_data = {
        "page_title": "Create New Project",
        "form_action": request.url_for('ui_create_project'),  # POST target
        # Get potential error from redirect
        "error": request.query_params.get("error"),
        "cancel_url": request.url_for('ui_list_projects')
    }
    return templates.TemplateResponse(
        "project_form.html",  # Reusable form template
        {"request": request, "data": context_data}
    )


# --- ADD NEW ROUTE: Display Edit Project Form ---
@router.get("/projects/{project_id}/edit", response_class=HTMLResponse, name="ui_edit_project")
async def edit_project_form(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
):
    """Displays the form pre-filled with data for editing an existing project."""
    logger.info(f"Web UI edit project form requested for ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        # Log error or return generic error response
        logger.error("Server configuration error: Templates not found.")
        raise HTTPException(
            status_code=500, detail="Server configuration error")

    # Efficient way to get by primary key
    project = await db.get(Project, project_id)
    if project is None:
        logger.warning(
            f"Edit requested for non-existent project ID: {project_id}")
        raise HTTPException(
            status_code=404, detail=f"Project with ID {project_id} not found")

    context_data = {
        "page_title": f"Edit Project: {project.name}",
        # The form will POST to the update handler (Step 4)
        "form_action": request.url_for('ui_update_project', project_id=project_id),
        # Link back to detail view
        "cancel_url": request.url_for('ui_view_project', project_id=project_id),
        # Get potential error from redirect (if update fails later)
        "error": request.query_params.get("error"),
        "project": project,  # Pass the fetched project object
        "is_edit_mode": True  # Flag for the template
    }
    return templates.TemplateResponse(
        "project_form.html",  # Reusable form template
        {"request": request, "data": context_data}
    )


# --- MODIFIED ROUTE: Handle New Project Form Submission (Direct DB Call) ---
@router.post("/projects", name="ui_create_project")
async def create_project_web(
    request: Request,
    db: AsyncSession = Depends(get_db_session),  # <-- Inject DB session
    # Extract form data (keep this part)
    name: str = Form(...),
    path: str = Form(...),
    description: Optional[str] = Form(None),
    # Gets value="true" or the hidden value="false"
    is_active: bool = Form(False)
):
    """Handles the submission of the new project form. Calls DB logic directly."""
    logger.info(f"Web UI create_project form submitted: name='{name}'")
    error_message = None
    new_project_id = None

    try:
        # --- REMOVE MCP Payload Construction and httpx Call ---

        # --- Directly call the database logic helper function ---
        # Use a transaction managed by the injected session
        async with db.begin():
             created_project = await _create_project_in_db(
                 session=db,  # Pass the injected session
                 name=name,
                 path=path,
                 description=description if description else None,  # Ensure None if empty
                 is_active=is_active
             )
        new_project_id = created_project.id
        logger.info(
            f"Project created directly via web route, ID: {new_project_id}")

    # --- Keep Exception Handling (adjust log messages slightly if desired) ---
    except SQLAlchemyError as e:
         # Simplified message for user
         error_message = f"Database error creating project: {e}"
         logger.error(
             f"Database error creating project via web route: {e}", exc_info=True)
    # Remove httpx.RequestError handler if httpx is removed
    except Exception as e:
        # Catch potential errors from _create_project_in_db other than SQLAlchemyError
        error_message = f"An unexpected error occurred: {e}"
        logger.error(
            f"Unexpected error in create_project_web: {e}", exc_info=True)

    # --- Keep Redirect Logic (ensure str() fix is applied) ---
    if new_project_id is not None:
        # Success -> Redirect to the new project's detail page
        # Make sure the detail route 'ui_view_project' exists
        return RedirectResponse(request.url_for('ui_view_project', project_id=new_project_id), status_code=303)
    else:
        # Failure -> Redirect back to the form page with an error query parameter
        error_param = f"?error={quote_plus(error_message or 'Unknown error')}"
        # Apply the str() fix here for the URL object:
        return RedirectResponse(str(request.url_for('ui_new_project')) + error_param, status_code=303)


@router.get("/projects/{project_id}", response_class=HTMLResponse, name="ui_view_project")
async def view_project_web(project_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific project AND its related items, renders its detail page."""
    logger.info(f"Web UI project detail requested for ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        return HTMLResponse("Server configuration error: Templates not found.", status_code=500)

    project = None
    error_message = None
    try:
        # --- THIS QUERY IS THE KEY CHANGE ---
        # Fetch the specific project and EAGERLY LOAD related documents/entries
        stmt = select(Project).options(
            selectinload(Project.documents),  # Load documents relationship
            # Load memory_entries relationship
             selectinload(Project.memory_entries)
        ).where(Project.id == project_id)
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        # --- END KEY CHANGE ---

        if project is None:
            error_message = f"Project with ID {project_id} not found."
            logger.warning(error_message)
            raise HTTPException(status_code=404, detail=error_message) # Raise 404
        else:
            logger.info(
                f"Found project '{project.name}' with {len(project.documents)} documents and {len(project.memory_entries)} memory entries for detail view.")

    except SQLAlchemyError as e: # Catch DB errors specifically
        logger.error(
            f"Database error fetching project {project_id} for web UI: {e}", exc_info=True)
        error_message = f"Database error fetching project details: {e}"
        raise HTTPException(status_code=500, detail=error_message) # Raise 500
    except Exception as e: # Catch other unexpected errors
        logger.error(
            f"Unexpected error fetching project {project_id} for web UI: {e}", exc_info=True)
        error_message = f"An unexpected server error occurred: {e}"
        raise HTTPException(status_code=500, detail=error_message) # Raise 500

    context_data = {
        "page_title": f"Project: {project.name}" if project else "Project Not Found",
        "project": project,
        # Pass query param error for potential redirect errors (e.g., from delete fail)
        "error": request.query_params.get("error", error_message)
    }
    return templates.TemplateResponse(
        "project_detail.html",
         {"request": request, "data": context_data}
    )


@router.post("/projects/{project_id}/edit", name="ui_update_project")
async def update_project_web(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session),  # Inject DB session
    # Extract form data
    name: str = Form(...),  # Assume name and path are always submitted
    path: str = Form(...),
    description: Optional[str] = Form(None),  # Description can be optional
    is_active: bool = Form(False)  # Handle checkbox boolean
):
    """Handles the submission of the edit project form. Calls DB logic directly."""
    logger.info(f"Web UI update_project form submitted for ID: {project_id}")
    error_message = None
    updated_project = None

    try:
        # Call the database logic helper function directly
        async with db.begin():  # Use transaction
             updated_project = await _update_project_in_db(
                 session=db,
                 project_id=project_id,
                 name=name,
                 path=path,
                 description=description if description else None,  # Pass None if empty string
                 is_active=is_active
             )

        if updated_project is None:
            # The helper function returned None, meaning project wasn't found
            error_message = f"Project with ID {project_id} not found."
            logger.warning(f"Update failed via web route: {error_message}")
        else:
            logger.info(
                 f"Project {project_id} updated successfully via web route.")

    except SQLAlchemyError as e:
         error_message = f"Database error updating project: {e}"
         logger.error(
             f"Database error updating project {project_id} via web route: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(
             f"Unexpected error in update_project_web for ID {project_id}: {e}", exc_info=True)

    # --- Redirect based on outcome ---
    if updated_project is not None and error_message is None:
        # Success -> Redirect to the project's detail page
        return RedirectResponse(request.url_for('ui_view_project', project_id=project_id), status_code=303)
    else:
        # Failure (not found or DB error) -> Redirect back to the EDIT form with error
        if not error_message: error_message = "Unknown error during update."  # Default error
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(str(request.url_for('ui_edit_project', project_id=project_id)) + error_param, status_code=303)


# --- ADD NEW ROUTE: Handle Delete Project Submission (Direct DB Call) ---
@router.post("/projects/{project_id}/delete", name="ui_delete_project")
async def delete_project_web(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session)  # Inject DB session
):
    """Handles the deletion of a project. Calls DB logic directly."""
    logger.info(f"Web UI delete_project form submitted for ID: {project_id}")
    # Consider adding user feedback mechanism later (flash messages)
    deleted = False
    error_message = None

    try:
        # Use a transaction managed by the dependency
        deleted = await _delete_project_in_db(session=db, project_id=project_id)
        if deleted:
            await db.commit() # Commit if helper succeeded
            logger.info(f"Project {project_id} deleted successfully via web route.")
        else:
            # Helper returned False (project not found handled by helper, likely DB error)
            error_message = f"Failed to delete project {project_id}."
            logger.error(f"{error_message} (Helper returned False)")
            await db.rollback() # Rollback on failure

    except Exception as e:
        # Log any unexpected errors during the process (dependency handles rollback)
        error_message = f"Error deleting project {project_id}: {e}"
        logger.error(error_message, exc_info=True)
        # Ensure rollback if not already done
        await db.rollback()


    # Always redirect back to the projects list page
    redirect_url = request.url_for('ui_list_projects')
    if error_message:
        # Optionally add error to query params for display (needs template support)
        # redirect_url += f"?error={quote_plus(error_message)}"
        pass # For now, just redirect without error message

    return RedirectResponse(redirect_url, status_code=303)


# --- ADD NEW ROUTE: Handle Activate Project Submission (Direct DB Call) ---
@router.post("/projects/{project_id}/activate", name="ui_activate_project")
async def activate_project_web(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session)  # Inject DB session
):
    """Handles setting a project as active. Calls DB logic directly."""
    logger.info(f"Web UI activate_project request for ID: {project_id}")
    error_message = None
    activated_project = None

    try:
        # Use transaction managed by dependency
        activated_project = await _set_active_project_in_db(session=db, project_id=project_id)
        if activated_project is None:
            # Project not found by helper
            error_message = f"Project {project_id} not found to activate."
            logger.warning(error_message)
            await db.rollback() # Rollback if project not found
        else:
            await db.commit() # Commit if successful
            logger.info(f"Project {project_id} activated successfully via web route.")

    except Exception as e:
        error_message = f"Error activating project {project_id}: {e}"
        logger.error(error_message, exc_info=True)
        await db.rollback() # Rollback on error

    # Always redirect back to the projects list page
    redirect_url = request.url_for('ui_list_projects')
    if error_message:
        # Optionally add error to query params (needs template support)
        # redirect_url += f"?error={quote_plus(error_message)}"
        pass
    return RedirectResponse(redirect_url, status_code=303)


# --- ADD NEW ROUTE: Display Document Detail Page ---
@router.get("/documents/{doc_id}", response_class=HTMLResponse, name="ui_view_document")
async def view_document_web(
    doc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
):
    """Fetches a specific document and its related items, renders its detail page."""
    logger.info(f"Web UI document detail requested for ID: {doc_id}")
    templates = request.app.state.templates
    if not templates:
        logger.error("Server configuration error: Templates not found.")
        raise HTTPException(
            status_code=500, detail="Server configuration error")

    document = None
    error_message = request.query_params.get("error") # Check for redirect errors first

    try:
        # Fetch the document and eagerly load related tags and versions
        stmt = select(Document).options(
            selectinload(Document.tags),  # Load tags relationship
            selectinload(Document.versions) # Load versions relationship (sorted by ID in model)
        ).where(Document.id == doc_id)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()  # Use scalar_one_or_none

        if document is None:
             error_message = f"Document with ID {doc_id} not found."
             logger.warning(error_message)
             raise HTTPException(status_code=404, detail=error_message)
        else:
            # Versions are sorted by ID descending in the model relationship definition
            # Tags are loaded as a set, order isn't guaranteed but usually not needed
            logger.info(f"Found document '{document.name}' (ID: {doc_id})")

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching document {doc_id}: {e}", exc_info=True)
        # Use the existing error message or set a new one
        error_message = error_message or f"Error fetching document details: {e}"
        raise HTTPException(status_code=500, detail="Database error fetching document details.")
    except Exception as e:
        logger.error(f"Unexpected error fetching document {doc_id}: {e}", exc_info=True)
        # Use the existing error message or set a new one
        error_message = error_message or f"Unexpected server error: {e}"
        raise HTTPException(status_code=500, detail="Unexpected server error.")


    context_data = {
        "page_title": f"Document: {document.name}" if document else "Document Not Found",
        "document": document, # Pass the document object (with tags/versions loaded)
        "error": error_message # Pass error if needed (from redirect or fetch)
    }
    return templates.TemplateResponse(
        "document_detail.html", # New template file
        {"request": request, "data": context_data}
    )


# --- ADD NEW ROUTE: Display New Document Form ---
@router.get("/projects/{project_id}/documents/new", response_class=HTMLResponse, name="ui_new_document")
async def new_document_form(project_id: int, request: Request):
    """Displays the form to create a new document for a specific project."""
    logger.info(f"Web UI new document form requested for project ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        logger.error("Server configuration error: Templates not found.")
        raise HTTPException(status_code=500, detail="Server configuration error")

    context_data = {
        "page_title": "Add New Document",
        # The form will POST to the create handler below
        "form_action": request.url_for('ui_create_document', project_id=project_id),
        "cancel_url": request.url_for('ui_view_project', project_id=project_id), # Link back to project detail
        "project_id": project_id, # Pass project ID for context if needed
        "error": request.query_params.get("error") # Get potential error from redirect
    }
    return templates.TemplateResponse(
        "document_form.html", # New template file
        {"request": request, "data": context_data}
    )


# --- ADD NEW ROUTE: Handle New Document Form Submission (Direct DB Call) ---
@router.post("/projects/{project_id}/documents", name="ui_create_document")
async def create_document_web(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session), # Inject DB session
    # Extract form data
    name: str = Form(...),
    path: str = Form(...),
    type: str = Form(...), # e.g., text/plain, text/markdown
    content: str = Form(...),
    version: str = Form("1.0.0") # Optional version, default to "1.0.0"
):
    """Handles the submission of the new document form. Calls DB logic directly."""
    logger.info(f"Web UI create_document form submitted for project {project_id}: name='{name}'")
    error_message = None
    new_document_id = None
    added_document = None

    try:
        # Call the database logic helper function directly
        # Use transaction managed by dependency
        added_document = await _add_document_in_db(
            session=db,
            project_id=project_id,
            name=name,
            path=path,
            content=content,
            type=type,
            version=version if version else "1.0.0" # Use default if empty
        )

        if added_document is None:
            # Project not found by helper
            error_message = f"Project with ID {project_id} not found."
            logger.warning(f"Add document failed via web route: {error_message}")
            await db.rollback() # Rollback if project not found
        else:
            new_document_id = added_document.id
            await db.commit() # Commit on success
            logger.info(f"Document created directly via web route, ID: {new_document_id}")

    except SQLAlchemyError as e:
         error_message = f"Database error adding document: {e}"
         logger.error(f"Database error adding document for project {project_id} via web route: {e}", exc_info=True)
         await db.rollback()
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Unexpected error in create_document_web for project {project_id}: {e}", exc_info=True)
        await db.rollback()

    # --- Redirect based on outcome ---
    if new_document_id is not None:
        # Success -> Redirect to the new document's detail page
        return RedirectResponse(request.url_for('ui_view_document', doc_id=new_document_id), status_code=303)
    else:
        # Failure (project not found or DB error) -> Redirect back to the NEW DOC form with error
        if not error_message: error_message = "Unknown error adding document."
        error_param = f"?error={quote_plus(error_message)}"
        # Redirect back to the form for THIS project
        return RedirectResponse(str(request.url_for('ui_new_document', project_id=project_id)) + error_param, status_code=303)


# --- ADD NEW ROUTE: Display Edit Document Form ---
@router.get("/documents/{doc_id}/edit", response_class=HTMLResponse, name="ui_edit_document")
async def edit_document_form(
    doc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
):
    """Displays the form pre-filled for editing document metadata."""
    logger.info(f"Web UI edit document form requested for ID: {doc_id}")
    templates = request.app.state.templates
    if not templates:
        logger.error("Server configuration error: Templates not found.")
        raise HTTPException(status_code=500, detail="Server configuration error")

    document = await db.get(Document, doc_id) # Fetch by primary key
    if document is None:
        logger.warning(f"Edit requested for non-existent document ID: {doc_id}")
        raise HTTPException(status_code=404, detail=f"Document with ID {doc_id} not found")

    context_data = {
        "page_title": f"Edit Document: {document.name}",
        # The form will POST to the update handler below
        "form_action": request.url_for('ui_update_document', doc_id=doc_id),
        "cancel_url": request.url_for('ui_view_document', doc_id=doc_id), # Link back to detail view
        "error": request.query_params.get("error"), # Get potential error from redirect
        "document": document, # Pass the fetched document object
        "is_edit_mode": True # Flag for the template
    }
    return templates.TemplateResponse(
        "document_form.html", # Reusing the document form template
         {"request": request, "data": context_data}
    )


# --- ADD NEW ROUTE: Handle Edit Document Form Submission (Direct DB Call) ---
@router.post("/documents/{doc_id}/edit", name="ui_update_document")
async def update_document_web(
    doc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session), # Inject DB session
    # Extract form data for metadata only
    name: str = Form(...),
    path: str = Form(...),
    type: str = Form(...)
    # Removed content and version for this simplified edit
):
    """Handles the submission of the edit document form (metadata only). Calls DB logic directly."""
    logger.info(f"Web UI update_document form submitted for ID: {doc_id}")
    error_message = None
    updated_document = None

    try:
        # Call the database logic helper function directly
        # Use transaction managed by dependency
        updated_document = await _update_document_in_db(
            session=db,
            document_id=doc_id,
            name=name,
            path=path,
            type=type
            # Not passing content/version here
        )

        if updated_document is None:
            # The helper function returned None, meaning document wasn't found
            error_message = f"Document with ID {doc_id} not found."
            logger.warning(f"Update failed via web route: {error_message}")
            await db.rollback() # Rollback if doc not found
        else:
            await db.commit() # Commit on success
            logger.info(f"Document {doc_id} metadata updated successfully via web route.")

    except SQLAlchemyError as e:
         error_message = f"Database error updating document: {e}"
         logger.error(f"Database error updating document {doc_id} via web route: {e}", exc_info=True)
         await db.rollback()
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Unexpected error in update_document_web for ID {doc_id}: {e}", exc_info=True)
        await db.rollback()

    # --- Redirect based on outcome ---
    if updated_document is not None and error_message is None:
         # Success -> Redirect to the document's detail page
        return RedirectResponse(request.url_for('ui_view_document', doc_id=doc_id), status_code=303)
    else:
        # Failure (not found or DB error) -> Redirect back to the EDIT form with error
        if not error_message: error_message = "Unknown error during update."
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(str(request.url_for('ui_edit_document', doc_id=doc_id)) + error_param, status_code=303)


# --- MODIFIED ROUTE: Handle Delete Document Submission ---
@router.post("/documents/{doc_id}/delete", name="ui_delete_document")
async def delete_document_web(
     doc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session) # Inject DB session
):
    """Handles the deletion of a document. Calls DB logic directly."""
    logger.info(f"Web UI delete_document form submitted for ID: {doc_id}")
    project_id_to_redirect = None
    deleted = False # Flag to track success
    error_message = None

    try:
        # First, get the project_id associated with the document for redirection
        doc_to_delete = await db.get(Document, doc_id)
        if doc_to_delete:
            project_id_to_redirect = doc_to_delete.project_id
            logger.debug(f"Document {doc_id} belongs to project {project_id_to_redirect}. Attempting delete.")

            # Call the helper directly using the session from Depends
            deleted = await _delete_document_in_db(session=db, document_id=doc_id)

            if deleted:
                 # Explicitly commit the session if delete helper succeeded
                 await db.commit()
                 logger.info(f"Document {doc_id} committed for deletion via web route.")
            else:
                 # Helper returned False (likely DB error during delete/flush)
                 error_message = f"Failed to delete document {doc_id}."
                 logger.error(f"{error_message} (Helper returned False)")
                 await db.rollback() # Rollback on failure

        else:
            # Document already gone or never existed
            deleted = True # Treat as success for redirection purposes (it's gone)
            logger.warning(f"Document {doc_id} not found for deletion via web route. Assuming success for redirect.")
            # Need to redirect somewhere, maybe project list if we can't determine project
            # This case should ideally be caught by checks before showing delete button
            # For now, redirect to project list if we can't find the project ID
            # This requires modifying the redirect logic below slightly

    except Exception as e:
        # Log any unexpected errors (get_db_session will handle rollback)
        error_message = f"Error deleting document {doc_id}: {e}"
        logger.error(error_message, exc_info=True)
        deleted = False
        await db.rollback() # Ensure rollback

    # --- REDIRECT LOGIC ---
    # Redirect back to the Project Detail page if we know it, otherwise project list
    redirect_url = None
    if project_id_to_redirect:
        redirect_url = request.url_for('ui_view_project', project_id=project_id_to_redirect)
    else:
        redirect_url = request.url_for('ui_list_projects') # Fallback

    if error_message:
        # Optionally add error to query params (needs template support)
        # redirect_url += f"?error={quote_plus(error_message)}"
        pass

    return RedirectResponse(redirect_url, status_code=303)


# --- NEW ROUTE: Handle Add Tag to Document ---
@router.post("/documents/{doc_id}/tags/add", name="ui_add_tag_to_document")
async def add_tag_to_document_web(
    doc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    tag_name: str = Form(...) # Get tag name from form input
):
    """Handles adding a tag to a document via web form."""
    logger.info(f"Web UI add tag '{tag_name}' request for document ID: {doc_id}")
    error_message = None
    success = False

    if not tag_name or tag_name.isspace():
        error_message = "Tag name cannot be empty."
    else:
        try:
            # Use transaction managed by dependency
            success = await _add_tag_to_document_db(session=db, document_id=doc_id, tag_name=tag_name.strip())
            if success:
                await db.commit()
                logger.info(f"Tag '{tag_name}' added/associated with document {doc_id} via web.")
            else:
                # Helper returned false - check if doc exists
                doc = await db.get(Document, doc_id)
                if doc is None:
                    error_message = f"Document {doc_id} not found."
                else:
                    error_message = f"Failed to add tag '{tag_name}'."
                logger.error(f"{error_message} (Helper returned False)")
                await db.rollback() # Rollback on failure

        except Exception as e:
            error_message = f"Error adding tag: {e}"
            logger.error(f"Error adding tag '{tag_name}' to doc {doc_id} via web: {e}", exc_info=True)
            await db.rollback() # Rollback on error

    # Redirect back to the document detail page
    redirect_url = request.url_for('ui_view_document', doc_id=doc_id)
    if error_message:
        # Add error message as query parameter for display in template
        redirect_url += f"?error={quote_plus(error_message)}"
        # Optionally add success flash message here later

    return RedirectResponse(redirect_url, status_code=303)


# --- NEW ROUTE: Handle Remove Tag from Document ---
@router.post("/documents/{doc_id}/tags/remove", name="ui_remove_tag_from_document")
async def remove_tag_from_document_web(
    doc_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    tag_name: str = Form(...) # Get tag name from form (e.g., hidden input)
):
    """Handles removing a tag from a document via web form."""
    logger.info(f"Web UI remove tag '{tag_name}' request for document ID: {doc_id}")
    error_message = None
    success = False

    if not tag_name: # Should not happen if form is set up correctly
        error_message = "Tag name not provided for removal."
    else:
        try:
            # Use transaction managed by dependency
            success = await _remove_tag_from_document_db(session=db, document_id=doc_id, tag_name=tag_name)
            if success:
                await db.commit()
                logger.info(f"Tag '{tag_name}' removed/disassociated from document {doc_id} via web.")
            else:
                # Helper returns True even if tag/doc not found, only False on DB error
                error_message = f"Failed to remove tag '{tag_name}' due to database error."
                logger.error(f"{error_message} (Helper returned False)")
                await db.rollback() # Rollback on failure

        except Exception as e:
            error_message = f"Error removing tag: {e}"
            logger.error(f"Error removing tag '{tag_name}' from doc {doc_id} via web: {e}", exc_info=True)
            await db.rollback() # Rollback on error

    # Redirect back to the document detail page
    redirect_url = request.url_for('ui_view_document', doc_id=doc_id)
    if error_message:
        # Add error message as query parameter
        redirect_url += f"?error={quote_plus(error_message)}"
        # Optionally add success flash message here later

    return RedirectResponse(redirect_url, status_code=303)
