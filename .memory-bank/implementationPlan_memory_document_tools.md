# Implementation Plan: Fixing Async Generator Usage in Memory and Document MCP Tools

## Objective
Update all remaining MCP tools in `src/mcp_memory_tools.py` and `src/mcp_document_tools.py` to remove the `ctx` parameter and replace session management to use the async context manager `get_session_from_factory` that correctly consumes the `get_db_session` async generator.

## Background
- The `get_db_session` function is an async generator yielding an `AsyncSession`.
- Using `async with get_db_session()` causes runtime errors because async generators do not support the async context manager protocol.
- The project tools were fixed by creating `get_session_from_factory` which uses `async for` to consume `get_db_session` and yields the session.
- All project tools were updated to use `async with get_session_from_factory()` for session management.
- Pylance static type checker shows false positives on async context manager methods; these are suppressed with comments.

## Step-by-Step Implementation

### 1. Remove `ctx` Parameter
- For each MCP tool function in `src/mcp_memory_tools.py` and `src/mcp_document_tools.py`, remove the `ctx` parameter from the function signature.
- Adjust any internal usage accordingly.

### 2. Replace Session Acquisition
- Replace all occurrences of:
  ```python
  session = await get_session(ctx)
  ```
  or
  ```python
  async with get_db_session() as session:
  ```
  with:
  ```python
  async with get_session_from_factory() as session:
  ```
- Ensure `get_session_from_factory` is defined as:
  ```python
  @asynccontextmanager
  async def get_session_from_factory():
      async for session in get_db_session():
          yield session
  ```

### 3. Add Suppression Comments
- Add the following at the top of both `src/mcp_memory_tools.py` and `src/mcp_document_tools.py` to suppress Pylance false positives:
  ```
  # pyright: reportMissingTypeStubs=false
  # pyright: reportUnknownMemberType=false
  ```

### 4. Test Each Tool
- After updating each tool, test it manually or via automated tests to confirm the async generator usage error is resolved.
- Proceed to the next tool only after confirming the previous one works correctly.

## Known Issues and Resolutions
- Static type checkers may report false positives on async context manager support for `AsyncSession`. These are suppressed with comments.
- Duplicate declarations of `get_session_from_factory` must be avoided to prevent function declaration obscured errors.
- Consistent use of `get_session_from_factory` across all tools ensures uniform session management and error handling.

## Documentation
- Update the Memory Bank with this implementation plan.
- Reference this plan in the active context for future work.

Please proceed with this plan to systematically fix the memory and document MCP tools.
