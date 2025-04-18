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
from .models import Document
from .mcp_db_helpers_document import (
    add_document_in_db,
    update_document_in_db,
    delete_document_in_db,
    add_tag_to_document_db,
    remove_tag_from_document_db,
    add_document_version_db,
    get_document_version_content_db
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/documents", response_class=HTMLResponse, name="ui_list_documents_all")
async def list_all_documents_web(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches ALL documents across projects and renders the documents list page."""
    logger.info("Web UI list all documents requested")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    documents = []
    error_message = request.query_params.get("error")
    try:
        stmt = select(Document).options(selectinload(Document.project)).order_by(Document.project_id, Document.name)
        result = await db.execute(stmt)
        documents = result.scalars().all()
        logger.info(f"Found {len(documents)} total documents.")
    except SQLAlchemyError as e:
        error_message = error_message or f"Database error fetching documents: {e}"
        logger.error(f"Database error fetching all documents: {e}", exc_info=True)
    except Exception as e:
        error_message = error_message or f"Unexpected server error: {e}"
        logger.error(f"Unexpected error fetching all documents: {e}", exc_info=True)
    context_data: Dict[str, Any] = {"page_title": "All Documents", "documents": documents, "error": error_message}
    return templates.TemplateResponse("documents_list.html", {"request": request, "data": context_data})

@router.get("/documents/{doc_id}", response_class=HTMLResponse, name="ui_view_document")
async def view_document_web(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific document and its related items, renders its detail page."""
    logger.info(f"Web UI document detail requested for ID: {doc_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    document = None
    error_message = request.query_params.get("error")
    try:
        stmt = select(Document).options(selectinload(Document.tags), selectinload(Document.versions)).where(Document.id == doc_id)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            error_message = f"Document with ID {doc_id} not found."
            logger.warning(error_message)
            raise HTTPException(status_code=404, detail=error_message)
        else:
            logger.info(f"Found document '{document.name}' (ID: {doc_id})")
    except SQLAlchemyError as e:
        error_message = error_message or f"Error fetching document details: {e}"
        logger.error(f"Database error fetching document {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error fetching document details.")
    except HTTPException:
        raise
    except Exception as e:
        error_message = error_message or f"Unexpected server error: {e}"
        logger.error(f"Unexpected error fetching document {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected server error.")
    context_data: Dict[str, Any] = {"page_title": f"Document: {document.name}" if document else "Document Not Found", "document": document, "error": error_message}
    return templates.TemplateResponse("document_detail.html", {"request": request, "data": context_data})

@router.get("/projects/{project_id}/documents/new", response_class=HTMLResponse, name="ui_new_document")
async def new_document_form(project_id: int, request: Request):
    """Displays the form to create a new document for a specific project."""
    logger.info(f"Web UI new document form requested for project ID: {project_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    context_data = {
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
    error_message = None
    new_document_id = None
    added_document = None
    redirect_url_on_error = str(request.url_for('ui_new_document', project_id=project_id))

    project = await db.get(Document, project_id)
    if project is None:
        error_message = f"Project with ID {project_id} not found."
        logger.warning(error_message)
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(redirect_url_on_error + error_param, status_code=303)

    try:
        async with db.begin():
            added_document = await add_document_in_db(session=db, project_id=project_id, name=name, path=path, content=content, type=type, version=version if version else "1.0.0")
            if added_document is None:
                error_message = "Database error adding document (helper returned None)."
                logger.error(f"Add document failed: {error_message}")
                raise ValueError(error_message)
        new_document_id = added_document.id
        logger.info(f"Document created directly via web route, ID: {new_document_id}")
    except (SQLAlchemyError, ValueError) as e:
        error_message = error_message or f"Error adding document: {e}"
        logger.error(f"Error in create_document_web for project {project_id}: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error in create_document_web for project {project_id}: {e}", exc_info=True)

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
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    document = await db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document with ID {doc_id} not found")
    context_data = {
        "page_title": f"Edit Document: {document.name}",
        "form_action": request.url_for('ui_update_document', doc_id=doc_id),
        "cancel_url": request.url_for('ui_view_document', doc_id=doc_id),
        "error": request.query_params.get("error"),
        "document": document,
        "is_edit_mode": True
    }
    return templates.TemplateResponse("document_form.html", {"request": request, "data": context_data})

@router.post("/documents/{doc_id}/edit", name="ui_update_document")
async def update_document_web(
    doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session),
    name: str = Form(...), path: str = Form(...), type: str = Form(...)
):
    """Handles the submission of the edit document form (metadata only)."""
    logger.info(f"Web UI update_document form submitted for ID: {doc_id}")
    error_message = None
    updated_document = None
    try:
        async with db.begin():
            updated_document = await update_document_in_db(session=db, document_id=doc_id, name=name, path=path, type=type)
            if updated_document is None:
                error_message = f"Document with ID {doc_id} not found."
                logger.warning(f"Update failed: {error_message}")
                raise ValueError(error_message)
        logger.info(f"Document {doc_id} metadata updated successfully via web route.")
    except (SQLAlchemyError, ValueError) as e:
        error_message = error_message or f"Database error updating document: {e}"
        logger.error(f"Error updating document {doc_id} via web: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Error updating document {doc_id} via web: {e}", exc_info=True)
    if updated_document is not None and error_message is None:
        return RedirectResponse(request.url_for('ui_view_document', doc_id=doc_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error during update.')}"
        return RedirectResponse(str(request.url_for('ui_edit_document', doc_id=doc_id)) + error_param, status_code=303)

@router.post("/documents/{doc_id}/delete", name="ui_delete_document")
async def delete_document_web(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Handles the deletion of a document."""
    logger.info(f"Web UI delete_document form submitted for ID: {doc_id}")
    project_id_to_redirect = None
    error_message = None
    try:
        doc_to_delete = await db.get(Document, doc_id)
        if doc_to_delete:
            project_id_to_redirect = doc_to_delete.project_id
            logger.debug(f"Document {doc_id} belongs to project {project_id_to_redirect}. Attempting delete.")
            async with db.begin():
                deleted = await delete_document_in_db(session=db, document_id=doc_id)
                if not deleted:
                    error_message = f"Failed to delete document {doc_id} (DB error)."
                    logger.error(f"{error_message} (Helper returned False)")
                    raise SQLAlchemyError(error_message)
            logger.info(f"Document {doc_id} committed for deletion via web route.")
        else:
            logger.warning(f"Document {doc_id} not found for deletion. Assuming success for redirect.")
    except SQLAlchemyError as e:
        error_message = error_message or f"Database error deleting document {doc_id}: {e}"
        logger.error(error_message, exc_info=True)
    except Exception as e:
        error_message = f"Error deleting document {doc_id}: {e}"
        logger.error(error_message, exc_info=True)
    redirect_url = request.url_for('ui_view_project', project_id=project_id_to_redirect) if project_id_to_redirect else request.url_for('ui_list_projects')
    if error_message:
        logger.warning(f"Redirecting after delete failure for doc {doc_id}: {error_message}")
    return RedirectResponse(redirect_url, status_code=303)

@router.post("/documents/{doc_id}/tags/add", name="ui_add_tag_to_document")
async def add_tag_to_document_web(
    doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session), tag_name: str = Form(...)
):
    """Handles adding a tag to a document via web form."""
    logger.info(f"Web UI add tag '{tag_name}' request for document ID: {doc_id}")
    error_message = None
    redirect_url = request.url_for('ui_view_document', doc_id=doc_id)

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
                    error_message = f"Failed to add tag '{tag_name}' (DB error)."
                    logger.error(f"{error_message} (add_tag_to_document_db returned False)")
                    raise ValueError(error_message)
            logger.info(f"Tag '{tag_name}' added/associated with document {doc_id} via web.")
        except (SQLAlchemyError, ValueError) as e:
            error_message = error_message or f"Error adding tag: {e}"
            logger.error(f"Error adding tag '{tag_name}' to doc {doc_id} via web: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error adding tag '{tag_name}' to doc {doc_id} via web: {e}", exc_info=True)

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
    if not tag_name:
        error_message = "Tag name not provided for removal."
    else:
        try:
            async with db.begin():
                success = await remove_tag_from_document_db(session=db, document_id=doc_id, tag_name=tag_name)
                if not success:
                    error_message = f"Failed to remove tag '{tag_name}' due to database error."
                    raise SQLAlchemyError(error_message)
            logger.info(f"Tag '{tag_name}' removed/disassociated from document {doc_id} via web.")
        except SQLAlchemyError as e:
            error_message = error_message or f"Database error removing tag: {e}"
            logger.error(f"Error removing tag '{tag_name}' from doc {doc_id} via web: {e}", exc_info=True)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"Error removing tag '{tag_name}' from doc {doc_id} via web: {e}", exc_info=True)
    redirect_url = request.url_for('ui_view_document', doc_id=doc_id)
    if error_message:
        redirect_url = str(redirect_url) + f"?error={quote_plus(error_message)}"
    return RedirectResponse(redirect_url, status_code=303)

@router.get("/versions/{version_id}", response_class=HTMLResponse, name="ui_view_version")
async def view_document_version_web(version_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Fetches a specific document version and renders its detail page."""
    logger.info(f"Web UI document version detail requested for Version ID: {version_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    version = None
    error_message = None
    try:
        version = await get_document_version_content_db(session=db, version_id=version_id)
        if version is None:
            error_message = f"Document Version with ID {version_id} not found."
            logger.warning(error_message)
            raise HTTPException(status_code=404, detail=error_message)
        else:
            logger.info(f"Found document version '{version.version}' (ID: {version_id}) for doc ID {version.document_id}")
    except SQLAlchemyError as e:
        error_message = f"Error fetching document version details: {e}"
        logger.error(f"Database error fetching document version {version_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error fetching version details.")
    except HTTPException:
        raise
    except Exception as e:
        error_message = f"Unexpected server error: {e}"
        logger.error(f"Unexpected error fetching document version {version_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected server error.")
    context_data = {"page_title": f"Version {version.version} of Document {version.document.name}" if version and version.document else "Version Not Found", "version": version, "error": error_message}
    return templates.TemplateResponse("version_detail.html", {"request": request, "data": context_data})

@router.get("/documents/{doc_id}/new_version", response_class=HTMLResponse, name="ui_new_version_form")
async def new_document_version_form(doc_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    """Displays the form to create a new version of a document."""
    logger.info(f"Web UI new version form requested for document ID: {doc_id}")
    templates = request.app.state.templates
    if not templates:
        raise HTTPException(status_code=500, detail="Server configuration error")
    document = await db.get(Document, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document with ID {doc_id} not found")
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
    error_message = None
    updated_doc = None
    new_version = None
    if not version_string or version_string.isspace():
        error_message = "Version string cannot be empty."
    if error_message:
        error_param = f"?error={quote_plus(error_message)}"
        return RedirectResponse(str(request.url_for('ui_new_version_form', doc_id=doc_id)) + error_param, status_code=303)
    try:
        async with db.begin():
            updated_doc, new_version = await add_document_version_db(session=db, document_id=doc_id, content=content, version_string=version_string.strip())
            if updated_doc is None or new_version is None:
                error_message = f"Failed to add version '{version_string}'. Document {doc_id} not found or DB error occurred."
                logger.error(f"Create version failed: {error_message}")
                raise ValueError(error_message)
        logger.info(f"Version '{new_version.version}' (ID: {new_version.id}) created for document {doc_id} via web.")
    except ValueError as ve:
        error_message = str(ve)
        logger.warning(f"Validation error creating version for doc {doc_id}: {error_message}", exc_info=False)
    except SQLAlchemyError as e:
        error_message = f"Database error creating version: {e}"
        logger.error(f"Database error creating version for doc {doc_id}: {e}", exc_info=True)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        logger.error(f"Unexpected error creating version for doc {doc_id}: {e}", exc_info=True)
    if updated_doc is not None and new_version is not None and error_message is None:
        return RedirectResponse(request.url_for('ui_view_document', doc_id=doc_id), status_code=303)
    else:
        error_param = f"?error={quote_plus(error_message or 'Unknown error creating version.')}"
        return RedirectResponse(str(request.url_for('ui_new_version_form', doc_id=doc_id)) + error_param, status_code=303)
