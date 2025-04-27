# Solution: Resolving Greenlet_Spawn Error in Document MCP Tools

## Problem Summary
Document MCP tools, particularly write operations like `create_document`, are triggering the `greenlet_spawn has not been called` error despite refactoring to use a dedicated session management utility. This error indicates that SQLAlchemy's async context is not properly established or propagated when the tools are executed by FastMCP.

## Root Cause Analysis
After comparing the working session management approach in project and memory tools with our refactored approach in document tools, a key difference was identified:

1. **Working Approach (project/memory tools)**:
   ```python
   @asynccontextmanager
   async def get_session_from_factory():
       async for session in get_db_session():
           yield session
   ```

2. **Our Refactored Approach (document tools)**:
   ```python
   async def get_session_from_mcp_context(ctx: Context) -> AsyncSession:
       session_factory = ctx.request_context.lifespan_context["db_session_factory"]
       session = session_factory()
       return session

   @asynccontextmanager
   async def managed_mcp_session(ctx: Context):
       session = await get_session_from_mcp_context(ctx)
       try:
           yield session
           await session.commit()
       except Exception as e:
           await session.rollback()
           raise
       finally:
           await session.close()
   ```

The critical difference is that the working approach uses `async for` with `get_db_session()`, which appears to establish the greenlet context correctly, while our approach directly calls the factory and manages the session lifecycle manually.

## Solution: Adopt the Working Pattern

### Detailed Implementation Plan

1. **Modify `src/mcp_session_utils.py`** to use the same pattern as the working tools:

```python
import logging
from contextlib import asynccontextmanager
from mcp.server.fastmcp import Context
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db_session

logger = logging.getLogger(__name__)

@asynccontextmanager
async def managed_mcp_session(ctx: Context):
    """
    Async context manager that handles the lifecycle of an AsyncSession.
    Uses the same pattern as the working project/memory tools by leveraging
    get_db_session() with async for, which properly establishes the greenlet context.
    
    Args:
        ctx: The FastMCP Context object (required for API compatibility but not used)
        
    Yields:
        AsyncSession: The database session for use in MCP tools
    """
    async for session in get_db_session():
        try:
            yield session
            # Let the caller handle commit explicitly if needed
            # This matches the pattern in project/memory tools
        finally:
            # Session is closed automatically by get_db_session
            pass
```

2. **Update document MCP tools** to use the modified `managed_mcp_session` and add explicit commit calls where needed:

```python
@mcp_instance.tool(name="create_document", description="Create a new document")
async def create_document(ctx: Context, project_id: int, name: str, path: str, content: str, type: str, version: str = "1.0.0"):
    logger.info(f"MCP Tool 'create_document' called for project_id: {project_id}, name: {name}.")
    async with managed_mcp_session(ctx) as session:
        document = await add_document_in_db(session, project_id=project_id, name=name, path=path, content=content, type=type, version=version)
        if document:
            # Add explicit commit call to match pattern in project/memory tools
            await session.commit()
            logger.info(f"MCP Tool 'create_document' successfully created document ID: {document.id}.")
            return {
                "status": "created",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags]
                }
            }
        else:
            logger.error(f"MCP Tool 'create_document' failed to create document for project_id: {project_id}, name: {name}.")
            return {"status": "error", "message": "Failed to create document"}
```

3. **Apply similar updates to all document MCP tools** that perform write operations:
   - `update_document`
   - `delete_document`
   - `add_document_tag`
   - `remove_document_tag`
   - `create_document_version`
   - `delete_document_version`

### Technical Explanation

The key insight is that `get_db_session()` is a FastAPI dependency that yields an `AsyncSession`. When used with `async for`, it properly establishes the greenlet context required by SQLAlchemy's async ORM operations. This pattern works correctly in the project and memory tools.

Our refactored approach attempted to access the session factory directly from the FastMCP context and manage the session lifecycle manually, but this bypassed the critical greenlet context setup that happens within `get_db_session()`.

By adopting the same pattern as the working tools, we leverage the proven approach while maintaining the benefits of our refactoring (consistent session management, error handling, and ctx parameter for API compatibility).

### Expected Outcome

After implementing this solution:
1. The `greenlet_spawn has not been called` error should no longer occur for write operations.
2. All document MCP tools should function correctly, with proper transaction management.
3. The code will maintain a consistent pattern across all MCP tools (project, memory, and document).

### Testing Strategy

1. Implement the changes to `src/mcp_session_utils.py`.
2. Update all document MCP tools to use the modified `managed_mcp_session` and add explicit commit calls.
3. Test with the mcp-session-context-remote server, focusing on write operations that currently fail.
4. Verify that the greenlet_spawn error no longer occurs.
5. Test all document MCP tools to ensure they function correctly.

### Fallback Options

If this solution does not resolve the issue, two alternative approaches can be considered:

1. **Hybrid Approach with Explicit Greenlet Context**: Modify `get_session_from_mcp_context` to ensure proper greenlet context using SQLAlchemy's async_scoped_session.

2. **Direct Use of AsyncEngine**: Bypass the session factory and create sessions directly from the engine, which might establish the greenlet context differently.

However, the solution outlined above is the most promising as it directly adopts the pattern that is already working in other parts of the codebase.
