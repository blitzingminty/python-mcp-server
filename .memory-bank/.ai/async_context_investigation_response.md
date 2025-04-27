## Technical Report: Resolving SQLAlchemy Async Context Error in FastMCP Document Tools

**Date:** 2025-04-27

**Project:** MCP Server with FastAPI, FastMCP, and SQLAlchemy Async

**Issue:** Persistent `MissingGreenlet: greenlet_spawn has not been called` error during the execution of specific MCP document tools (`update_document`), indicating an issue with asynchronous context propagation when using SQLAlchemy's async ORM with FastAPI and FastMCP.

**Status:** Memory and project tools using the same declared async session pattern function correctly. The error is isolated to document tools, particularly update operations.

---

### 1. Executive Summary

The project encounters an asynchronous context error (`MissingGreenlet: greenlet_spawn has not been called`) specifically within the `update_document` MCP tool. This error stems from an incompatibility between how the SQLAlchemy async session is being created/managed within the FastMCP tool's execution context and the requirements of SQLAlchemy's async operations (which rely on `greenlet` for bridging async/sync boundaries, even with async drivers like `aiosqlite`). While other tools work, the `update_document` operation likely triggers specific SQLAlchemy internal states (e.g., during `flush` or `refresh`) that strictly require the `greenlet` context, which appears improperly propagated or missing in the execution path of this specific tool via FastMCP.

The most probable cause is that the current method of obtaining a database session (`get_session_from_factory` -> `get_db_session`) within the MCP tool, while standard for FastAPI endpoints, does not correctly integrate with the execution context managed by FastMCP for its tools.

This report recommends aligning the database session acquisition within MCP tools with FastMCP's context management system, likely by leveraging the `Context` object potentially passed to tools or using a mechanism provided by FastMCP for managing request-scoped resources.

---

### 2. Analysis of the Problem

#### 2.1. Understanding the `greenlet_spawn` Error

SQLAlchemy's asynchronous support, even when using native async DBAPI drivers like `aiosqlite`, utilizes the `greenlet` library internally. `greenlet` allows SQLAlchemy to run blocking DBAPI calls in a separate micro-thread (a greenlet) without blocking the main `asyncio` event loop. The `greenlet_spawn has not been called` error indicates that a SQLAlchemy operation attempted to use this greenlet mechanism, but the necessary async context wrapping the operation was not correctly established or propagated. This typically happens when async SQLAlchemy operations are invoked from a context that isn't managed by `AsyncSession` or `AsyncEngine`'s context management protocols.

#### 2.2. Interaction Points: FastAPI, FastMCP, SQLAlchemy Async

* **FastAPI:** Manages the main `asyncio` event loop for handling HTTP requests. Its dependency injection system (`Depends`) correctly manages resources like DB sessions *within the scope of an HTTP request*. The `get_db_session` function uses this pattern.
* **SQLAlchemy Async:** Requires careful context management. The `AsyncSession` and its methods (`commit`, `flush`, `refresh`, `execute`) must be awaited within a correctly established `asyncio` task that has the `greenlet` integration set up by the session/engine.
* **FastMCP:** Acts as an intermediary, defining and executing "tools". The critical question is *how* FastMCP executes these `async def` tool functions. If it runs them outside the direct FastAPI request context (e.g., in a separate task spawned internally, or via a different mechanism) without correctly propagating the necessary context, SQLAlchemy's async operations can fail.
* **`aiosqlite`:** While an async driver, SQLAlchemy's ORM layer on top still uses `greenlet` for managing transaction states and ensuring compatibility across different driver types.

#### 2.3. Current Session Management in Tools

The document tools (`mcp_document_tools.py`) currently use:

```python
from src.database import get_db_session
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session_from_factory():
    async for session in get_db_session(): # Relies on FastAPI's dependency pattern
        yield session

# Inside the tool:
async with get_session_from_factory() as session:
    # ... operations ...

```

This approach directly calls `get_db_session`, which is designed as a *FastAPI dependency*. While this works perfectly for standard FastAPI endpoints, it might be problematic if FastMCP invokes the tool function (`update_document`) in a way that doesn't automatically provide the context expected by FastAPI's dependency injection mechanism. The session created might be detached from the necessary `greenlet` context required by subsequent SQLAlchemy operations like `session.flush()` or `session.refresh()` within `update_document_in_db`.

#### 2.4. Why `update_document` Might Fail Specifically

Update operations often involve more complex state transitions within the SQLAlchemy session compared to reads (`list`, `get`) or simple additions/deletions:

1.  **Fetching:** `session.get(Document, document_id)` retrieves the object and attaches it to the session.
2.  **Modification:** `setattr(document, key, value)` marks the object instance as "dirty".
3.  **Flush:** `await session.flush()` attempts to synchronize the changes in the session (dirty objects) with the database, emitting SQL (e.g., `UPDATE` statements). This is a common point where context issues manifest, as it involves significant interaction with the database transaction and connection state.
4.  **Refresh:** `await session.refresh(document)` updates the object's attributes from the database after the flush. This also requires proper context.

Simple reads or even `add`/`delete` followed by `commit` might sometimes bypass the specific internal code paths within SQLAlchemy that are most sensitive to the missing `greenlet` context, explaining why other tools might appear to work.

---

### 3. Potential Causes

1.  **Incorrect Async Context Propagation (Most Likely):** FastMCP executes the tool function in an `asyncio` task or context that is not correctly linked to the initial FastAPI request context where `greenlet_spawn` would have been set up by SQLAlchemy's engine/session management tied to the request lifecycle. Using `get_db_session` directly inside the tool bypasses any context management potentially provided by FastMCP itself.
2.  **Session Scope Mismatch:** The session created via `get_session_from_factory` might have a lifecycle tied to the FastAPI dependency mechanism, which might end or become invalid before/during the FastMCP tool's execution, especially if the tool execution is deferred or happens in a background task managed by FastMCP.
3.  **FastMCP Internal Handling:** The way FastMCP awaits or handles the `async def` tool function might interfere with or strip the necessary context required by SQLAlchemy.
4.  **Subtle Bug in `update_document_in_db`:** While less likely given the code looks standard, there might be a subtle interaction with relationship loading or state management specifically within the update helper that triggers the context requirement more strictly.
5.  **Dependency Version Conflicts:** Incompatibility between `sqlalchemy`, `greenlet`, `aiosqlite`, `fastapi`, or `fastmcp` versions.

---

### 4. Recommendations and Solutions

#### 4.1. Align Session Management with FastMCP Context (Primary Recommendation)

The most robust solution is to obtain the `AsyncSession` using the mechanism intended by FastMCP, assuming it provides one. This usually involves accessing resources set up during the application lifespan via a context object passed to the tool.

* **Identify FastMCP Context:** Determine if FastMCP tool functions receive a context object (like the `ctx: Context[Any, Any]` mentioned in the commented-out code in `mcp_server_core.py`). Consult FastMCP documentation or examples.
* **Access Session Factory from Context:** Modify the tools to get the `AsyncSessionFactory` from the FastMCP context, which should have access to the `lifespan_context` established in `mcp_server_core.py`.

**Example (Conceptual - Adapt based on actual FastMCP API):**

```python
# src/mcp_server_core.py (Ensure lifespan stores the factory)
@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[Dict[str, Any]]:
    # ... (database init) ...
    context_data = {"db_session_factory": AsyncSessionFactory} # Correctly stored
    try:
        yield context_data
    finally:
        logger.info("Application lifespan shutdown.")

mcp_instance = FastMCP(
    # ...
    lifespan=app_lifespan
)

# --- Define a helper to get session from MCP context ---
# (Place this in a shared utility module or mcp_server_core.py if no circular imports)
async def get_session_from_mcp_context(ctx: Context[Any, Any]) -> AsyncSession:
    """Gets an AsyncSession using the factory stored in the lifespan context."""
    try:
        # The exact path to lifespan_context might differ based on FastMCP's Context structure
        session_factory = ctx.request_context.lifespan_context["db_session_factory"]
        # Create a new session instance for this tool execution
        return session_factory()
    except (KeyError, AttributeError) as e:
        logger.error(f"Failed to get DB session factory from FastMCP context: {e}", exc_info=True)
        raise RuntimeError("Server configuration error: DB Session Factory missing or context structure invalid.")

# src/mcp_document_tools.py (Modify tools)
from src.mcp_server_core import mcp_instance # Or wherever get_session_from_mcp_context is defined
from mcp.server.fastmcp import Context # Assuming Context is importable

# Remove get_session_from_factory and its usage

@mcp_instance.tool(name="update_document", description="Update an existing document")
async def update_document(
    ctx: Context[Any, Any], # <--- Assume context is passed by FastMCP
    document_id: int,
    name: str | None = None,
    path: str | None = None,
    type: str | None = None
):
    logger.info(f"MCP Tool 'update_document' called for document_id: {document_id}...")
    # Use the MCP context-aware session getter
    session: AsyncSession | None = None
    try:
        session = await get_session_from_mcp_context(ctx)
        document = await update_document_in_db(session, document_id=document_id, name=name, path=path, type=type)
        if document:
            await session.commit() # Commit happens here
            logger.info(f"MCP Tool 'update_document' successfully updated document ID: {document_id}.")
            # ... (return success response) ...
        else:
            # ... (return error response) ...
            pass # No commit needed if update_document_in_db returned None or didn't update

    except Exception as e:
        logger.error(f"Error during update_document tool execution: {e}", exc_info=True)
        if session:
            await session.rollback() # Rollback on any exception
        # ... (return error response) ...
        raise # Optionally re-raise or return error structure
    finally:
        if session:
            await session.close() # Ensure session is closed

    # --- Apply similar changes to other document tools ---
    # Modify list_documents, create_document, get_document, delete_document
    # to accept the 'ctx' and use 'get_session_from_mcp_context'
    # Ensure proper try/except/finally blocks with commit/rollback/close logic.

```

