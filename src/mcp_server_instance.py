# src/mcp_server_instance.py
# Defines the FastMCP server instance and its handlers.

import logging, time
from typing import Any, Dict, Optional, List, AsyncIterator
from contextlib import asynccontextmanager
import datetime

# --- FastAPI Import (needed for lifespan signature) ---
from fastapi import FastAPI

# --- SQLAlchemy Imports ---
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker # Use the newer session maker
)
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy import event # Import event
from sqlalchemy.engine import Engine # Import Engine

# --- Database Imports ---
# Import Base and the PRAGMA function directly
# Remove engine, AsyncSessionFactory, get_db_session imports from here
from .database import Base, _set_sqlite_pragma, logger as db_logger

# Import your models - **IMPORTANT**: Ensure models are loaded before create_all
# You might need to explicitly import them if they aren't loaded elsewhere
from .models import Project, Document, DocumentVersion, MemoryEntry, Tag, MemoryEntryRelation

# --- SDK Imports ---
try:
    from mcp.server.fastmcp import FastMCP, Context
    # from mcp import types as mcp_types
except ImportError as e:
    logging.critical(
        f"Failed to import from mcp.server.fastmcp: {e}. Please ensure 'mcp[cli]' is installed correctly.")
    raise

# --- Project Imports ---
from .config import settings

logger = logging.getLogger(__name__)


# --- Lifespan Management for Database ---
@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[Dict[str, Any]]: # Accepts FastAPI app instance
    """
    Manage application lifecycle: create engine, session factory, ensure tables exist,
    and clean up resources. Stores session factory in app.state.
    """
    logger.info("Application lifespan startup (explicitly attached)...")
    db_logger.info(f"Lifespan: DATABASE_URL from settings: {settings.DATABASE_URL}")

    # --- Create Engine ---
    logger.info("Lifespan: Creating SQLAlchemy engine...")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.LOG_LEVEL == "DEBUG",
        future=True,
        pool_pre_ping=True
    )

    # --- Attach PRAGMA listener to the specific engine instance ---
    if engine.dialect.name == "sqlite":
         event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
         logger.info("Lifespan: Attached PRAGMA listener for SQLite engine.")

    # --- Create Session Factory ---
    logger.info("Lifespan: Creating SQLAlchemy async session factory...")
    AsyncSessionFactory_local = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    # Store factory in app state for dependency injection
    app.state.db_session_factory = AsyncSessionFactory_local
    logger.info("Lifespan: DB Session Factory attached to app state.")

    # --- Ensure tables are created ---
    try:
        async with engine.begin() as conn:
            logger.info("Lifespan: Initializing database tables (if they don't exist)...")
            # ** Ensure all models inheriting from Base are imported before this line **
            # e.g., from . import models # Ensure Project, Document etc. are known to Base.metadata
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Lifespan: Database tables initialization check complete.")
            if settings.DATABASE_URL.startswith("sqlite"):
                # Log the expected file path for verification
                db_file_path = settings.DATABASE_URL.split(":///")[-1]
                if db_file_path == ':memory:':
                     logger.info("Lifespan: Using in-memory SQLite database.")
                else:
                     if settings.DATABASE_URL.startswith("sqlite+aiosqlite:////"):
                         db_file_path = "/" + settings.DATABASE_URL.split("////")[-1]
                     logger.info(f"Lifespan: Database file should be at {db_file_path}")

    except Exception as e:
        logger.critical(f"Lifespan: Database table initialization failed: {e}", exc_info=True)
        await engine.dispose() # Clean up engine if init fails
        raise # Re-raise to prevent app startup with bad DB state

    # --- Yield control to the application ---
    context_data = {} # Can yield other startup context if needed
    try:
        yield context_data
    finally:
        # --- Clean up resources ---
        logger.info("Application lifespan shutdown: Disposing SQLAlchemy engine...")
        await engine.dispose()
        logger.info("Application lifespan shutdown: Engine disposed.")

        

# --- Create the FastMCP Instance ---
# REMOVED lifespan argument from constructor
mcp_instance = FastMCP(
    name=settings.MCP_SERVER_NAME,
    version=settings.VERSION,
    # lifespan=app_lifespan # <<< REMOVED
)
logger.info(
    f"FastMCP instance created (without lifespan arg): {mcp_instance.name} v{mcp_instance.version}")


# --- Helper to get session from context ---
# This helper might not be needed if tools use the standard FastAPI dependency system
# Keeping it for now if MCP tools rely on the MCP Context object directly
async def get_session_from_mcp_context(ctx: Context) -> AsyncSession:
    """Gets an async session from the lifespan context via MCP Context."""
    # This assumes FastMCP somehow provides access back to the FastAPI app's state
    # This might need adjustment based on how FastMCP integrates Context and FastAPI state
    # A safer approach is often to have tools use FastAPI dependencies directly if possible.
    try:
        # Attempt to access the underlying app state - THIS IS SPECULATIVE
        # You might need to adapt this based on FastMCP's Context object structure
        app_state = getattr(ctx, '_app_state', None) or getattr(getattr(ctx, 'request_context', None), 'app_state', None)
        if not app_state:
            raise AttributeError("Could not access app state from MCP Context")

        session_factory = getattr(app_state, 'db_session_factory', None)
        if not session_factory:
             raise KeyError("Database session factory not found in app state via MCP context.")

        return session_factory() # Return a new session instance
    except (KeyError, AttributeError) as e:
        logger.error(f"Error accessing DB session factory via MCP context: {e}", exc_info=True)
        raise RuntimeError("Server configuration error: DB Session Factory missing or inaccessible via MCP Context.")
    except Exception as e:
        logger.error(f"Unexpected error getting session from MCP context: {e}", exc_info=True)
        raise RuntimeError("Server configuration error: Unexpected context issue.")


# --- DB Helper Functions ---
# (Keep _get_or_create_tag, _create_project_in_db, _update_project_in_db, etc. as they are)
# ... all existing DB helper functions (_get_or_create_tag, _create_project_in_db, ... _unlink_memory_entries) ...
async def _get_or_create_tag(session: AsyncSession, tag_name: str) -> Tag:
    """Helper function to get a Tag or create it if it doesn't exist."""
    stmt = select(Tag).where(Tag.name == tag_name)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if tag is None:
        logger.info(f"Tag '{tag_name}' not found, creating...")
        tag = Tag(name=tag_name)
        session.add(tag)
        try:
            await session.flush()
            await session.refresh(tag)
            logger.info(f"Tag '{tag_name}' created or retrieved.")
        except IntegrityError:
            logger.warning(f"Tag '{tag_name}' likely created concurrently, retrieving existing.")
            await session.rollback() # Rollback the failed add
            stmt = select(Tag).where(Tag.name == tag_name)
            result = await session.execute(stmt)
            tag = result.scalar_one() # Should exist now
        except SQLAlchemyError as e:
            logger.error(f"Database error getting/creating tag '{tag_name}': {e}", exc_info=True)
            raise
    return tag

async def _create_project_in_db(
    session: AsyncSession, name: str, path: str, description: Optional[str], is_active: bool
) -> Project:
    """Core logic to create a project in the database."""
    logger.debug(f"Helper: Creating project '{name}' in DB.")
    new_project = Project(name=name, path=path, description=description, is_active=is_active)
    session.add(new_project)
    await session.flush()
    await session.refresh(new_project)
    logger.debug(f"Helper: Project created with ID {new_project.id}")
    return new_project

