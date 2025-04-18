import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from typing import Dict, Any
from .database import get_db_session
from .models import Document, Project, MemoryEntry

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_class=HTMLResponse, name="ui_root")
async def ui_root(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Serves the main dashboard/index page of the UI with entity counts."""
    logger.info("Web UI root requested")

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

        logger.info(f"Dashboard counts: Projects={project_count} Docs={document_count} Memory={memory_entry_count}")

    except Exception as e:
        logger.error(f"Failed to fetch counts for dashboard: {e}", exc_info=True)
        error_message = "Could not load counts."
        project_count = 'N/A'
        document_count = 'N/A'
        memory_entry_count = 'N/A'

    context_data: Dict[str, Any] = {
        "page_title": "MCP Server Dashboard",
        "welcome_message": "Welcome to the MCP Server Maintenance UI!",
        "project_count": project_count,
        "document_count": document_count,
        "memory_entry_count": memory_entry_count,
        "error_message": error_message,
        "request": request,
    }

    return templates.TemplateResponse("index.html", {"request": request, "data": context_data})