* **Session Lifecycle:** The example above manually handles session creation, commit/rollback, and closing. A potentially cleaner approach is to use an `asynccontextmanager` based on `get_session_from_mcp_context`:

```python
# In a shared utility module or alongside get_session_from_mcp_context
@asynccontextmanager
async def managed_mcp_session(ctx: Context[Any, Any]) -> AsyncGenerator[AsyncSession, None]:
    session = await get_session_from_mcp_context(ctx)
    try:
        yield session
        # Commit is handled *outside* the context manager in the tool function
        # await session.commit() # DON'T commit here unless always desired
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# In mcp_document_tools.py
@mcp_instance.tool(name="update_document", description="Update an existing document")
async def update_document(ctx: Context[Any, Any], document_id: int, ...):
    logger.info(...)
    async with managed_mcp_session(ctx) as session:
        document = await update_document_in_db(session, document_id=document_id, ...)
        if document:
            # Decide whether to commit based on the helper's logic/return
            await session.commit() # Commit changes if update was successful
            logger.info(...)
            # ... return success ...
        else:
            logger.warning(...)
            # ... return error ...
    # No need for explicit close, context manager handles it
```

#### 4.2. Verify `update_document_in_db` Logic

* Double-check the flow within `update_document_in_db`. Ensure `session.flush()` and `session.refresh(document)` are necessary. If the goal is just to persist the changes and return the potentially updated data, often a `commit()` is sufficient, and SQLAlchemy handles the flush implicitly before the commit. Refresh is only needed if you need database-generated values (like triggers, defaults) immediately after the update within the same transaction.
* Temporarily comment out `await session.flush()` and `await session.refresh(document)` (if `commit` is still performed later) to see if the error specifically originates there.

#### 4.3. Check Environment and Dependencies

* Ensure `sqlalchemy`, `greenlet`, `aiosqlite`, `fastapi`, and `fastmcp` are updated to recent, compatible versions. Check their respective release notes for any known issues related to async context propagation.
    * `pip list` or `poetry show`
    * Consult documentation for compatibility matrices if available.

#### 4.4. Enhance Logging

* Add logging *inside* `managed_mcp_session` (or equivalent) to log session creation and closing.
* Add specific log points immediately before and after `await session.flush()`, `await session.refresh()`, and `await session.commit()` calls within the helper functions and tool functions to pinpoint the exact failure point.
* Log `asyncio.current_task()` at various points to see if the task context changes unexpectedly during tool execution.

---

### 5. References

* **SQLAlchemy AsyncIO Documentation:**
    * Engine/Session: [https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncSession](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncSession)
    * Contextual Sessions: [https://docs.sqlalchemy.org/en/20/orm/session_basics.html#contextual-thread-local-sessions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#contextual-thread-local-sessions) (While for sync, the context management concepts are relevant).
    * Greenlet Usage Notes: [https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#greenlet-usage](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#greenlet-usage)
* **FastAPI Dependencies:** [https://fastapi.tiangolo.com/tutorial/dependencies/](https://fastapi.tiangolo.com/tutorial/dependencies/)
* **FastMCP Documentation:** (Please consult the specific documentation for FastMCP regarding tool context, lifespan state access, and recommended patterns for managing resources like database sessions within tools).

---

### 6. Conclusion

The `greenlet_spawn has not been called` error strongly indicates that the `AsyncSession` used within the failing `update_document` MCP tool is operating in an `asyncio` context incompatible with SQLAlchemy's requirements. The primary path to resolution involves modifying the tool functions to acquire the `AsyncSession` via a mechanism integrated with FastMCP's execution context, likely leveraging a context object passed to the tool function and the `AsyncSessionFactory` stored during application lifespan startup. Verifying dependency versions and enhancing logging are important secondary steps. Implementing the session management strategy outlined in Recommendation 4.1 is the most likely solution.