async def _update_project_in_db(
    session: AsyncSession, project_id: int, name: Optional[str] = None,
    description: Optional[str] = None, path: Optional[str] = None, is_active: Optional[bool] = None
) -> Project | None:
    """Core logic to update a project in the database."""
    logger.debug(f"Helper: Updating project ID {project_id} in DB.")
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for update.")
        return None
    update_data = {"name": name, "description": description, "path": path, "is_active": is_active}
    updated = False
    for key, value in update_data.items():
        if value is not None and getattr(project, key) != value:
            setattr(project, key, value)
            updated = True
    if updated:
        logger.debug(f"Helper: Applying updates to project {project_id}.")
        # Ensure timestamp updates if your model relies on default= or onupdate=
        project.updated_at = datetime.datetime.utcnow() # Manually set if not automatic
        await session.flush()
        await session.refresh(project)
    else:
        logger.debug(f"Helper: No changes detected for project {project_id}.")
    return project

# ... (rest of the helper functions remain unchanged) ...
async def _delete_project_in_db(session: AsyncSession, project_id: int) -> bool:
    """Core logic to delete a project from the database."""
    logger.debug(f"Helper: Deleting project ID {project_id} from DB.")
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for deletion.")
        return True # Consider it success if it doesn't exist
    try:
        await session.delete(project)
        await session.flush()
        logger.info(f"Helper: Project ID {project_id} deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting project {project_id}: {e}", exc_info=True)
        return False # Indicate failure

async def _set_active_project_in_db(session: AsyncSession, project_id: int) -> Project | None:
    """Core logic to set a project as active, deactivating others."""
    logger.debug(f"Helper: Setting project ID {project_id} as active in DB.")
    project_to_activate = await session.get(Project, project_id)
    if project_to_activate is None:
        logger.warning(f"Helper: Project ID {project_id} not found to activate.")
        return None
    # Deactivate others in a separate query for clarity/efficiency
    stmt_deactivate = (
        update(Project)
        .where(Project.is_active == True, Project.id != project_id)
        .values(is_active=False)
    )
    await session.execute(stmt_deactivate)

    updated = False
    if not project_to_activate.is_active:
        logger.debug(f"Helper: Activating project ID: {project_id}")
        project_to_activate.is_active = True
        project_to_activate.updated_at = datetime.datetime.utcnow() # Manually set if needed
        updated = True
    else:
         logger.debug(f"Helper: Project ID: {project_id} was already active.")

    if updated:
        await session.flush() # Flush changes to the single project if it was updated
        await session.refresh(project_to_activate)
    else:
        logger.debug(f"Helper: No change in active state for project {project_id}.")
    return project_to_activate


async def _add_document_in_db(
    session: AsyncSession, project_id: int, name: str, path: str, content: str,
    type: str, version: str = "1.0.0"
) -> Document | None:
    """Core logic to add a document and its initial version."""
    logger.debug(f"Helper: Adding document '{name}' to project {project_id}.")
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project {project_id} not found for adding document.")
        return None
    new_document = Document(project_id=project_id, name=name, path=path, content=content, type=type, version=version)
    session.add(new_document)
    await session.flush() # Get the new document ID
    new_version_entry = DocumentVersion(document_id=new_document.id, content=content, version=version)
    session.add(new_version_entry)
    # Flush again or rely on commit/outer flush
    await session.flush()
    await session.refresh(new_document)
    await session.refresh(new_version_entry)
    logger.info(f"Helper: Document '{name}' (ID: {new_document.id}) added to project {project_id}.")
    return new_document

async def _update_document_in_db(
    session: AsyncSession, document_id: int, name: Optional[str] = None,
    path: Optional[str] = None, type: Optional[str] = None
) -> Document | None:
    """Core logic to update a document's metadata."""
    logger.debug(f"Helper: Updating metadata for document ID {document_id} in DB.")
    document = await session.get(Document, document_id)
    if document is None:
        logger.warning(f"Helper: Document ID {document_id} not found for update.")
        return None
    update_data = {"name": name, "path": path, "type": type}
    updated = False
    for key, value in update_data.items():
        if value is not None and getattr(document, key) != value:
            setattr(document, key, value)
            updated = True
    if updated:
        logger.debug(f"Helper: Applying metadata updates to document {document_id}.")
        document.updated_at = datetime.datetime.utcnow() # Manually set if needed
        await session.flush()
        await session.refresh(document)
    else:
        logger.debug(f"Helper: No metadata changes detected for document {document_id}.")
    return document

async def _delete_document_in_db(session: AsyncSession, document_id: int) -> bool:
    """Core logic to delete a document."""
    logger.debug(f"Helper: Deleting document ID {document_id} from DB.")
    # Ensure related data like versions and tags are handled (cascade should work if set up)
    doc = await session.get(Document, document_id) # options for selectinload might not be needed if cascade delete works
    if doc is None:
        logger.warning(f"Helper: Document ID {document_id} not found for deletion.")
        return True # Success if not found
    try:
        doc_name = doc.name # Get name before deletion for logging
        await session.delete(doc)
        await session.flush()
        logger.info(f"Helper: Document ID {document_id} ('{doc_name}') deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting document {document_id}: {e}", exc_info=True)
        return False

async def _add_document_version_db(
    session: AsyncSession, document_id: int, content: str, version_string: str
) -> tuple[Document | None, DocumentVersion | None]:
    """
    Core logic to add a new version to a document.
    Creates a new DocumentVersion record and updates the parent Document's
    content and version fields.
    Returns (updated_document, new_version_record) on success, or (None, None) on failure.
    """
    logger.debug(f"Helper: Adding new version '{version_string}' to document ID {document_id}.")
    try:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for adding version.")
            return None, None

        existing_version_stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version == version_string
        )
        existing_version_result = await session.execute(existing_version_stmt)
        if existing_version_result.scalar_one_or_none() is not None:
            logger.warning(f"Helper: Version string '{version_string}' already exists for document {document_id}.")
            raise ValueError(f"Version string '{version_string}' already exists for this document.")

        new_version_entry = DocumentVersion(
            document_id=document.id,
            content=content,
            version=version_string
        )
        session.add(new_version_entry)

        logger.debug(f"Helper: Updating parent document {document_id} content and version to '{version_string}'.")
        document.content = content
        document.version = version_string
        document.updated_at = datetime.datetime.utcnow() # Manually set if needed

        await session.flush()
        await session.refresh(document)
        await session.refresh(new_version_entry)

        logger.info(f"Helper: Added version '{version_string}' (ID: {new_version_entry.id}) to document {document_id}.")
        return document, new_version_entry

    except ValueError as ve:
        logger.error(f"Helper: Validation error adding version to document {document_id}: {ve}")
        raise # Re-raise ValueError
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding version to document {document_id}: {e}", exc_info=True)
        return None, None # Indicate failure
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding version to document {document_id}: {e}", exc_info=True)
        return None, None

