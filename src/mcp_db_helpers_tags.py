import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from .models import Tag

logger = logging.getLogger(__name__)

async def get_or_create_tag(session: AsyncSession, tag_name: str) -> Tag:
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
            tag = result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"Database error getting/creating tag '{tag_name}': {e}", exc_info=True)
            raise
    return tag
