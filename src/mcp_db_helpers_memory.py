import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from .models import MemoryEntry, MemoryEntryRelation, Project #, Tag
#from .database import AsyncSessionFactory

logger = logging.getLogger(__name__)

async def get_memory_entry_db(session: AsyncSession, entry_id: int) -> Optional[MemoryEntry]: # type: ignore
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

async def add_memory_entry_db( # type: ignore
    session: AsyncSession, project_id: int, title: str, type: str, content: str
) -> Optional[MemoryEntry]:
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

async def update_memory_entry_db( # type: ignore
    session: AsyncSession, entry_id: int, title: Optional[str] = None,
    type: Optional[str] = None, content: Optional[str] = None
) -> Optional[MemoryEntry]:
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
    except Exception as e:
        logger.error(f"Helper: Unexpected error updating memory entry {entry_id}: {e}", exc_info=True)
        return None

async def delete_memory_entry_db(session: AsyncSession, entry_id: int) -> Tuple[bool, Optional[int]]: # type: ignore
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

async def add_tag_to_memory_entry_db(session: AsyncSession, entry_id: int, tag_name: str) -> bool: # type: ignore
    logger.debug(f"Helper: Adding tag '{tag_name}' to memory entry ID {entry_id}.")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == entry_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            logger.warning(f"Helper: MemoryEntry {entry_id} not found for adding tag '{tag_name}'.")
            return False
        from .mcp_db_helpers_tags import get_or_create_tag
        tag = await get_or_create_tag(session, tag_name)
        if tag in entry.tags:
            logger.info(f"Helper: Tag '{tag_name}' already exists on memory entry {entry_id}.")
            return True
        else:
            entry.tags.add(tag)
            await session.flush()
            logger.info(f"Helper: Tag '{tag_name}' added to memory entry {entry_id}.")
            return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: DB error adding tag '{tag_name}' to memory {entry_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error adding tag '{tag_name}' to memory {entry_id}: {e}", exc_info=True)
        return False

async def remove_tag_from_memory_entry_db(session: AsyncSession, entry_id: int, tag_name: str) -> bool: # type: ignore
    logger.debug(f"Helper: Removing tag '{tag_name}' from memory entry ID {entry_id}.")
    try:
        stmt = select(MemoryEntry).options(selectinload(MemoryEntry.tags)).where(MemoryEntry.id == entry_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            logger.warning(f"Helper: MemoryEntry {entry_id} not found for removing tag '{tag_name}'.")
            return True
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
            return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: DB error removing tag '{tag_name}' from memory {entry_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error removing tag '{tag_name}' from memory {entry_id}: {e}", exc_info=True)
        return False
