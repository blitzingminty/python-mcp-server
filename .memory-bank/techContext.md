# Technical Context

This file details the technologies used, development setup, technical constraints, dependencies, and tool usage patterns.

## Technologies Used
- Python 3.13.3
- FastAPI for web framework and MCP server integration
- SQLAlchemy 2.0 Async ORM with SQLite backend
- Jinja2 templating for Web UI
- Uvicorn ASGI server
- MCP protocol libraries for tool and resource management

## Development Setup
- Async database session management using SQLAlchemy async API
- Use of async generators for database session lifecycle
- MCP tools implemented as async functions without `ctx` parameter
- Use of async context managers to handle database sessions in MCP tools
- Use `uv pip` command for package management instead of `pip`

## Technical Constraints
- SQLite database with foreign key enforcement via PRAGMA
- Static type checking challenges with SQLAlchemy async API
- Pylance false positives on async context manager support for AsyncSession
- Need to suppress or work around type hinting limitations

## Dependencies
- SQLAlchemy async packages
- FastAPI and related ASGI components
- MCP server libraries
- Python typing extensions for async generators and context managers

## Tool Usage Patterns
- Async generators for database session provision
- Async context managers wrapping async generators for session management
- MCP tools consuming sessions via async context managers
- Explicit type hints and suppression comments to aid static analysis
