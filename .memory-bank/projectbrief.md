# Project Summary: MCP Server with FastAPI Web UI

## 1. Goal
The primary goal of this project is to create a Python-based server application that manages Projects, Documents, and Memory Entries, and exposes this data/functionality through two interfaces:
* An MCP (Model Context Protocol) compliant server endpoint for programmatic access (e.g., by LLMs or other tools).
* A human-usable Web UI for viewing and performing basic CRUD (Create, Read, Update, Delete) and management operations on the data.

## 2. Core Technologies
* **Language:** Python 3
* **Web Framework:** FastAPI (used for both the Web UI and mounting the MCP server)
* **MCP Server:** `mcp` library, specifically `FastMCP` for defining MCP tools and resources.
* **Database:** SQLAlchemy 2.0 (async ORM) with an SQLite backend. Foreign key enforcement is enabled via `PRAGMA foreign_keys=ON` configured in `src/database.py`.
* **Templating:** Jinja2 (via FastAPI's `Jinja2Templates`) for rendering the Web UI HTML pages.
* **Serving:** Uvicorn ASGI server.

## 3. Project Structure (Key Files in `src/`)
* `main.py`: Main application entry point. Sets up the FastAPI app, mounts static files, includes the Web UI router under `/ui`, mounts the FastMCP SSE application under `/mcp`, and starts the Uvicorn server. Supports running in HTTP or STDIO mode.
* `mcp_server_core.py`: Defines the `FastMCP` instance, application lifespan management (including database initialization), and helper functions to obtain database sessions for MCP tools.
* `mcp_project_tools.py`: Defines MCP tools related to Project management, including create, read, update, delete, and set active project operations. These tools use async helper functions for database interactions.
* `mcp_server.py`: Contains additional MCP tool definitions; currently includes a placeholder tool for handling messages from MCP clients.
* `web_routes.py`: Aggregates FastAPI routers for the Web UI, including project, document, memory, and root routes, all mounted under the `/ui` prefix.
* `project_routes.py`, `document_routes.py`, `memory_routes.py`, `root_routes.py`: Define FastAPI route handlers for the Web UI, handling display pages and form submissions for Projects, Documents (including versions and tags), Memory Entries (including tags and relations), and root-level routes respectively.
* `models.py`: Defines SQLAlchemy ORM models for the core entities: `Project`, `Document`, `DocumentVersion`, `MemoryEntry`, `MemoryEntryRelation`, and `Tag`, including association tables and relationships.
* `database.py`: Configures the asynchronous SQLAlchemy engine and session factory, including SQLite foreign key enforcement via PRAGMA.
* `mcp_db_helpers_project.py`, `mcp_db_helpers_document.py`, `mcp_db_helpers_memory.py`, `mcp_db_helpers_relations.py`, `mcp_db_helpers_tags.py`, `mcp_db_helpers.py`: Contain async helper functions encapsulating database CRUD operations and business logic for Projects, Documents, Memory Entries, relations, and tags.
* `config.py`: Contains application settings such as database URL, server host/port, logging level, and MCP transport mode.
* `templates/`: Contains Jinja2 HTML templates for rendering the Web UI pages, including forms and detail views for Projects, Documents, Memory Entries, and versions.
* `static/`: Contains static assets such as CSS files.

## 4. MCP Server Component (`/mcp` endpoint)
* The MCP server is implemented using the `FastMCP` library, instantiated in `mcp_server_core.py`.
* The MCP server exposes tools primarily defined in `mcp_project_tools.py` for Project management:
  - `list_projects`
  - `create_project`
  - `get_project`
  - `update_project`
  - `delete_project`
  - `set_active_project`
* Additional MCP tools can be defined in `mcp_server.py` and other modules as needed.
* Communication with MCP clients occurs over Server-Sent Events (SSE) via the application mounted at `/mcp` in `main.py`.
* MCP clients connect to this SSE endpoint, receive a unique session ID, and use that ID to make POST requests containing JSON-RPC calls to execute MCP tools.
* Resources such as documents or memory entries are not currently exposed as MCP resources.
* **To-do:** Add MCP tools for managing Documents, Document Versions, Memory Entries, Tags, and Relations to achieve feature parity with the Web UI.

## 5. Web UI Frontend Component (`/ui` endpoint)
* The Web UI is implemented as a set of FastAPI routes aggregated in `web_routes.py` and mounted under the `/ui` prefix.
* Routes are modularized into:
  - `project_routes.py`: Handles listing, creating, viewing, editing, deleting, and activating Projects.
  - `document_routes.py`: Handles listing documents, viewing document details, creating/editing/deleting documents, managing document versions and tags.
  - `memory_routes.py`: Handles listing memory entries, viewing details, creating/editing/deleting entries, and managing tags and relations.
  - `root_routes.py`: Handles root-level or miscellaneous routes.
* The Web UI uses Jinja2 templates located in `src/templates/` to render HTML pages.
* Static assets such as CSS are served from `src/static/`.
* The Web UI route handlers obtain database sessions via FastAPI dependency injection (`Depends(get_db_session)`).
* The Web UI directly calls async helper functions (e.g., in `mcp_db_helpers_project.py`) for database operations, sharing logic with MCP tools.

## 6. Interaction Pattern (Web UI <-> Backend Logic)
* The Web UI does not communicate with the MCP server over the SSE endpoint internally.
* Instead, Web UI route handlers directly invoke the same async helper functions used by MCP tools for database CRUD operations.
* Database sessions are obtained via FastAPI dependency injection in the Web UI routes, and via the lifespan context in MCP tools.
* This design simplifies development by avoiding internal SSE client connections and ensures consistent business logic across interfaces.
* The Web UI supports full CRUD and management operations for Projects, Documents (including versions and tags), and Memory Entries (including tags and relations).
* The MCP server currently exposes only Project management tools, lacking tools for Documents and Memory Entries.

---
This updated summary reflects the current architecture, components, and data flow of the project based on the latest `/src` directory contents.
