# Active Context

## Current Work Focus
- Fixed persistence issue in MCP `create_project` tool by adding explicit `await session.commit()` after project creation.
- Confirmed that projects created via MCP tools are now properly persisted and retrievable.
- Verified consistency between MCP tools and Web UI for project creation and retrieval.
- Continued investigation plan for MCP tool issues, focusing on session and transaction management.
- Maintained async session management patterns using `get_session_from_factory` context manager.
- Addressed boolean parameter input coercion in MCP tool handlers to prevent validation errors.

## Recent Changes
- Updated `src/mcp_project_tools.py` `create_project` handler to include explicit commit.
- Tested `create_project` and `get_project` tools to confirm fix effectiveness.
- Documented findings and updated Memory Bank accordingly.

## Active Decisions and Considerations
- Explicit commit calls are necessary in MCP tool handlers to ensure data persistence.
- MCP tools and Web UI routes differ in transaction commit handling; MCP tools require explicit commits.
- Continue reviewing other MCP tools for similar commit handling improvements.
- Maintain consistent async session management patterns across MCP tools.

## Learnings and Insights
- Async session context managers do not auto-commit transactions; explicit commit is required.
- Proper transaction management is critical for data consistency and visibility.
- Input coercion for boolean parameters improves robustness of MCP tool handlers.
- Comprehensive testing and comparison with Web UI implementations help identify discrepancies.

## Next Steps
- Review and update other MCP tool handlers to include explicit commit calls where needed.
- Expand automated tests to cover transaction management scenarios.
- Monitor MCP tool runtime behavior for any further persistence or retrieval issues.
- Update Memory Bank documentation to reflect transaction management best practices.
