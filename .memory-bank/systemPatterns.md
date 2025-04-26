# System Patterns

## Async Database Session Management Pattern

- The project uses SQLAlchemy's asynchronous API for database interactions.
- Database sessions are managed using an async generator function `get_db_session()` which yields an `AsyncSession` instance.
- This async generator must be consumed using `async for` to correctly handle the session lifecycle.
- A dedicated async context manager `get_session_from_factory` wraps `get_db_session()` and yields the session for use in MCP tools.
- MCP tools use `async with get_session_from_factory()` to obtain a database session for their operations.
- This pattern ensures proper opening and closing of sessions, including rollback on exceptions.

## Common Pitfalls and Resolutions

- Attempting to `await` the async generator `get_db_session()` directly causes errors like "object async_generator can't be used in 'await' expression".
- The correct approach is to use `async for` to iterate over the async generator.
- Static type checkers (e.g., Pylance) may show false positives about missing async context manager methods on `AsyncSession`.
- Suppression comments and explicit type hints are used to reduce false positives.
- This pattern and its caveats are documented to guide future development and troubleshooting.