async def _add_tag_to_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool:
    """Core logic to add a tag to a document."""
    logger.debug(f"Helper: Adding tag '{tag_name}' to document ID {document_id} in DB.")
    try:
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for adding tag '{tag_name}'.")
            return False
        tag = await _get_or_create_tag(session, tag_name)
        if tag not in document.tags:
            document.tags.append(tag) # Use append for lists
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' added to document {document_id}.")
        else:
            logger.info(f"Helper: Tag '{tag_name}' already exists on document {document_id}.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False

async def _remove_tag_from_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool:
    """Core logic to remove a tag from a document."""
    logger.debug(f"Helper: Removing tag '{tag_name}' from document ID {document_id} in DB.")
    try:
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for removing tag '{tag_name}'.")
            return True # Success if doc not found
        tag_to_remove = None
        for tag in document.tags:
            if tag.name == tag_name:
                tag_to_remove = tag
                break
        if tag_to_remove:
            document.tags.remove(tag_to_remove)
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' removed from document {document_id}.")
            return True
        else:
            logger.info(f"Helper: Tag '{tag_name}' was not found on document {document_id}.")
            return True # Success if tag not found
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False

async def _get_document_version_content_db(session: AsyncSession, version_id: int) -> DocumentVersion | None:
    """
    Core logic to get a specific document version object by its ID.
    Eagerly loads the parent document for context (like mime type).
    Returns the DocumentVersion object or None if not found.
    """
    logger.debug(f"Helper: Getting document version content for version ID {version_id} in DB.")
    try:
        stmt = select(DocumentVersion).options(
            selectinload(DocumentVersion.document) # Eager load parent document
        ).where(DocumentVersion.id == version_id)
        result = await session.execute(stmt)
        version = result.scalar_one_or_none()

        if version is None:
            logger.warning(f"Helper: DocumentVersion ID {version_id} not found.")
            return None
        elif version.document is None:
             logger.error(f"Helper: Data integrity issue - DocumentVersion {version_id} has no associated document.")
             return None
        else:
             logger.debug(f"Helper: Found DocumentVersion {version_id} (version string: '{version.version}')")
             return version

    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error getting document version {version_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Helper: Unexpected error getting document version {version_id}: {e}", exc_info=True)
        return None

async def _get_memory_entry_db(session: AsyncSession, entry_id: int) -> MemoryEntry | None:
    """
    Core logic to get a specific memory entry by its ID.
    Eagerly loads relationships needed for detail view.
    """
    logger.debug(f"Helper: Getting memory entry ID {entry_id} with relationships from DB.")
    try:
        stmt = select(MemoryEntry).options(
            selectinload(MemoryEntry.project),
            selectinload(MemoryEntry.tags),
            selectinload(MemoryEntry.documents),
            selectinload(MemoryEntry.target_relations).options(
                selectinload(MemoryEntryRelation.source_entry)
            ),
            selectinload(MemoryEntry.source_relations).options(
                selectinload(MemoryEntryRelation.target_entry)
            )
        ).where(MemoryEntry.id == entry_id)

        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry is None:
            logger.warning(f"Helper: MemoryEntry ID {entry_id} not found.")
            return None
        else:
            logger.debug(f"Helper: Found MemoryEntry {entry_id} ('{entry.title}')")
            return entry

    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error getting memory entry {entry_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Helper: Unexpected error getting memory entry {entry_id}: {e}", exc_info=True)
        return None

async def _add_memory_entry_db(
    session: AsyncSession, project_id: int, title: str, type: str, content: str
) -> MemoryEntry | None:
    """Core logic to add a memory entry to the database."""
    logger.debug(f"Helper: Adding memory entry '{title}' (type: {type}) to project {project_id}.")
    try:
        project = await session.get(Project, project_id)
        if project is None:
            logger.warning(f"Helper: Project {project_id} not found for adding memory entry.")
            return None
        new_entry = MemoryEntry(
            project_id=project_id, title=title, type=type, content=content
        )
        session.add(new_entry)
        await session.flush()
        await session.refresh(new_entry)
        logger.info(f"Helper: Memory entry '{title}' (ID: {new_entry.id}) added to project {project_id}.")
        return new_entry
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding memory entry to project {project_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding memory entry to project {project_id}: {e}", exc_info=True)
        return None

async def _update_memory_entry_db(
    session: AsyncSession, entry_id: int, title: Optional[str] = None,
    type: Optional[str] = None, content: Optional[str] = None
) -> MemoryEntry | None:
    """Core logic to update a memory entry's fields in the database."""
    logger.debug(f"Helper: Updating memory entry ID {entry_id} in DB.")
    try:
        entry = await session.get(MemoryEntry, entry_id)
        if entry is None:
            logger.warning(f"Helper: MemoryEntry ID {entry_id} not found for update.")
            return None

        update_data = {"title": title, "type": type, "content": content}
        updated = False
        for key, value in update_data.items():
            if value is not None and getattr(entry, key) != value:
                setattr(entry, key, value)
                updated = True

        if updated:
            logger.debug(f"Helper: Applying updates to memory entry {entry_id}.")
            entry.updated_at = datetime.datetime.utcnow() # Manually set if needed
            await session.flush()
            await session.refresh(entry)
        else:
            logger.debug(f"Helper: No changes detected for memory entry {entry_id}.")

        return entry
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error updating memory entry {entry_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Helper: Unexpected error updating memory entry {entry_id}: {e}", exc_info=True)
        return None

async def _delete_memory_entry_db(session: AsyncSession, entry_id: int) -> tuple[bool, int | None]:
    """
    Core logic to delete a memory entry from the database.
    Returns a tuple: (success_boolean, project_id_or_None).
    """
    logger.debug(f"Helper: Deleting memory entry ID {entry_id} from DB.")
    entry = await session.get(MemoryEntry, entry_id)
    if entry is None:
        logger.warning(f"Helper: MemoryEntry ID {entry_id} not found for deletion.")
        return True, None
    project_id = entry.project_id
    entry_title = entry.title
    try:
        await session.delete(entry)
        await session.flush()
        logger.info(f"Helper: Memory entry ID {entry_id} ('{entry_title}') deleted.")
        return True, project_id
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting memory entry {entry_id}: {e}", exc_info=True)
        return False, project_id
    except Exception as e:
        logger.error(f"Helper: Unexpected error deleting memory entry {entry_id}: {e}", exc_info=True)
        return False, project_id

async def _add_tag_to_memory_entry_db(session: AsyncSession, entry_id: int, tag_name: str) -> bool:
    """Core logic to add a tag to a memory entry."""
    logger.debug(f"Helper: Adding tag '{tag_name}' to memory entry ID {entry_id}.")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == entry_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            logger.warning(f"Helper: MemoryEntry {entry_id} not found for adding tag '{tag_name}'.")
            return False
        tag = await _get_or_create_tag(session, tag_name)
        if tag not in entry.tags:
            entry.tags.append(tag) # Use append
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' added to memory entry {entry_id}.")
        else:
            logger.info(f"Helper: Tag '{tag_name}' already exists on memory entry {entry_id}.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: DB error adding tag '{tag_name}' to memory {entry_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to memory {entry_id}: {e}", exc_info=True)
        return False

async def _remove_tag_from_memory_entry_db(session: AsyncSession, entry_id: int, tag_name: str) -> bool:
    """Core logic to remove a tag from a memory entry."""
    logger.debug(f"Helper: Removing tag '{tag_name}' from memory entry ID {entry_id}.")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == entry_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            logger.warning(f"Helper: MemoryEntry {entry_id} not found for removing tag '{tag_name}'.")
            return True # Success if entry not found
        tag_to_remove = None
        for tag in entry.tags:
            if tag.name == tag_name:
                tag_to_remove = tag
                break
        if tag_to_remove:
            entry.tags.remove(tag_to_remove)
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' removed from memory entry {entry_id}.")
            return True
        else:
            logger.info(f"Helper: Tag '{tag_name}' not found on memory entry {entry_id}.")
            return True # Success if tag not found
    except SQLAlchemyError as e:
        logger.error(f"Helper: DB error removing tag '{tag_name}' from memory {entry_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from memory {entry_id}: {e}", exc_info=True)
        return False

# --- Define MCP Tools using Decorators ---
# IMPORTANT: These tools now need to get the session using the FastAPI dependency system
# or the potentially unreliable get_session_from_mcp_context helper.
# Using FastAPI dependencies is the standard and recommended way.
# This requires refactoring the tools or how they are called if they purely rely on MCP Context.
# For now, assuming get_session_from_mcp_context works or tools are adapted.

# --- Project Tools ---
@mcp_instance.tool()
async def list_projects(ctx: Context) -> Dict[str, Any]:
    logger.info("Handling list_projects request...")
    projects_data = []
    if not ctx: logger.error("Context (ctx) argument missing in list_projects call."); return {"error": "Internal server error: Context missing."}
    try:
        # Use the helper that attempts to get factory from context
        async with await get_session_from_mcp_context(ctx) as session:
            stmt = select(Project).order_by(Project.name)
            result = await session.execute(stmt)
            projects = result.scalars().all()
            for proj in projects:
                projects_data.append({
                     "id": proj.id, "name": proj.name, "description": proj.description, "path": proj.path,
                    "is_active": proj.is_active,
                    "created_at": proj.created_at.isoformat() if proj.created_at else None,
                    "updated_at": proj.updated_at.isoformat() if proj.updated_at else None,
                })
        logger.info(f"Found {len(projects_data)} projects.")
        return {"projects": projects_data}
    except SQLAlchemyError as e: logger.error(f"Database error listing projects: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing projects: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

# ... (rest of the MCP tool definitions remain the same, but their reliance on get_session_from_mcp_context might need review/testing) ...
@mcp_instance.tool()
async def create_project(
    name: str, path: str, description: Optional[str] = None, is_active: bool = False, ctx: Context = None
) -> Dict[str, Any]:
    logger.info(f"Handling create_project MCP tool request: name='{name}'")
    if not ctx: logger.error("Context (ctx) argument missing in create_project call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin(): # Use transaction block
                created_project = await _create_project_in_db(session=session, name=name, path=path, description=description, is_active=is_active)
        logger.info(f"Project created successfully via MCP tool with ID: {created_project.id}")
        return {
            "message": "Project created successfully",
            "project": {
                "id": created_project.id, "name": created_project.name, "description": created_project.description,
                "path": created_project.path, "is_active": created_project.is_active,
                "created_at": created_project.created_at.isoformat() if created_project.created_at else None,
                "updated_at": created_project.updated_at.isoformat() if created_project.updated_at else None,
            }
        }
    except SQLAlchemyError as e: logger.error(f"Database error creating project via MCP tool: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error creating project via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def get_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling get_project request for ID: {project_id}")
    if not ctx: logger.error("Context (ctx) argument missing in get_project call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            project = await session.get(Project, project_id)
            if project is None: logger.warning(f"Project with ID {project_id} not found."); return {"error": f"Project with ID {project_id} not found"}
            logger.info(f"Found project: {project.name}")
            return {
                "project": {
                    "id": project.id, "name": project.name, "description": project.description,
                    "path": project.path, "is_active": project.is_active,
                    "created_at": project.created_at.isoformat() if project.created_at else None,
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                }
            }
    except SQLAlchemyError as e: logger.error(f"Database error getting project {project_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error getting project {project_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def update_project(
    project_id: int, name: Optional[str] = None, description: Optional[str] = None,
    path: Optional[str] = None, is_active: Optional[bool] = None, ctx: Context = None
) -> Dict[str, Any]:
    logger.info(f"Handling update_project MCP tool request for ID: {project_id}")
    if not ctx: logger.error("Context (ctx) argument missing in update_project call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                updated_project = await _update_project_in_db(session=session, project_id=project_id, name=name, description=description, path=path, is_active=is_active)
        if updated_project is None: logger.warning(f"MCP Tool: Project with ID {project_id} not found for update."); return {"error": f"Project with ID {project_id} not found"}
        logger.info(f"Project {project_id} updated successfully via MCP tool.")
        return {
            "message": "Project updated successfully",
            "project": {
                "id": updated_project.id, "name": updated_project.name, "description": updated_project.description,
                "path": updated_project.path, "is_active": updated_project.is_active,
                "created_at": updated_project.created_at.isoformat() if updated_project.created_at else None,
                "updated_at": updated_project.updated_at.isoformat() if updated_project.updated_at else None,
            }
        }
    except SQLAlchemyError as e: logger.error(f"Database error updating project {project_id} via MCP tool: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error updating project {project_id} via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def delete_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling delete_project MCP tool request for ID: {project_id}")
    if not ctx: logger.error("Context (ctx) argument missing in delete_project call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
             async with session.begin():
                deleted = await _delete_project_in_db(session, project_id)
        # Check the result *after* the transaction commits
        if deleted:
            logger.info(f"Project {project_id} deleted successfully via MCP tool.")
            return {"message": f"Project ID {project_id} deleted successfully"}
        else:
            # This case implies a DB error occurred within the helper
            logger.error(f"MCP Tool: Failed to delete project {project_id} due to database error during delete (helper returned False).")
            return {"error": "Database error during project deletion"}
    except SQLAlchemyError as e: logger.error(f"Database error processing delete_project tool for {project_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error processing delete_project tool for {project_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def set_active_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling set_active_project MCP tool request for ID: {project_id}")
    if not ctx: logger.error("Context (ctx) argument missing in set_active_project call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                activated_project = await _set_active_project_in_db(session, project_id)
        if activated_project is None: logger.warning(f"MCP Tool: Project with ID {project_id} not found to activate."); return {"error": f"Project with ID {project_id} not found"}
        logger.info(f"Project {project_id} is now the active project (via MCP tool).")
        return {
             "message": f"Project ID {project_id} set as active",
            "project": { "id": activated_project.id, "name": activated_project.name, "is_active": activated_project.is_active }
        }
    except SQLAlchemyError as e: logger.error(f"Database error setting active project {project_id} via MCP tool: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error setting active project {project_id} via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

# --- Document Tools ---
@mcp_instance.tool()
async def add_document(
    project_id: int, name: str, path: str, content: str, type: str,
    version: str = "1.0.0", ctx: Context = None
) -> Dict[str, Any]:
    logger.info(f"Handling add_document MCP tool request for project ID: {project_id}, name: {name}")
    if not ctx: logger.error("Context (ctx) argument missing in add_document call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                added_document = await _add_document_in_db(session=session, project_id=project_id, name=name, path=path, content=content, type=type, version=version)
        if added_document is None: logger.warning(f"MCP Tool: Project with ID {project_id} not found for adding document."); return {"error": f"Project with ID {project_id} not found"}
        logger.info(f"Document '{name}' (ID: {added_document.id}) added successfully via MCP tool.")
        return {
            "message": "Document added successfully",
            "document": {
                 "id": added_document.id, "project_id": added_document.project_id, "name": added_document.name,
                 "path": added_document.path, "type": added_document.type, "version": added_document.version,
                 "created_at": added_document.created_at.isoformat() if added_document.created_at else None,
                 "updated_at": added_document.updated_at.isoformat() if added_document.updated_at else None,
            }
        }
    except SQLAlchemyError as e: logger.error(f"Database error adding document to project {project_id} via MCP tool: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error adding document to project {project_id} via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def list_documents_for_project(project_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling list_documents_for_project request for project ID: {project_id}")
    documents_data = []
    if not ctx: logger.error("Context (ctx) argument missing in list_documents_for_project call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            project = await session.get(Project, project_id)
            if project is None: logger.warning(f"Project with ID {project_id} not found for listing documents."); return {"error": f"Project with ID {project_id} not found"}
            stmt = select(Document).where(Document.project_id == project_id).order_by(Document.name)
            result = await session.execute(stmt)
            documents = result.scalars().all()
            for doc in documents:
                documents_data.append({
                    "id": doc.id, "project_id": doc.project_id, "name": doc.name, "path": doc.path,
                    "type": doc.type, "version": doc.version,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                })
        logger.info(f"Found {len(documents_data)} documents for project {project_id}.")
        return {"documents": documents_data}
    except SQLAlchemyError as e: logger.error(f"Database error listing documents for project {project_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing documents for project {project_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_document_versions(document_id: int, ctx: Context) -> Dict[str, Any]:
    start_time = time.time()
    logger.info(f"Handling list_document_versions request for document ID: {document_id}")
    versions_data = []
    if not ctx: logger.error("Context (ctx) argument missing in list_document_versions call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
             stmt = select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
             result = await session.execute(stmt)
             document = result.scalar_one_or_none()
             if document is None: logger.warning(f"Document {document_id} not found for listing versions."); return {"error": f"Document {document_id} not found"}
             # Sort versions, perhaps by created_at or semantic version if possible
             sorted_versions = sorted(document.versions, key=lambda v: v.created_at or datetime.datetime.min) # Sort by creation time
             for version in sorted_versions:
                 versions_data.append({
                     "version_id": version.id, "document_id": version.document_id, "version_string": version.version,
                     "created_at": version.created_at.isoformat() if version.created_at else None,
                     "is_current": version.version == document.version # Check against parent doc's current version string
                 })
        logger.info(f"Found {len(versions_data)} versions for document {document_id}.")
        end_time = time.time()
        logger.info(f"list_document_versions for doc {document_id} took {end_time - start_time:.4f} seconds.")
        return {"versions": versions_data}
    except SQLAlchemyError as e: logger.error(f"Database error listing versions for document {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing versions for document {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def get_document_version_content(version_id: int, ctx: Context = None) -> Dict[str, Any]:
    """Tool handler to get the content of a specific document version by its ID."""
    logger.info(f"Handling get_document_version_content TOOL request for version ID: {version_id}")
    if not ctx: logger.error("Context (ctx) argument missing in get_document_version_content call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            version_obj = await _get_document_version_content_db(session, version_id)
            if version_obj is None:
                logger.warning(f"MCP Tool: Failed to get document version {version_id}.")
                return {"error": f"DocumentVersion {version_id} not found or error fetching"}
            logger.info(f"MCP Tool: Found document version '{version_obj.version}' (ID: {version_id}), returning content.")
            return {
                "result": {
                    "content": version_obj.content,
                    "mime_type": version_obj.document.type, # Get type from parent
                    "version_string": version_obj.version,
                    "document_id": version_obj.document_id
                }
            }
    except Exception as e: logger.error(f"Unexpected error processing get_document_version_content tool for {version_id}: {e}", exc_info=True); return {"error": f"Unexpected server error processing tool"}

@mcp_instance.resource("document://{document_id}")
async def get_document_content(document_id: int, ctx: Context) -> Dict[str, Any]: # Added ctx
    logger.info(f"Handling get_document_content resource request for document ID: {document_id}")
    if not ctx: logger.error("Context (ctx) argument missing in get_document_content resource call."); return {"error": "Internal server error: Context missing."}
    try:
        # Use session from context
        async with await get_session_from_mcp_context(ctx) as session:
            document = await session.get(Document, document_id)
            if document is None: logger.warning(f"Document with ID {document_id} not found for resource request."); return {"error": f"Document {document_id} not found"}
            logger.info(f"Found document '{document.name}', returning content.")
            return {"content": document.content, "mime_type": document.type}
    except SQLAlchemyError as e: logger.error(f"Database error getting document {document_id} content: {e}", exc_info=True); return {"error": f"Database error getting document content"}
    except Exception as e: logger.error(f"Unexpected error getting document {document_id} content: {e}", exc_info=True); return {"error": f"Unexpected server error processing resource"}
    # Session closed automatically by context manager

@mcp_instance.tool()
async def update_document(
    document_id: int, name: Optional[str] = None, path: Optional[str] = None,
    content: Optional[str] = None, type: Optional[str] = None,
    version: Optional[str] = None, # Renamed from version_string for clarity
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Updates a document. Handles metadata updates and/or content updates (which creates a new version).
    Requires 'version' if 'content' is provided.
    """
    logger.info(f"Handling update_document MCP tool request for ID: {document_id}")
    if not ctx: logger.error("Context (ctx) argument missing in update_document call."); return {"error": "Internal server error: Context missing."}

    updated_metadata = False
    updated_content = False
    response_doc_data = None

    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                # Handle metadata update first
                if name or path or type:
                    updated_doc_meta = await _update_document_in_db(session=session, document_id=document_id, name=name, path=path, type=type)
                    if updated_doc_meta is None:
                        raise ValueError(f"Document with ID {document_id} not found for metadata update")
                    updated_metadata = True
                    response_doc_data = updated_doc_meta # Store for response
                    logger.info(f"Document {document_id} metadata updated.")
                else:
                    # Fetch the document if only content is being updated
                    response_doc_data = await session.get(Document, document_id)
                    if response_doc_data is None:
                         raise ValueError(f"Document with ID {document_id} not found for content update")

                # Handle content update (create new version)
                if content is not None:
                    if version is None:
                        raise ValueError("Parameter 'version' (new version string) is required when updating 'content'.")
                    updated_doc_content, new_version = await _add_document_version_db(session=session, document_id=document_id, content=content, version_string=version)
                    if updated_doc_content is None or new_version is None:
                        # Error occurred in helper, already logged
                        raise SQLAlchemyError(f"Failed to add new version '{version}' to document {document_id}")
                    updated_content = True
                    response_doc_data = updated_doc_content # Update response data with latest doc state
                    logger.info(f"Document {document_id} content updated to version '{version}'.")

        # Prepare response after commit
        if not updated_metadata and not updated_content:
            message = "No updates performed (no changes specified)."
        elif updated_metadata and updated_content:
            message = "Document metadata and content (new version) updated successfully."
        elif updated_metadata:
            message = "Document metadata updated successfully."
        else: # updated_content only
            message = "Document content updated successfully (new version created)."

        final_doc_dict = {
             "id": response_doc_data.id, "project_id": response_doc_data.project_id,
             "name": response_doc_data.name, "path": response_doc_data.path,
             "type": response_doc_data.type, "version": response_doc_data.version, # This is now the *new* version if content was updated
             "created_at": response_doc_data.created_at.isoformat() if response_doc_data.created_at else None,
             "updated_at": response_doc_data.updated_at.isoformat() if response_doc_data.updated_at else None,
        }
        return {"message": message, "document": final_doc_dict}

    except ValueError as ve: # Catch validation errors (missing version, not found)
        logger.error(f"Validation error updating document {document_id} via MCP tool: {ve}")
        return {"error": str(ve)}
    except SQLAlchemyError as e:
        logger.error(f"Database error updating document {document_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Database error: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error updating document {document_id} via MCP tool: {e}", exc_info=True)
        return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def delete_document(document_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling delete_document MCP tool request for ID: {document_id}")
    if not ctx: logger.error("Context (ctx) argument missing in delete_document call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                deleted = await _delete_document_in_db(session, document_id)
        if deleted: logger.info(f"Document {document_id} deleted successfully via MCP tool."); return {"message": f"Document ID {document_id} deleted successfully"}
        else: logger.error(f"MCP Tool: Failed to delete document {document_id} due to database error during delete."); return {"error": "Database error during document deletion"}
    except SQLAlchemyError as e: logger.error(f"Database error processing delete_document tool for {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error processing delete_document tool for {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

# --- Memory Entry Tools ---
@mcp_instance.tool()
async def add_memory_entry(
    project_id: int, type: str, title: str, content: str, ctx: Context = None
) -> Dict[str, Any]:
    logger.info(f"Handling add_memory_entry MCP request for project ID: {project_id}, title: {title}")
    if not ctx: logger.error("Context (ctx) argument missing in add_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                new_entry = await _add_memory_entry_db(session, project_id, title, type, content)
                if new_entry is None:
                     # Check if project exists using the same session before raising
                     project = await session.get(Project, project_id)
                     error_msg = f"Project with ID {project_id} not found" if project is None else "Database error adding memory entry"
                     logger.warning(f"MCP Tool: {error_msg}") if project is None else logger.error(f"MCP Tool: {error_msg}")
                     raise ValueError(error_msg)
        logger.info(f"MCP Tool: Memory entry '{title}' (ID: {new_entry.id}) added successfully.")
        return {
            "message": "Memory entry added successfully",
            "memory_entry": { "id": new_entry.id, "project_id": new_entry.project_id, "type": new_entry.type, "title": new_entry.title, "created_at": new_entry.created_at.isoformat() if new_entry.created_at else None, "updated_at": new_entry.updated_at.isoformat() if new_entry.updated_at else None }
        }
    except (SQLAlchemyError, ValueError) as e: logger.error(f"Error adding memory entry via MCP tool: {e}", exc_info=False); return {"error": str(e)} # Don't need full traceback for ValueError
    except Exception as e: logger.error(f"Unexpected error adding memory entry via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_memory_entries(project_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling list_memory_entries request for project ID: {project_id}")
    entries_data = []
    if not ctx: logger.error("Context (ctx) argument missing in list_memory_entries call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            project = await session.get(Project, project_id)
            if project is None: logger.warning(f"Project with ID {project_id} not found for listing memory entries."); return {"error": f"Project with ID {project_id} not found"}
            stmt = select(MemoryEntry).where(MemoryEntry.project_id == project_id).order_by(MemoryEntry.updated_at.desc())
            result = await session.execute(stmt)
            entries = result.scalars().all()
            for entry in entries: entries_data.append({ "id": entry.id, "project_id": entry.project_id, "type": entry.type, "title": entry.title, "created_at": entry.created_at.isoformat() if entry.created_at else None, "updated_at": entry.updated_at.isoformat() if entry.updated_at else None, })
        logger.info(f"Found {len(entries_data)} memory entries for project {project_id}.")
        return {"memory_entries": entries_data}
    except SQLAlchemyError as e: logger.error(f"Database error listing memory entries for project {project_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing memory entries for project {project_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def get_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling get_memory_entry MCP request for ID: {memory_entry_id}")
    if not ctx: logger.error("Context (ctx) argument missing in get_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            entry = await _get_memory_entry_db(session, memory_entry_id)
            if entry is None: return {"error": f"MemoryEntry with ID {memory_entry_id} not found or error fetching"}
            logger.info(f"MCP Tool: Found memory entry: {entry.title}")
            tags = sorted([tag.name for tag in entry.tags])
            linked_docs = [{"id": doc.id, "name": doc.name} for doc in entry.documents]
            relations_from = [{"relation_id": rel.id, "type": rel.relation_type, "target_id": rel.target_memory_entry_id, "target_title": rel.target_entry.title if rel.target_entry else None} for rel in entry.source_relations]
            relations_to = [{"relation_id": rel.id, "type": rel.relation_type, "source_id": rel.source_memory_entry_id, "source_title": rel.source_entry.title if rel.source_entry else None} for rel in entry.target_relations]
            return { "memory_entry": { "id": entry.id, "project_id": entry.project_id, "type": entry.type, "title": entry.title, "content": entry.content, "created_at": entry.created_at.isoformat() if entry.created_at else None, "updated_at": entry.updated_at.isoformat() if entry.updated_at else None, "tags": tags, "linked_documents": linked_docs, "relations_from_this": relations_from, "relations_to_this": relations_to } }
    except Exception as e: logger.error(f"Unexpected error processing get_memory_entry tool for {memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def update_memory_entry(
    memory_entry_id: int, type: Optional[str] = None, title: Optional[str] = None,
    content: Optional[str] = None, ctx: Context = None
) -> Dict[str, Any]:
    logger.info(f"Handling update_memory_entry MCP request for ID: {memory_entry_id}")
    if not ctx: logger.error("Context (ctx) argument missing in update_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                updated_entry = await _update_memory_entry_db(session, memory_entry_id, title=title, type=type, content=content)
                if updated_entry is None: error_msg = f"MemoryEntry with ID {memory_entry_id} not found"; logger.warning(f"MCP Tool: {error_msg}"); raise ValueError(error_msg)
        logger.info(f"MCP Tool: Memory entry {memory_entry_id} updated successfully.")
        return {
            "message": "Memory entry updated successfully",
            "memory_entry": { "id": updated_entry.id, "project_id": updated_entry.project_id, "type": updated_entry.type, "title": updated_entry.title, "created_at": updated_entry.created_at.isoformat() if updated_entry.created_at else None, "updated_at": updated_entry.updated_at.isoformat() if updated_entry.updated_at else None }
        }
    except (SQLAlchemyError, ValueError) as e: logger.error(f"Error updating memory entry {memory_entry_id} via MCP tool: {e}", exc_info=False); return {"error": str(e)}
    except Exception as e: logger.error(f"Unexpected error updating memory entry {memory_entry_id} via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def delete_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling delete_memory_entry MCP request for ID: {memory_entry_id}")
    if not ctx: logger.error("Context (ctx) argument missing in delete_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                success, _ = await _delete_memory_entry_db(session, memory_entry_id)
                if not success: error_msg = "Database error during memory entry deletion"; logger.error(f"MCP Tool: {error_msg}"); raise SQLAlchemyError(error_msg)
        logger.info(f"MCP Tool: Memory entry {memory_entry_id} deleted successfully.")
        return {"message": f"Memory entry ID {memory_entry_id} deleted successfully"}
    except SQLAlchemyError as e: logger.error(f"Database error processing delete_memory_entry tool for {memory_entry_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error processing delete_memory_entry tool for {memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


# --- Tagging Tools ---
@mcp_instance.tool()
async def add_tag_to_document(document_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling MCP tool add_tag_to_document request for doc ID: {document_id}, tag: {tag_name}")
    if not ctx: logger.error("Context (ctx) argument missing in add_tag_to_document call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin(): success = await _add_tag_to_document_db(session, document_id, tag_name)
            if success: logger.info(f"MCP Tool: Tag '{tag_name}' added/already present on document {document_id}."); return {"message": f"Tag '{tag_name}' associated with document {document_id}"}
            else:
                # Check if document exists before returning generic DB error
                doc_exists = await session.get(Document, document_id)
                if doc_exists is None: return {"error": f"Document {document_id} not found"}
                else: logger.error(f"MCP Tool: Failed to add tag '{tag_name}' to document {document_id}."); return {"error": f"Database error adding tag '{tag_name}' to document {document_id}"}
    except SQLAlchemyError as e: logger.error(f"Database error processing add_tag_to_document tool for {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error processing add_tag_to_document tool for {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def remove_tag_from_document(document_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling MCP tool remove_tag_from_document request for doc ID: {document_id}, tag: {tag_name}")
    if not ctx: logger.error("Context (ctx) argument missing in remove_tag_from_document call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin(): success = await _remove_tag_from_document_db(session, document_id, tag_name)
            if success: logger.info(f"MCP Tool: Tag '{tag_name}' removed or was not present on document {document_id}."); return {"message": f"Tag '{tag_name}' disassociated from document {document_id}"}
            else: logger.error(f"MCP Tool: Failed to remove tag '{tag_name}' from document {document_id} due to DB error."); return {"error": f"Database error removing tag '{tag_name}' from document {document_id}"}
    except SQLAlchemyError as e: logger.error(f"Database error processing remove_tag_from_document tool for {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error processing remove_tag_from_document tool for {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def list_tags_for_document(document_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling list_tags_for_document request for doc ID: {document_id}")
    tag_names = []
    if not ctx: logger.error("Context (ctx) argument missing in list_tags_for_document call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
             stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
             result = await session.execute(stmt)
             document = result.scalar_one_or_none()
             if document is None: logger.warning(f"Document {document_id} not found for listing tags."); return {"error": f"Document {document_id} not found"}
             tag_names = sorted([tag.name for tag in document.tags])
        logger.info(f"Found {len(tag_names)} tags for document {document_id}.")
        return {"tags": tag_names}
    except SQLAlchemyError as e: logger.error(f"Database error listing tags for document {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing tags for document {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def add_tag_to_memory_entry(memory_entry_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling add_tag_to_memory_entry MCP request for entry ID: {memory_entry_id}, tag: {tag_name}")
    if not ctx: logger.error("Context (ctx) argument missing in add_tag_to_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                success = await _add_tag_to_memory_entry_db(session, memory_entry_id, tag_name)
                if not success:
                    # Check if entry exists
                    entry_exists = await session.get(MemoryEntry, memory_entry_id)
                    error_msg = f"MemoryEntry {memory_entry_id} not found" if entry_exists is None else f"Database error adding tag '{tag_name}' to memory entry {memory_entry_id}"
                    logger.error(f"MCP Tool: {error_msg}")
                    raise ValueError(error_msg)
        logger.info(f"MCP Tool: Tag '{tag_name}' added/associated with memory entry {memory_entry_id}.")
        return {"message": f"Tag '{tag_name}' associated with memory entry {memory_entry_id}"}
    except (SQLAlchemyError, ValueError) as e: logger.error(f"Error adding tag to memory entry {memory_entry_id} via MCP tool: {e}", exc_info=False); return {"error": str(e)}
    except Exception as e: logger.error(f"Unexpected error adding tag to memory entry {memory_entry_id} via MCP tool: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def remove_tag_from_memory_entry(memory_entry_id: int, tag_name: str, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling remove_tag_from_memory_entry MCP request for entry ID: {memory_entry_id}, tag: {tag_name}")
    if not ctx: logger.error("Context (ctx) argument missing in remove_tag_from_memory_entry call."); return {"error": "Internal server error: Context missing."}
    message = None
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                success = await _remove_tag_from_memory_entry_db(session, memory_entry_id, tag_name)
                if not success: error_msg = f"Database error removing tag '{tag_name}' from memory entry {memory_entry_id}"; logger.error(f"MCP Tool: {error_msg}"); raise SQLAlchemyError(error_msg)
                else: message = f"Tag '{tag_name}' disassociated from memory entry {memory_entry_id}"; logger.info(f"MCP Tool: {message}")
        return {"message": message}
    except SQLAlchemyError as e: logger.error(f"Database error processing remove_tag_from_memory_entry tool for {memory_entry_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error processing remove_tag_from_memory_entry tool for {memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_tags_for_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling list_tags_for_memory_entry request for entry ID: {memory_entry_id}")
    tag_names = []
    if not ctx: logger.error("Context (ctx) argument missing in list_tags_for_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
             stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == memory_entry_id)
             result = await session.execute(stmt)
             entry = result.scalar_one_or_none()
             if entry is None: logger.warning(f"MemoryEntry {memory_entry_id} not found for listing tags."); return {"error": f"MemoryEntry {memory_entry_id} not found"}
             tag_names = sorted([tag.name for tag in entry.tags])
        logger.info(f"Found {len(tag_names)} tags for memory entry {memory_entry_id}.")
        return {"tags": tag_names}
    except SQLAlchemyError as e: logger.error(f"Database error listing tags for memory entry {memory_entry_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing tags for memory entry {memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

# --- Relationship Management Tools ---
@mcp_instance.tool()
async def link_memory_entry_to_document(memory_entry_id: int, document_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling link_memory_entry_to_document request for entry ID: {memory_entry_id} and doc ID: {document_id}")
    if not ctx: logger.error("Context (ctx) argument missing in link_memory_entry_to_document call."); return {"error": "Internal server error: Context missing."}
    message = None
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                entry_stmt = select(MemoryEntry).options(selectinload(MemoryEntry.documents)).where(MemoryEntry.id == memory_entry_id)
                entry_res = await session.execute(entry_stmt)
                entry = entry_res.scalar_one_or_none()
                document = await session.get(Document, document_id)
                if entry is None: return {"error": f"MemoryEntry {memory_entry_id} not found"}
                if document is None: return {"error": f"Document {document_id} not found"}
                if document in entry.documents: logger.info(f"Document {document_id} is already linked to MemoryEntry {memory_entry_id}."); message = "Link already exists"
                else: entry.documents.append(document); logger.info(f"Linked Document {document_id} to MemoryEntry {memory_entry_id}."); message = f"Linked document {document_id} to memory entry {memory_entry_id}"
        return {"message": message}
    except SQLAlchemyError as e: logger.error(f"Database error linking memory entry {memory_entry_id} to doc {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error linking memory entry {memory_entry_id} to doc {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_documents_for_memory_entry(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling list_documents_for_memory_entry request for entry ID: {memory_entry_id}")
    documents_data = []
    if not ctx: logger.error("Context (ctx) argument missing in list_documents_for_memory_entry call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
             stmt = select(MemoryEntry).options(selectinload(MemoryEntry.documents)).where(MemoryEntry.id == memory_entry_id)
             result = await session.execute(stmt)
             entry = result.scalar_one_or_none()
             if entry is None: logger.warning(f"MemoryEntry {memory_entry_id} not found for listing documents."); return {"error": f"MemoryEntry {memory_entry_id} not found"}
             for doc in entry.documents: documents_data.append({ "id": doc.id, "name": doc.name, "path": doc.path, "type": doc.type, "version": doc.version, "created_at": doc.created_at.isoformat() if doc.created_at else None, "updated_at": doc.updated_at.isoformat() if doc.updated_at else None, })
        logger.info(f"Found {len(documents_data)} linked documents for memory entry {memory_entry_id}.")
        return {"linked_documents": documents_data}
    except SQLAlchemyError as e: logger.error(f"Database error listing documents for memory entry {memory_entry_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing documents for memory entry {memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def link_memory_entries(
    source_memory_entry_id: int, target_memory_entry_id: int,
    relation_type: Optional[str] = None, ctx: Context = None
) -> Dict[str, Any]:
    logger.info(f"Handling link_memory_entries request from {source_memory_entry_id} to {target_memory_entry_id} (type: {relation_type})")
    if not ctx: logger.error("Context (ctx) argument missing in link_memory_entries call."); return {"error": "Internal server error: Context missing."}
    if source_memory_entry_id == target_memory_entry_id: return {"error": "Cannot link a memory entry to itself"}
    new_relation = None
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                source_entry = await session.get(MemoryEntry, source_memory_entry_id)
                target_entry = await session.get(MemoryEntry, target_memory_entry_id)
                if source_entry is None: return {"error": f"Source MemoryEntry {source_memory_entry_id} not found"}
                if target_entry is None: return {"error": f"Target MemoryEntry {target_memory_entry_id} not found"}
                # Check if relation already exists (optional)
                existing_rel_stmt = select(MemoryEntryRelation).where(
                    MemoryEntryRelation.source_memory_entry_id == source_memory_entry_id,
                    MemoryEntryRelation.target_memory_entry_id == target_memory_entry_id,
                    MemoryEntryRelation.relation_type == relation_type # Match type too if provided
                )
                existing_rel_res = await session.execute(existing_rel_stmt)
                if existing_rel_res.scalar_one_or_none() is not None:
                    logger.warning(f"Relation from {source_memory_entry_id} to {target_memory_entry_id} (type: {relation_type}) already exists.")
                    return {"error": "Relation already exists"}

                new_relation = MemoryEntryRelation(source_memory_entry_id=source_memory_entry_id, target_memory_entry_id=target_memory_entry_id, relation_type=relation_type)
                session.add(new_relation)
                await session.flush(); await session.refresh(new_relation) # Get ID etc.
        logger.info(f"Linked MemoryEntry {source_memory_entry_id} to {target_memory_entry_id}. Relation ID: {new_relation.id}")
        return { "message": "Memory entries linked successfully", "relation": { "id": new_relation.id, "source_id": new_relation.source_memory_entry_id, "target_id": new_relation.target_memory_entry_id, "type": new_relation.relation_type, "created_at": new_relation.created_at.isoformat() if new_relation.created_at else None } }
    except SQLAlchemyError as e: logger.error(f"Database error linking memory entries {source_memory_entry_id} -> {target_memory_entry_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error linking memory entries {source_memory_entry_id} -> {target_memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}


@mcp_instance.tool()
async def list_related_memory_entries(memory_entry_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling list_related_memory_entries request for entry ID: {memory_entry_id}")
    relations_from = []; relations_to = []
    if not ctx: logger.error("Context (ctx) argument missing in list_related_memory_entries call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
             stmt = select(MemoryEntry).options(selectinload(MemoryEntry.source_relations).options(selectinload(MemoryEntryRelation.target_entry)), selectinload(MemoryEntry.target_relations).options(selectinload(MemoryEntryRelation.source_entry))).where(MemoryEntry.id == memory_entry_id)
             result = await session.execute(stmt)
             entry = result.scalar_one_or_none()
             if entry is None: logger.warning(f"MemoryEntry {memory_entry_id} not found for listing relations."); return {"error": f"MemoryEntry {memory_entry_id} not found"}
             for rel in entry.source_relations:
                 if rel.target_entry: relations_from.append({ "relation_id": rel.id, "relation_type": rel.relation_type, "target_entry_id": rel.target_memory_entry_id, "target_entry_title": rel.target_entry.title, "created_at": rel.created_at.isoformat() if rel.created_at else None, })
             for rel in entry.target_relations:
                 if rel.source_entry: relations_to.append({ "relation_id": rel.id, "relation_type": rel.relation_type, "source_entry_id": rel.source_memory_entry_id, "source_entry_title": rel.source_entry.title, "created_at": rel.created_at.isoformat() if rel.created_at else None, })
        logger.info(f"Found {len(relations_from)} outgoing and {len(relations_to)} incoming relations for memory entry {memory_entry_id}.")
        return {"relations_from_this": relations_from, "relations_to_this": relations_to}
    except SQLAlchemyError as e: logger.error(f"Database error listing relations for memory entry {memory_entry_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error listing relations for memory entry {memory_entry_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def unlink_memory_entry_from_document(memory_entry_id: int, document_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling unlink_memory_entry_from_document request for entry ID: {memory_entry_id} and doc ID: {document_id}")
    if not ctx: logger.error("Context (ctx) argument missing in unlink_memory_entry_from_document call."); return {"error": "Internal server error: Context missing."}
    message = None
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                stmt = select(MemoryEntry).options(selectinload(MemoryEntry.documents)).where(MemoryEntry.id == memory_entry_id)
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()
                if entry is None: logger.warning(f"MemoryEntry {memory_entry_id} not found for unlinking document."); return {"error": f"MemoryEntry {memory_entry_id} not found"}
                document_to_remove = None
                for doc in entry.documents:
                    if doc.id == document_id: document_to_remove = doc; break
                if document_to_remove: entry.documents.remove(document_to_remove); logger.info(f"Unlinked Document {document_id} from MemoryEntry {memory_entry_id}."); message = f"Unlinked document {document_id} from memory entry {memory_entry_id}"
                else: logger.warning(f"Link between MemoryEntry {memory_entry_id} and Document {document_id} not found."); message = "Link not found"
        return {"message": message}
    except SQLAlchemyError as e: logger.error(f"Database error unlinking memory entry {memory_entry_id} from doc {document_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error unlinking memory entry {memory_entry_id} from doc {document_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

@mcp_instance.tool()
async def unlink_memory_entries(relation_id: int, ctx: Context) -> Dict[str, Any]:
    logger.info(f"Handling unlink_memory_entries request for relation ID: {relation_id}")
    if not ctx: logger.error("Context (ctx) argument missing in unlink_memory_entries call."); return {"error": "Internal server error: Context missing."}
    try:
        async with await get_session_from_mcp_context(ctx) as session:
            async with session.begin():
                relation = await session.get(MemoryEntryRelation, relation_id)
                if relation is None: logger.warning(f"MemoryEntryRelation with ID {relation_id} not found for deletion."); return {"error": f"Relation with ID {relation_id} not found"}
                logger.info(f"Deleting relation ID: {relation_id} (linking {relation.source_memory_entry_id} -> {relation.target_memory_entry_id})")
                await session.delete(relation)
        logger.info(f"Relation {relation_id} deleted successfully.")
        return {"message": f"Relation ID {relation_id} deleted successfully"}
    except SQLAlchemyError as e: logger.error(f"Database error deleting relation {relation_id}: {e}", exc_info=True); return {"error": f"Database error: {e}"}
    except Exception as e: logger.error(f"Unexpected error deleting relation {relation_id}: {e}", exc_info=True); return {"error": f"Unexpected server error: {e}"}

# Ensure MCP instance tools are registered if using auto-discovery or manual registration
# If FastMCP relies on scanning the module, ensure this file is imported appropriately.