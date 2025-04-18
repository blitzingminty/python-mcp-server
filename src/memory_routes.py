import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus
from .database import get_db_session
from .models import MemoryEntry
from .mcp_db_helpers_memory import (
    get_memory_entry_db,
    add_memory_entry_db,
    update_memory_entry_db,
    delete_memory_entry_db,
    add_tag_to_memory_entry_db,
    remove_tag_from_memory_entry_db
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/memory", response_class=HTMLResponse, name="ui_list_memory_entries_all")
async def list_all_memory_entries_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches ALL memory entries across projects and renders the list page."""
    logger.info("Web UI list all memory entries requested")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    memory_entries = []
    error_message = request.query_params.get("error")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.project)).order_by(MemoryEntry.updated_at.desc())
        result = await db.execute(stmt)
        memory_entries = result.scalars().all()
        logger.info(f"Found {len(memory_entries)} total memory entries.")
    except SQLAlchemyError as e:
        error_message = error_message or f"Database error fetching entries: {e}"
        logger.error(f"Database error fetching all memory entries: {e}", exc_info=True)
    except Exception as e:
        error_message = error_message or f"Unexpected server error: {e}"
        logger.error(f"Unexpected error fetching all memory entries: {e}", exc_info=True)
    context_data: Dict[str, Any] = {"page_title": "All Memory Entries", "memory_entries": memory_entries, "error": error_message}
    return templates.TemplateResponse("memory_entries_list.html", {"request": request, "data": context_data})

@router.get("/memory/{entry_id}", response_class=HTMLResponse, name="ui_view_memory_entry")
async def view_memory_entry_web(entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific memory entry, its relationships, and available linkable items."""
    logger.info(f"Web UI memory entry detail requested for ID: {entry_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")

    error_message = request.query_params.get("error")
    entry = None
    available_documents = []
    available_memory_entries = []

    try:
        entry = await get_memory_entry_db(session=db, entry_id=entry_id)
        if entry is None:
            error_message = f"Memory Entry with ID {entry_id} not found."
            raise HTTPException(status_code=404, detail=error_message)
        logger.info(f"Found memory entry '{entry.title}' (ID: {entry_id})")

        if entry.project_id:
            mem_stmt = select(MemoryEntry).where(
                MemoryEntry.project_id == entry.project_id,
                MemoryEntry.id != entry_id
            ).order_by(MemoryEntry.title)

            mem_results = await db.execute(mem_stmt)
            available_memory_entries = mem_results.scalars().all()

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching memory entry {entry_id} or related data: {e}", exc_info=True)
        error_message = error_message or f"Database error fetching data: {e}"
        raise HTTPException(status_code=500, detail=error_message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching memory entry {entry_id}: {e}", exc_info=True)
        error_message = error_message or f"Unexpected server error: {e}"
        raise HTTPException(status_code=500, detail=error_message)

    tags = sorted([tag.name for tag in entry.tags]) if entry.tags else []
    linked_docs = [{"id": doc.id, "name": doc.name} for doc in entry.documents] if entry.documents else []
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
        "available_memory_entries": available_memory_entries,
        "error": error_message
    }
    return templates.TemplateResponse("memory_detail.html", {"request": request, "data": context_data})

@router.get("/projects/{project_id}/memory/new", response_class=HTMLResponse, name="ui_new_memory_entry")
async def new_memory_entry_form(project_id: int, request: Request):
    """Displays the form to create a new memory entry."""
    logger.info(f"Web UI new memory entry form requested for project ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    context_data = {
        "page_title": "Add New Memory Entry",
        "form_action": request.url_for('ui_create_memory_entry', project_id=project_id),
        "cancel_url": request.url_for('ui_view_project', project_id=project_id),
        "project_id": project_id,
        "error": request.query_params.get("error")
    }
    return templates.TemplateResponse("memory_form.html", {"request": request, "data": context_data})

@router.post("/projects/{project_id}/memory", name="ui_create_memory_entry")
async def create_memory_entry_web(
    project_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    title: str = Form(...), type: str = Form(...), content: str = Form(...)
):
    """Handles submission of the new memory entry form."""
    logger.info(f"Web UI create memory entry submitted for project {project_id}: title='{title}'")
    error_message = None
    new_entry = None
    new_entry_id = None
    redirect_url_on_error = str(request.url_for('ui_new_memory_entry', project_id=project_id))

    project = await db.get(MemoryEntry, project_id)
    if project is None:
        error_message = f"Project with ID {project_id} not found."
        logger.warning(error_message)
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(redirect_url_on_error + error_param, status_code=303)

    try:
        async with db.begin():
            new_entry = await add_memory_entry_db(session=db, project_id=project_id, title=title, type=type, content=content)
            if new_entry is None:
                error_message = "Database error adding memory entry (helper returned None)."
                logger.error(f"Add memory entry failed: {error_message}")
                raise ValueError(error_message)
        new_entry_id = new_entry.id
        logger.info(f"Memory entry created via web route, ID: {new_entry_id}")
    except (SQLAlchemyError, ValueError) as e:
        error_message = error_message or f"Error adding memory entry: {e}"
        logger.error(f"Error in create_memory_entry_web for project {project_id}: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error in create_memory_entry_web for project {project_id}: {e}", exc_info=True)

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
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    entry = await db.get(MemoryEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Memory Entry with ID {entry_id} not found")
    context_data = {
        "page_title": f"Edit Memory Entry: {entry.title}",
        "form_action": request.url_for('ui_update_memory_entry', entry_id=entry_id),
        "cancel_url": request.url_for('ui_view_memory_entry', entry_id=entry_id),
        "error": request.query_params.get("error"),
        "entry": entry,
        "is_edit_mode": True
    }
    return templates.TemplateResponse("memory_form.html", {"request": request, "data": context_data})

@router.post("/memory/{entry_id}/edit", name="ui_update_memory_entry")
async def update_memory_entry_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    title: str = Form(...), type: str = Form(...), content: str = Form(...)
):
    """Handles submission of the edit memory entry form."""
    logger.info(f"Web UI update memory entry submitted for ID: {entry_id}")
    error_message = None
    updated_entry = None
    try:
        async with db.begin():
            updated_entry = await update_memory_entry_db(session=db, entry_id=entry_id, title=title, type=type, content=content)
            if updated_entry is None:
                error_message = f"Memory Entry with ID {entry_id} not found."
                logger.warning(f"Update failed: {error_message}")
                raise ValueError(error_message)
        logger.info(f"Memory entry {entry_id} updated successfully via web route.")
    except (SQLAlchemyError, ValueError) as e:
        error_message = error_message or f"Database error updating memory entry: {e}"
        logger.error(f"Error updating memory entry {entry_id} via web: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error updating memory entry {entry_id} via web: {e}", exc_info=True)
    if updated_entry is not None and error_message is None:
        return RedirectResponse(request.url_for('ui_view_memory_entry', entry_id=entry_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error during update.')}"
        return RedirectResponse(str(request.url_for('ui_edit_memory_entry', entry_id=entry_id)) + error_param, status_code=303)

@router.post("/memory/{entry_id}/delete", name="ui_delete_memory_entry")
async def delete_memory_entry_web(entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles deletion of a memory entry."""
    logger.info(f"Web UI delete memory entry request for ID: {entry_id}")
    error_message = None
    project_id_to_redirect = None
    try:
        async with db.begin():
            deleted, project_id = await delete_memory_entry_db(session=db, entry_id=entry_id)
            project_id_to_redirect = project_id
            if not deleted:
                error_message = f"Memory Entry {entry_id} not found." if project_id is None else f"Database error deleting memory entry {entry_id}."
                logger.error(f"Deletion failed: {error_message}")
                raise SQLAlchemyError(error_message)
        logger.info(f"Memory entry {entry_id} deleted successfully via web route.")
    except SQLAlchemyError as e:
        error_message = error_message or f"Database error during deletion: {e}"
        logger.error(error_message, exc_info=True)
    except Exception as e:
        error_message = f"Error deleting memory entry {entry_id}: {e}"
        logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_view_project', project_id=project_id_to_redirect) if project_id_to_redirect else request.url_for('ui_list_projects')
    if error_message:
        logger.warning(f"Redirecting after delete failure for memory entry {entry_id}: {error_message}")
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/memory/{entry_id}/tags/add", name="ui_add_tag_to_memory_entry")
async def add_tag_to_memory_entry_web(
    entry_id: int, request: Request, db: AsyncSession = Depends(get_db_session), tag_name: str = Form(...)
):
    """Handles adding a tag to a memory entry."""
    logger.info(f"Web UI add tag '{tag_name}' request for memory entry ID: {entry_id}")
    error_message = None
    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)

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
                    error_message = f"Failed to add tag '{tag_name}' (DB error)."
                    logger.error(f"{error_message} (add_tag_to_memory_entry_db returned False)")
                    raise ValueError(error_message)
            logger.info(f"Tag '{tag_name}' added/associated with memory entry {entry_id} via web.")
        except (SQLAlchemyError, ValueError) as e:
            error_message = error_message or f"Error adding tag: {e}"
            logger.error(f"Error adding tag '{tag_name}' to memory {entry_id} via web: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error adding tag '{tag_name}' to memory {entry_id} via web: {e}", exc_info=True)

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
    if not tag_name:
        error_message = "Tag name not provided for removal."
    else:
        try:
            async with db.begin():
                success = await remove_tag_from_memory_entry_db(session=db, entry_id=entry_id, tag_name=tag_name)
                if not success:
                    error_message = f"Failed to remove tag '{tag_name}' due to database error."
                    raise SQLAlchemyError(error_message)
            logger.info(f"Tag '{tag_name}' removed/disassociated from memory entry {entry_id} via web.")
        except SQLAlchemyError as e:
            error_message = error_message or f"Database error removing tag: {e}"
            logger.error(f"Error removing tag '{tag_name}' from memory {entry_id} via web: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error removing tag '{tag_name}' from memory {entry_id} via web: {e}", exc_info=True)
    redirect_url = request.url_for('ui_view_memory_entry', entry_id=entry_id)
    if error_message:
        redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)
