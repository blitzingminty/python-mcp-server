import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError #, IntegrityError
from sqlalchemy.orm import selectinload

from .models import Document, DocumentVersion #, Tag
#from .database import AsyncSessionFactory

logger = logging.getLogger(__name__)

async def add_document_in_db( # type: ignore
    session: AsyncSession, project_id: int, name: str, path: str, content: str,
    type: str, version: str = "1.0.0"
) -> Optional[Document]:
    logger.debug(f"Helper: Adding document '{name}' to project {project_id}.")
    project = await session.get(Document.__table__.c.project_id.type.python_type, project_id)
    if project is None:
        logger.warning(f"Helper: Project {project_id} not found for adding document.")
        return None
    new_document = Document(project_id=project_id, name=name, path=path, content=content, type=type, version=version)
    session.add(new_document)
    await session.flush()
    new_version_entry = DocumentVersion(document_id=new_document.id, content=content, version=version)
    session.add(new_version_entry)
    await session.refresh(new_document)
    await session.refresh(new_version_entry)
    logger.info(f"Helper: Document '{name}' (ID: {new_document.id}) added to project {project_id}.")
    return new_document

async def update_document_in_db( # type: ignore
    session: AsyncSession, document_id: int, name: Optional[str] = None,
    path: Optional[str] = None, type: Optional[str] = None
) -> Optional[Document]:
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
    logger.debug(f"Helper: Deleting document ID {document_id} from DB.")
    doc = await session.get(Document, document_id, options=[selectinload(Document.tags), selectinload(Document.versions)])
    if doc is None:
        logger.warning(f"Helper: Document ID {document_id} not found for deletion.")
        return True
    try:
        await session.delete(doc)
        await session.flush()
        logger.info(f"Helper: Document ID {document_id} ('{doc.name}') deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting document {document_id}: {e}", exc_info=True)
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
        elif version.document is None:  # type: ignore[comparison-overlap]
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


async def add_document_version_db( # type: ignore
    session: AsyncSession, document_id: int, content: str, version_string: str
) -> Tuple[Optional[Document], Optional[DocumentVersion]]:
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

        document.content = content
        document.version = version_string

        await session.flush()
        await session.refresh(document)
        await session.refresh(new_version_entry)

        logger.info(f"Helper: Added version '{version_string}' (ID: {new_version_entry.id}) to document {document_id}.")
        return document, new_version_entry

    except ValueError as ve:
        logger.error(f"Helper: Validation error adding version to document {document_id}: {ve}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding version to document {document_id}: {e}", exc_info=True)
        return None, None
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding version to document {document_id}: {e}", exc_info=True)
        return None, None

async def add_tag_to_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool: # type: ignore
    logger.debug(f"Helper: Adding tag '{tag_name}' to document ID {document_id} in DB.")
    try:
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for adding tag '{tag_name}'.")
            return False
        from .mcp_db_helpers_tags import get_or_create_tag
        tag = await get_or_create_tag(session, tag_name)
        if tag in document.tags:
            logger.info(f"Helper: Tag '{tag_name}' already exists on document {document_id}.")
            return True
        else:
            document.tags.add(tag)
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' added to document {document_id}.")
            return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to document {document_id}: {e}", exc_info=True)
        return False

async def remove_tag_from_document_db(session: AsyncSession, document_id: int, tag_name: str) -> bool: # type: ignore
    logger.debug(f"Helper: Removing tag '{tag_name}' from document ID {document_id} in DB.")
    try:
        stmt = select(Document).options(selectinload(Document.tags)).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            logger.warning(f"Helper: Document {document_id} not found for removing tag '{tag_name}'.")
            return True
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
            return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from document {document_id}: {e}", exc_info=True)
        return False
