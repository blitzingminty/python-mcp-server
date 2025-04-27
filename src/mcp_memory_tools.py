# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

import logging
from src.mcp_server_core import mcp_instance
from .mcp_db_helpers_memory import list_memory_entries_db
from src.database import get_db_session
from typing import Any, Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_session_from_factory():
    async for session in get_db_session():
        yield session

@mcp_instance.tool(name="list_memory", description="List all memory entries")
async def list_memory(project_id: int):
    logger.info("MCP Tool 'list_memory' called.")

    async with get_session_from_factory() as session:
        memory_entries = await list_memory_entries_db(session, project_id)
        memory_list = []
        for entry in memory_entries:
            memory_list.append({
                "id": entry.id,
                "title": entry.title,
                "type": entry.type,
                "content": entry.content
            })
        return {"memory_entries": memory_list}

@mcp_instance.tool(name="create_memory", description="Create a new memory entry")
async def create_memory(project_id: int, title: str, type: str, content: str):
    logger.info("MCP Tool 'create_memory' called with data: %s", {"title": title, "type": type, "content": content})

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_memory import add_memory_entry_db
        memory_entry = await add_memory_entry_db(session, project_id, title, type, content)
        if memory_entry:
            await session.commit()
            return {
                "status": "created",
                "memory_entry": {
                    "id": memory_entry.id,
                    "title": memory_entry.title,
                    "type": memory_entry.type,
                    "content": memory_entry.content
                }
            }
        else:
            return {"status": "error", "message": "Failed to create memory entry"}

@mcp_instance.tool(name="get_memory", description="Retrieve details for a memory entry")
async def get_memory(memory_id: int):
    logger.info("MCP Tool 'get_memory' called for memory_id: %d", memory_id)

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_memory import get_memory_entry_db
        memory_entry = await get_memory_entry_db(session, memory_id)
        if memory_entry:
            return {
                "id": memory_entry.id,
                "title": memory_entry.title,
                "type": memory_entry.type,
                "content": memory_entry.content
            }
        else:
            return {"status": "error", "message": f"Memory entry with id {memory_id} not found"}

@mcp_instance.tool(name="add_tag_to_memory_entry", description="Add a tag to a memory entry")
async def add_tag_to_memory_entry(memory_id: int, tag_name: str):
    logger.info("MCP Tool 'add_tag_to_memory_entry' called for memory_id: %d, tag_name: %s", memory_id, tag_name)

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_memory import add_tag_to_memory_entry_db
        success = await add_tag_to_memory_entry_db(session, memory_id, tag_name)
        if success:
            await session.commit()
            return {"status": "success", "message": f"Tag '{tag_name}' added to memory entry with id {memory_id}"}
        else:
            return {"status": "error", "message": f"Failed to add tag '{tag_name}' to memory entry with id {memory_id}"}

@mcp_instance.tool(name="delete_memory", description="Delete a memory entry")
async def delete_memory(memory_id: int):
    logger.info("MCP Tool 'delete_memory' called for memory_id: %d", memory_id)

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_memory import delete_memory_entry_db
        success, project_id = await delete_memory_entry_db(session, memory_id)
        if success:
            await session.commit()
            return {"status": "deleted", "memory_id": memory_id}
        else:
            return {"status": "error", "message": f"Failed to delete memory entry with id {memory_id}"}

@mcp_instance.tool(name="add_tag_to_memory_entry", description="Add a tag to a memory entry")
async def add_tag_to_memory_entry_1(memory_id: int, tag_name: str):
    logger.info("MCP Tool 'add_tag_to_memory_entry' called for memory_id: %d, tag_name: %s", memory_id, tag_name)

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_memory import add_tag_to_memory_entry_db
        success = await add_tag_to_memory_entry_db(session, memory_id, tag_name)
        if success:
            await session.commit()
            return {"status": "success", "message": f"Tag '{tag_name}' added to memory entry with id {memory_id}"}
        else:
            return {"status": "error", "message": f"Failed to add tag '{tag_name}' to memory entry with id {memory_id}"}

@mcp_instance.tool(name="add_memory_relation", description="Add a relation between two memory entries")
async def add_memory_relation(memory_id_source: int, memory_id_target: int, relation_type: Optional[str] = None):
    logger.info("MCP Tool 'add_memory_relation' called for memory_id_source: %d, memory_id_target: %d, relation_type: %s", memory_id_source, memory_id_target, relation_type)

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_relations import link_memory_entries_db
        relation = await link_memory_entries_db(session, memory_id_source, memory_id_target, relation_type)
        if relation:
            await session.commit()
            return {"status": "success", "message": f"Relation added between memory entries {memory_id_source} and {memory_id_target} with id {relation.id}"}
        else:
            return {"status": "error", "message": f"Failed to add relation between memory entries {memory_id_source} and {memory_id_target}"}

@mcp_instance.tool(name="remove_memory_relation", description="Remove a relation between two memory entries")
async def remove_memory_relation(relation_id: int):
    logger.info("MCP Tool 'remove_memory_relation' called for relation_id: %d", relation_id)

    async with get_session_from_factory() as session:
        from .mcp_db_helpers_relations import unlink_memory_entry_relation_db
        success = await unlink_memory_entry_relation_db(session, relation_id)
        if success:
            return {"status": "success", "message": f"Relation with id {relation_id} removed"}
        else:
            return {"status": "error", "message": f"Failed to remove relation with id {relation_id}"}

# Additional tools for managing memory tags and relations can be implemented here.
