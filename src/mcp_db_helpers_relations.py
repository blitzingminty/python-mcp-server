import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from .models import MemoryEntryRelation, MemoryEntry

logger = logging.getLogger(__name__)

async def link_memory_entries_db(
    session: AsyncSession, source_memory_entry_id: int, target_memory_entry_id: int,
    relation_type: Optional[str] = None
) -> Optional[MemoryEntryRelation]:
    logger.debug(f"Helper: Linking memory entries {source_memory_entry_id} -> {target_memory_entry_id} with type '{relation_type}'.")
    if source_memory_entry_id == target_memory_entry_id:
        logger.warning("Helper: Cannot link a memory entry to itself.")
        return None
    try:
        source_entry = await session.get(MemoryEntry, source_memory_entry_id)
        target_entry = await session.get(MemoryEntry, target_memory_entry_id)
        if source_entry is None or target_entry is None:
            logger.warning(f"Helper: Source or target memory entry not found (source: {source_memory_entry_id}, target: {target_memory_entry_id}).")
            return None
        new_relation = MemoryEntryRelation(
            source_memory_entry_id=source_memory_entry_id,
            target_memory_entry_id=target_memory_entry_id,
            relation_type=relation_type
        )
        session.add(new_relation)
        await session.flush()
        await session.refresh(new_relation)
        logger.info(f"Helper: Linked memory entries with relation ID {new_relation.id}.")
        return new_relation
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error linking memory entries: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Helper: Unexpected error linking memory entries: {e}", exc_info=True)
        return None

async def unlink_memory_entry_relation_db(session: AsyncSession, relation_id: int) -> bool:
    logger.debug(f"Helper: Unlinking memory entry relation ID {relation_id}.")
    try:
        relation = await session.get(MemoryEntryRelation, relation_id)
        if relation is None:
            logger.warning(f"Helper: MemoryEntryRelation ID {relation_id} not found for deletion.")
            return False
        await session.delete(relation)
        await session.flush()
        logger.info(f"Helper: MemoryEntryRelation ID {relation_id} deleted.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Helper: Database error deleting memory entry relation {relation_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Helper: Unexpected error deleting memory entry relation {relation_id}: {e}", exc_info=True)
        return False
