# Implementation Plan: Fix `app_lifespan` Lifespan Error for FastAPI Compatibility (Updated for Modular Approach)

## Background
The current `app_lifespan` function was designed as an async context manager that takes a `FastMCP` instance and yields a dictionary with context data. FastAPI expects the lifespan function to accept a `FastAPI` instance and yield `None` (or an async context manager compatible with FastAPI's lifespan protocol). This mismatch causes type errors and runtime issues.

With the new modular structure, lifespan management and MCP server lifecycle are separated into different modules.

---

## Goal
Refactor lifespan management to be compatible with FastAPI's expected lifespan signature while preserving MCP server lifecycle management, reflecting the new modular file structure.

---

## Proposed Changes

### 1. Create Two Separate Lifespan Functions in `src/mcp_server_lifespan.py`

- `fastapi_lifespan`:
  - Accepts a `FastAPI` instance.
  - Yields `None`.
  - Performs database initialization.
  - Stores `AsyncSessionFactory` in `app.state` for access in routes and tools.
  - Passed to FastAPI app's `lifespan` parameter.

- `mcp_lifespan`:
  - Accepts a `FastMCP` instance.
  - Yields a context dictionary with `db_session_factory`.
  - Passed to `FastMCP` constructor.

### 2. Update `src/main.py`

- Import and use `fastapi_lifespan` for FastAPI app lifespan.
- Import `mcp_lifespan` for MCP server instance.
- Adjust code to access session factory from `app.state` in FastAPI routes and from MCP context in MCP tools.

### 3. Adjust MCP Tools and Helper Functions

- For FastAPI routes, retrieve session factory from `app.state.db_session_factory`.
- For MCP tools, continue using MCP lifespan context.
- Update imports and references to reflect modular helper files.

### 4. Testing and Validation

- Test both FastAPI HTTP mode and MCP STDIO mode.
- Ensure database initialization and session management work correctly.
- Confirm no lifespan-related type errors.
- Verify context data accessibility.

---

## Summary of File Changes

| File                  | Description                                      |
|-----------------------|-------------------------------------------------|
| `src/mcp_server_lifespan.py` | Add `fastapi_lifespan` and `mcp_lifespan` functions |
| `src/main.py`         | Use `fastapi_lifespan` for FastAPI app lifespan |
| MCP tools/helpers     | Adjust context/session factory access accordingly |

---

## Next Steps

- Implement the above changes in the respective modules.
- Test thoroughly.
- Remove any legacy lifespan code from old files.
- Ensure all references are updated to the modular structure.

---

**This updated plan is saved for future reference.**
