# Implementation Plan: Fix `app_lifespan` Lifespan Error for FastAPI Compatibility

## Background
The current `app_lifespan` function in `src/mcp_server_instance.py` is designed as an async context manager that takes a `FastMCP` instance and yields a dictionary with context data. However, FastAPI expects the lifespan function to accept a `FastAPI` instance and yield `None` (or an async context manager compatible with FastAPI's lifespan protocol). This mismatch causes type errors in Pylance and may cause runtime issues.

---

## Goal
Refactor the lifespan management to be compatible with FastAPI's expected lifespan signature while preserving the existing functionality for FastMCP.

---

## Proposed Changes

### 1. Refactor `app_lifespan` to `fastapi_lifespan`

- Change the argument to accept a `FastAPI` instance.
- Yield `None` instead of a dictionary.
- Move any context data (e.g., `AsyncSessionFactory`) to `app.state` for access elsewhere.
- Keep the database initialization logic intact.
- This function will be passed to FastAPI's `lifespan` parameter.

**Code Example:**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def fastapi_lifespan(app: FastAPI):
    # Database initialization logic here (same as current)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        # Log error, decide on behavior
        pass

    # Store session factory in app.state for access in routes/tools
    app.state.db_session_factory = AsyncSessionFactory

    yield

    # Optional cleanup logic here
```

---

### 2. Adapt MCP Instance Creation

- Create a separate lifespan function for FastMCP that matches its expected signature (taking `FastMCP` instance and yielding context dictionary).
- Pass this MCP-specific lifespan function to the `FastMCP` constructor.
- This keeps MCP lifecycle management separate from FastAPI's.

**Code Example:**

```python
@asynccontextmanager
async def mcp_lifespan(server: FastMCP):
    # Same as current app_lifespan implementation
    # Yield context dictionary with session factory
    context_data = {"db_session_factory": AsyncSessionFactory}
    yield context_data
```

---

### 3. Update `src/main.py` to Use `fastapi_lifespan`

- Import and use `fastapi_lifespan` as the lifespan argument when creating the FastAPI app.
- Access the session factory in routes/tools via `request.app.state.db_session_factory` or equivalent.

---

### 4. Update MCP Tools and Context Access

- Modify MCP tools and helper functions to retrieve the session factory from the appropriate context.
- For FastAPI routes, use `app.state.db_session_factory`.
- For MCP tools, continue using the MCP lifespan context as before.

---

### 5. Testing and Validation

- Test both FastAPI HTTP mode and MCP STDIO mode to ensure database initialization and session management work correctly.
- Validate no type errors remain related to lifespan.
- Confirm that context data is accessible where needed.

---

## Summary

| File                 | Change Description                                      |
|----------------------|---------------------------------------------------------|
| `src/mcp_server_instance.py` | Split lifespan into `mcp_lifespan` and `fastapi_lifespan` functions |
| `src/main.py`        | Use `fastapi_lifespan` for FastAPI app lifespan          |
| MCP tools/helpers    | Adjust context/session factory access accordingly        |

---

This plan ensures compatibility with FastAPI's lifespan protocol while preserving MCP server lifecycle management and database initialization.

---

**Next Steps:**

- Implement the above changes.
- Test thoroughly.
- Address any further issues.

---

**This plan is saved for future reference.**
