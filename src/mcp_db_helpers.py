# src/mcp_db_helpers.py
# Contains internal database interaction logic for the MCP server.

import logging
from typing import Optional, Tuple # Changed tuple to Tuple

# --- SQLAlchemy Imports ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import selectinload

# --- Model Imports ---
from .models import Project, Document, DocumentVersion, MemoryEntry, Tag, MemoryEntryRelation

logger = logging.getLogger(__name__)

# --- DB Helper Functions ---

async def get_or_create_tag(session: AsyncSession, tag_name: str) -> Tag:
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
            await session.rollback()
            stmt = select(Tag).where(Tag.name == tag_name)
            result = await session.execute(stmt)
            tag = result.scalar_one() # Should exist now
        except SQLAlchemyError as e:
            logger.error(f"Database error getting/creating tag '{tag_name}': {e}", exc_info=True)
            raise
    return tag

async def create_project_in_db( # type: ignore
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

async def update_project_in_db( # type: ignore
    session: AsyncSession, project_id: int, name: Optional[str] = None,
    description: Optional[str] = None, path: Optional[str] = None, is_active: Optional[bool] = None
) -> Project | None:
    """Core logic to update a project in the database."""
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
    """Core logic to delete a project from the database."""
    logger.debug(f"Helper: Deleting project ID {project_id} from DB.")
    project = await session.get(Project, project_id)
    if project is None:
        logger.warning(f"Helper: Project ID {project_id} not found for deletion.")
        return True # Indicate deletion (or non-existence) is complete
    try:
        await session.delete(project)
        await session.flush()
        logger.info(f"Helper: Project ID {project_id} deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting project {project_id}: {e}", exc_info=True)
        return False

async def set_active_project_in_db(session: AsyncSession, project_id: int) -> Project | None: # type: ignore
    """Core logic to set a project as active, deactivating others."""
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

async def add_document_in_db( # type: ignore
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
    await session.refresh(new_document) # Refresh to get default values if any
    await session.refresh(new_version_entry) # Refresh to get default values if any
    logger.info(f"Helper: Document '{name}' (ID: {new_document.id}) added to project {project_id}.")
    return new_document

async def update_document_in_db( # type: ignore
    session: AsyncSession, document_id: int, name: Optional[str] = None,
    path: Optional[str] = None, type: Optional[str] = None
) -> Document | None:
    """Core logic to update a document's metadata (excluding content/version)."""
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
        await session.flush()
        await session.refresh(document)
    else:
        logger.debug(f"Helper: No metadata changes detected for document {document_id}.")
    return document

async def delete_document_in_db(session: AsyncSession, document_id: int) -> bool: # type: ignore
    """Core logic to delete a document and its associated versions/tags via cascade."""
    logger.debug(f"Helper: Deleting document ID {document_id} from DB.")
    # Eager load relationships that might cause issues if not handled by cascade (though cascade should work)
    doc = await session.get(Document, document_id, options=[selectinload(Document.tags), selectinload(Document.versions)])
    if doc is None:
        logger.warning(f"Helper: Document ID {document_id} not found for deletion.")
        return True # Indicate deletion (or non-existence) is complete
    doc_name = doc.name # Store name for logging before deletion
    try:
        await session.delete(doc)
        await session.flush()
        logger.info(f"Helper: Document ID {document_id} ('{doc_name}') deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting document {document_id}: {e}", exc_info=True)
        return False

async def add_document_version_db( # type: ignore
    session: AsyncSession, document_id: int, content: str, version_string: str
) -> Tuple[Document | None, DocumentVersion | None]: # Changed tuple to Tuple
    """
    Core logic to add a new version to a document.
    Creates a new DocumentVersion record and updates the parent Document's
    content and version fields.
    Returns (updated_document, new_version_record) on success, or (None, None) on failure.
    Raises ValueError if version string already exists.
    """
    logger.debug(f"Helper: Adding new version '{version_string}' to document ID {document_id}.")
    try:
        # Fetch the parent document
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for adding version.")
            return None, None # Indicate document not found

        # Check if this version string already exists for this document
        existing_version_stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version == version_string
        )
        existing_version_result = await session.execute(existing_version_stmt)
        existing_version: Optional[DocumentVersion] = existing_version_result.scalar_one_or_none()
        if existing_version is not None:
             logger.warning(f"Helper: Version string '{version_string}' already exists for document {document_id}.")
             raise ValueError(f"Version string '{version_string}' already exists for this document.")

        # Create the new DocumentVersion entry
        new_version_entry = DocumentVersion(
            document_id=document.id,
            content=content,
            version=version_string
        )
        session.add(new_version_entry)

        # Update the parent document's content and version string
        logger.debug(f"Helper: Updating parent document {document_id} content and version to '{version_string}'.")
        document.content = content
        document.version = version_string
        # The document's updated_at will be handled by the model's onupdate

        # Flush to ensure version gets ID and document updates are staged
        await session.flush()
        # Refresh both objects to get updated states (like timestamps, IDs)
        await session.refresh(document)
        await session.refresh(new_version_entry)

        logger.info(f"Helper: Added version '{version_string}' (ID: {new_version_entry.id}) to document {document_id}.")
        return document, new_version_entry # Return both updated objects

    except ValueError as ve: # Catch specific validation error
        logger.error(f"Helper: Validation error adding version to document {document_id}: {ve}")
        raise # Re-raise ValueError for route handler to catch specifically
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding version to document {document_id}: {e}", exc_info=True)
        # Rollback will be handled by session.begin() in the caller
        return None, None # Indicate failure
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error adding version to document {document_id}: {e}", exc_info=True)
        return None, None

async def add_tag_to_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool: # type: ignore
    """Core logic to add a tag to a document."""
    logger.debug(f"Helper: Adding tag '{tag_name}' to document ID {document_id} in DB.")
    try:
        # Use options to load tags relationship
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for adding tag '{tag_name}'.")
            return False # Indicate failure: document not found

        tag = await get_or_create_tag(session, tag_name) # Re-use tag creation/retrieval logic

        if tag in document.tags:
            logger.info(f"Helper: Tag '{tag_name}' already exists on document {document_id}.")
            return True # Indicate success: tag already present
        else:
            document.tags.add(tag)
            await session.flush() # Persist the association
            logger.info(f"Helper: Tag '{tag_name}' added to document {document_id}.")
            return True # Indicate success: tag added
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False # Indicate failure: database error
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False

async def remove_tag_from_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool: # type: ignore
    """Core logic to remove a tag from a document."""
    logger.debug(f"Helper: Removing tag '{tag_name}' from document ID {document_id} in DB.")
    try:
        # Use options to load tags relationship
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()

        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for removing tag '{tag_name}'.")
            return True # Indicate success: document doesn't exist, so tag isn't associated

        tag_to_remove = None
        for tag in document.tags:
            if tag.name == tag_name:
                tag_to_remove = tag
                break

        if tag_to_remove:
            document.tags.remove(tag_to_remove)
            await session.flush() # Persist the removal
            logger.info(f"Helper: Tag '{tag_name}' removed from document {document_id}.")
            return True # Indicate success: tag removed
        else:
            logger.info(f"Helper: Tag '{tag_name}' was not found on document {document_id}.")
            return True # Indicate success: tag wasn't there to begin with
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False # Indicate failure: database error
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False

async def get_document_version_content_db(session: AsyncSession, version_id: int) -> DocumentVersion | None: # type: ignore
    """
    Core logic to get a specific document version object by its ID.
    Eagerly loads the parent document for context (like mime type).
    Returns the DocumentVersion object or None if not found.
    """
    logger.debug(f"Helper: Getting document version content for version ID {version_id} in DB.")
    try:
        # Fetch the specific version, eagerly loading the parent document
        stmt = select(DocumentVersion).options(
            selectinload(DocumentVersion.document) # Eager load parent document
        ).where(DocumentVersion.id == version_id)
        result = await session.execute(stmt)
        version = result.scalar_one_or_none()

        if version is None:
            logger.warning(f"Helper: DocumentVersion ID {version_id} not found.")
            return None # Indicate not found
        elif version.document is None:
             # This case should be rare if FK constraints are working, but good to check
             logger.error(f"Helper: Data integrity issue - DocumentVersion {version_id} has no associated document.")
             # Treat as not found or raise an internal error? Returning None seems safer.
             return None
        else:
             logger.debug(f"Helper: Found DocumentVersion {version_id} (version string: '{version.version}')")
             return version # Return the found version object

    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error getting document version {version_id}: {e}", exc_info=True)
        # Re-raise or return None? Returning None to indicate failure to retrieve.
        return None
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error getting document version {version_id}: {e}", exc_info=True)
        return None

async def get_memory_entry_db(session: AsyncSession, entry_id: int) -> MemoryEntry | None: # type: ignore
    """
    Core logic to get a specific memory entry by its ID.
    Eagerly loads relationships needed for detail view.
    """
    logger.debug(f"Helper: Getting memory entry ID {entry_id} with relationships from DB.")
    try:
        stmt = select(MemoryEntry).options(
            selectinload(MemoryEntry.project), # Load parent project
            selectinload(MemoryEntry.tags), # Load associated tags
            selectinload(MemoryEntry.documents), # Load linked documents
            # Load relationships TO this entry (where this entry is the target)
            selectinload(MemoryEntry.target_relations).options(
                selectinload(MemoryEntryRelation.source_entry) # Load the source entry of the relation
            ),
            # Load relationships FROM this entry (where this entry is the source)
            selectinload(MemoryEntry.source_relations).options(
                selectinload(MemoryEntryRelation.target_entry) # Load the target entry of the relation
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
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error getting memory entry {entry_id}: {e}", exc_info=True)
        return None

async def add_memory_entry_db( # type: ignore
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
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error adding memory entry to project {project_id}: {e}", exc_info=True)
        return None

async def update_memory_entry_db( # type: ignore
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
            await session.flush()
            await session.refresh(entry)
        else:
            logger.debug(f"Helper: No changes detected for memory entry {entry_id}.")

        return entry
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error updating memory entry {entry_id}: {e}", exc_info=True)
        return None
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error updating memory entry {entry_id}: {e}", exc_info=True)
        return None

async def delete_memory_entry_db(session: AsyncSession, entry_id: int) -> Tuple[bool, int | None]:  # type: ignore
    """
    Core logic to delete a memory entry from the database.
    Returns a tuple: (success_boolean, project_id_or_None).
    """
    logger.debug(f"Helper: Deleting memory entry ID {entry_id} from DB.")
    # Eager load relationships that might cause issues if not handled by cascade
    entry = await session.get(MemoryEntry, entry_id, options=[
        selectinload(MemoryEntry.tags),
        selectinload(MemoryEntry.documents),
        selectinload(MemoryEntry.source_relations),
        selectinload(MemoryEntry.target_relations)
    ])
    if entry is None:
        logger.warning(f"Helper: MemoryEntry ID {entry_id} not found for deletion.")
        return True, None # Indicate deletion (or non-existence) is complete
    project_id = entry.project_id
    entry_title = entry.title # Store for logging
    try:
        await session.delete(entry)
        await session.flush()
        logger.info(f"Helper: Memory entry ID {entry_id} ('{entry_title}') deleted.")
        return True, project_id
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting memory entry {entry_id}: {e}", exc_info=True)
        return False, project_id
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error deleting memory entry {entry_id}: {e}", exc_info=True)
        return False, project_id

async def add_tag_to_memory_entry_db(session: AsyncSession, entry_id: int, tag_name: str) -> bool: # type: ignore
    """Core logic to add a tag to a memory entry."""
    logger.debug(f"Helper: Adding tag '{tag_name}' to memory entry ID {entry_id}.")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == entry_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            logger.warning(f"Helper: MemoryEntry {entry_id} not found for adding tag '{tag_name}'.")
            return False # Indicate failure: entry not found
        tag = await get_or_create_tag(session, tag_name)
        if tag in entry.tags:
            logger.info(f"Helper: Tag '{tag_name}' already exists on memory entry {entry_id}.")
            return True # Indicate success: tag already present
        else:
            entry.tags.add(tag)
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' added to memory entry {entry_id}.")
            return True # Indicate success: tag added
    except SQLAlchemyError as e:
        logger.error(f"Helper: DB error adding tag '{tag_name}' to memory {entry_id}: {e}", exc_info=True)
        return False # Indicate failure: database error
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to memory {entry_id}: {e}", exc_info=True)
        return False

async def remove_tag_from_memory_entry_db(session: AsyncSession, entry_id: int, tag_name: str) -> bool: # type: ignore
    """Core logic to remove a tag from a memory entry."""
    logger.debug(f"Helper: Removing tag '{tag_name}' from memory entry ID {entry_id}.")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == entry_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            logger.warning(f"Helper: MemoryEntry {entry_id} not found for removing tag '{tag_name}'.")
            return True # Indicate success: entry doesn't exist
        tag_to_remove = None
        for tag in entry.tags:
            if tag.name == tag_name:
                tag_to_remove = tag
                break
        if tag_to_remove:
            entry.tags.remove(tag_to_remove)
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' removed from memory entry {entry_id}.")
            return True # Indicate success: tag removed
        else:
            logger.info(f"Helper: Tag '{tag_name}' not found on memory entry {entry_id}.")
            return True # Indicate success: tag wasn't there
    except SQLAlchemyError as e:
        logger.error(f"Helper: DB error removing tag '{tag_name}' from memory {entry_id}: {e}", exc_info=True)
        return False # Indicate failure: database error
    except Exception as e: # Catch unexpected errors
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from memory {entry_id}: {e}", exc_info=True)
        return False
