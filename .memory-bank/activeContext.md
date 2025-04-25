# Active Context

**Date:** 2025-04-25

## Current Work & Recent Changes
- Resolved the MCP tool registration issue in `src/mcp_server_core.py`.
- Fixed a problem where duplicate or unsafe calls to the original add_tool function were causing tool registration errors.
- Applied logging patches to FastMCP.add_tool, ToolManager.add_tool, and FastMCP.list_tools to ensure that tool registrations are properly tracked.

## Findings & Resolution
- The root cause was identified as an inconsistency in how the FastMCP instance was retrieving and calling its original add_tool function. In some cases, it was `None` or not callable.
- A safe retrieval mechanism (using a fallback lambda) was implemented to ensure that if the original add_tool is missing, a harmless no-op is used instead.
- Comprehensive logging was added to diagnose the tool registration process and confirm that all expected MCP tools – list_projects, create_project, get_project, update_project, delete_project, set_active_project, and handle_message – are registered correctly.
- Debug output from running the debug listing script confirmed that the tools are now properly registered and that the logging patches are functioning as intended.

## Learnings
- It's critical to establish a reliable MCP instance creation flow that occurs before any tool modules are imported.
- Careful management of function references (like original_add_tool) is necessary to prevent runtime errors such as "object of type None cannot be called."
- Implementing fallback mechanisms (e.g., checking with callable()) and extensive logging helps in diagnosing and resolving issues in complex initialization flows.
- Testing using a dedicated debug tool (e.g., `src/debug_list_tools.py`) is invaluable for verifying the correctness of tool registration. 

*Memory bank updated to reflect the changes and learnings regarding the MCP tool registration resolution.*
