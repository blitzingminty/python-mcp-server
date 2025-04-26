# Active Context

## Current Work Focus
- Fixed async generator usage in MCP memory and document tools by removing the `ctx` parameter and replacing session management with the async context manager `get_session_from_factory`.
- Ensured consistent async session handling across all MCP tools.
- Added Pylance suppression comments to reduce false positives related to async context manager typing.

## Recent Changes
- Updated `src/mcp_memory_tools.py` to replace all `async with get_db_session()` usage with `async with get_session_from_factory()`.
- Updated `src/mcp_document_tools.py` to remove `ctx` parameters and replace session acquisition with `async with get_session_from_factory()`.
- Verified manual testing indicates all async generator usage errors are resolved.

## Active Decisions and Considerations
- `get_session_from_factory` is the standard async context manager for acquiring database sessions in MCP tools.
- MCP tools no longer accept the `ctx` parameter for session management.
- Pylance false positives on async context manager typing are suppressed with comments.

## Learnings and Insights
- Proper async generator consumption is critical for stable async session management with SQLAlchemy.
- Consistent patterns across MCP tools improve maintainability and reduce runtime errors.
- Static type checkers may require suppression comments due to complex async typing in SQLAlchemy.

## Next Steps
- Continue monitoring MCP tools for any runtime issues.
- Update Memory Bank documentation as needed for future reference.
- Proceed with further MCP tool enhancements or bug fixes as requested.
