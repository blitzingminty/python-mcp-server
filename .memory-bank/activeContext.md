# activeContext.md

## Current Work Focus
- Implementing robust async session management for document MCP tools to resolve the persistent `greenlet_spawn has not been called` error.
- Created a dedicated utility module `src/mcp_session_utils.py` with proper async context management.
- Refactored document MCP tools to use the new session management pattern.
- Testing document MCP tools to verify the resolution of async context errors.
- Investigating why write operations (create_document) still trigger the greenlet_spawn error despite the refactoring.

## Recent Changes
- Created `src/mcp_session_utils.py` with two key functions:
  - `async def get_session_from_mcp_context(ctx: Context) -> AsyncSession`: Retrieves an AsyncSession from the MCP context.
  - `@asynccontextmanager async def managed_mcp_session(ctx: Context)`: Manages the session lifecycle with proper commit/rollback/close handling.
- Refactored all document MCP tools in `src/mcp_document_tools.py` to:
  - Accept `ctx: Context` as the first parameter.
  - Use `async with managed_mcp_session(ctx) as session:` for database operations.
  - Remove manual session.commit() calls (now handled by the context manager).
  - Ensure proper error handling and response formatting.
- Removed legacy session management code and get_logged_session_from_factory.

## Next Steps
- Implement Solution 1 from `.memory-bank/solution_greenlet_spawn_error.md` to resolve the persistent greenlet_spawn error:
  1. Modify `src/mcp_session_utils.py` to use the same session acquisition pattern as the working project/memory tools.
  2. Update the `managed_mcp_session` context manager to use `get_db_session()` with `async for` to properly establish the greenlet context.
  3. Update all document MCP tools to add explicit commit calls where needed.
  4. Test with the mcp-session-context-remote server to verify the solution resolves the error.
- If Solution 1 doesn't resolve the issue, consider the fallback options documented in the solution file.
- Test all document MCP tools thoroughly after implementing the fix.

## Active Decisions and Considerations
- The decision to use a dedicated utility module for session management helps avoid circular imports and promotes code reuse.
- The managed_mcp_session context manager provides consistent session lifecycle management across all document tools.
- The ctx parameter is essential for accessing the lifespan context where the AsyncSessionFactory is stored.
- Explicit commit calls may still be needed in specific cases, even with the context manager.

## Learnings and Insights
- The greenlet_spawn error indicates that SQLAlchemy's async context is not properly established or propagated.
- FastMCP's execution context for tools may differ from FastAPI's request context, affecting how async resources should be managed.
- Project and memory tools work correctly with their session management approach, suggesting a subtle difference in how they handle async context.
- The error specifically affects write operations (create, update) that involve complex state transitions in SQLAlchemy.
- Consistent transaction management is critical for MCP tool reliability, especially for write operations.
