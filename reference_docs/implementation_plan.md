# Implementation Plan: MCP Server Web UI

**Project:** Python MCP Server with FastAPI Web UI for Maintenance

**Goal:** Build a web-based user interface using FastAPI and Jinja2 templates to allow viewing and basic management (Create, Update, Delete actions where applicable) of the Projects, Documents, and Memory Entries managed by the backend MCP server.

**Current Status (Summary):**

* **Backend:** Functionally complete. All core MCP tools and resources for Projects, Documents (including basic Versioning), Memory Entries (including Tagging), and Relationships (Linking/Unlinking) are implemented in `src/mcp_server_instance.py` using `FastMCP` and tested via MCP Inspector. Database models (`src/models.py`) and SQLAlchemy setup (`src/database.py`) are complete. Schema auto-creation via lifespan manager in `mcp_server_instance.py` is functional. Server runs in HTTP and STDIO modes (`src/main.py`).
* **Web UI (Basic):** FastAPI app configured in `src/main.py`. Jinja2 templates (`src/templates`) and static files (`src/static`) configured. Web routes defined in `src/web_routes.py` and included under `/ui` prefix in `main.py`. Base template (`base.html`), index page (`index.html` at `/ui/`), Projects List page (`projects.html` at `/ui/projects`), and Project Detail page (`project_detail.html` at `/ui/projects/{id}`) are implemented and functional, displaying data fetched via SQLAlchemy within the route handlers.

**Key Technologies & Patterns:**

* **Framework:** FastAPI (`fastapi`)
* **Templating:** Jinja2 (`jinja2`) via `FastAPI.state.templates`
* **Styling/JS:** Basic CSS/JS served via `StaticFiles` from `src/static`.
* **Backend Interaction:** Web UI route handlers will primarily interact with the backend by making **asynchronous HTTP POST requests** to the MCP message endpoint (`/mcp/messages/`) using the `httpx` library. This simulates an MCP client.
    * **Session ID:** A placeholder `session_id` (e.g., `"webapp-session"`) will need to be added as a query parameter to these `httpx` requests until a proper UI session/auth mechanism is decided upon.
    * **Data Fetching:** For displaying lists/details, UI routes can perform direct read-only database queries using SQLAlchemy sessions obtained via `Depends(get_db_session)`.
* **Forms:** Standard HTML forms using POST method. Data parsed in FastAPI using `fastapi.Form`.
* **Redirection:** Use `fastapi.responses.RedirectResponse` after successful POST actions.

**Required Dependencies:**

* `fastapi`, `uvicorn[standard]`, `jinja2`, `SQLAlchemy`, `aiosqlite`, `mcp[cli]`, `python-dotenv`, `pydantic-settings`, `sse-starlette`, `alembic` (Ensure these are in `requirements.txt`).
* **Add:** `httpx` (`pip install httpx`)

**Remaining Implementation Steps:**

**Phase 1: Complete Project Management UI**

1.  **Create Project Form (GET):**
    * **Goal:** Display form to create a new project.
    * **File:** `src/web_routes.py`
    * **Route:** `GET /ui/projects/new` (name: `ui_new_project`)
    * **Logic:** Render `project_form.html`, passing necessary context (e.g., form action URL `request.url_for('ui_create_project')`, field definitions, cancel URL `request.url_for('ui_list_projects')`).
    * **Template:** Create `src/templates/project_form.html` (inherits `base.html`). Include fields for Name (text, required), Path (text, required), Description (textarea, optional), Is Active (checkbox).
    * **Navigation:** Add link "Add New Project" from `projects.html` to `request.url_for('ui_new_project')`.

2.  **Create Project Handler (POST):**
    * **Goal:** Process form submission, call backend tool, redirect.
    * **File:** `src/web_routes.py`
    * **Route:** `POST /ui/projects` (name: `ui_create_project`)
    * **Logic:**
        * Accept form data using `fastapi.Form`.
        * Instantiate `httpx.AsyncClient`.
        * Construct JSON-RPC payload for `create_project` tool using form data.
        * `POST` payload to `http://127.0.0.1:PORT/mcp/messages/?session_id=webapp-session`.
        * Handle response: On success (check `result` key), extract new project ID and redirect (`RedirectResponse`) to `request.url_for('ui_view_project', project_id=new_id)`. On error (check `error` key), re-render `project_form.html` with an error message passed to context.

3.  **Edit Project Form (GET):**
    * **Goal:** Display form pre-filled with existing project data.
    * **File:** `src/web_routes.py`
    * **Route:** `GET /ui/projects/{project_id}/edit` (name: `ui_edit_project`)
    * **Logic:** Use `Depends(get_db_session)` to fetch the `Project` by `project_id`. Handle not found. Render `project_form.html`, passing the fetched project data to pre-fill form fields. Set form action URL to `request.url_for('ui_update_project', project_id=project_id)`.
    * **Template:** Adapt `project_form.html` to handle pre-filling values (e.g., `value="{{ data.project.name }}"`). Change title/button text.
    * **Navigation:** Add "Edit Project" link to `projects.html` (in table) and `project_detail.html`, pointing to `request.url_for('ui_edit_project', project_id=project.id)`.

4.  **Update Project Handler (POST):**
    * **Goal:** Process edit form submission, call backend tool, redirect.
    * **File:** `src/web_routes.py`
    * **Route:** `POST /ui/projects/{project_id}/edit` (name: `ui_update_project`)
    * **Logic:**
        * Accept `project_id` from path and form data.
        * Use `httpx` to call the `update_project` MCP tool, passing `project_id` and any non-empty/changed form fields as parameters.
        * Handle response: On success, redirect to `request.url_for('ui_view_project', project_id=project_id)`. On error, re-render `project_form.html` with error.

5.  **Delete Project Handler (POST):**
    * **Goal:** Call backend delete tool, redirect to list.
    * **File:** `src/web_routes.py`
    * **Route:** `POST /ui/projects/{project_id}/delete` (name: `ui_delete_project`)
    * **Logic:** Use `httpx` to call the `delete_project` MCP tool with `project_id`. Handle potential errors from the tool call. Redirect to `request.url_for('ui_list_projects')`.
    * **Template:** Add a "Delete" button within a small `<form method="post">` on `projects.html` (in table) and `project_detail.html`. *Strongly recommend adding JavaScript `confirm()` dialog before form submission.*

6.  **Set Active Project Handler (POST):**
    * **Goal:** Call backend activate tool, redirect.
    * **File:** `src/web_routes.py`
    * **Route:** `POST /ui/projects/{project_id}/activate` (name: `ui_activate_project`)
    * **Logic:** Use `httpx` to call `set_active_project` tool. Redirect back to the referring page (project list or detail) or always to project list.
    * **Template:** Add "Activate" button/form to `projects.html` and `project_detail.html` (potentially only show if `project.is_active == False`). Visually indicate the active project on the list page (e.g., bold text, icon).

**Phase 2: Implement Document Management UI**

* (Structure mirrors Phase 1, operating on Documents and linking primarily from Project Detail page)
1.  **List Documents:** Enhance Project Detail page or create dedicated `/ui/documents` page (TBD based on preference). Fetch using direct DB access or `list_documents_for_project` tool.
2.  **Document Detail Page (`GET /ui/documents/{doc_id}`):** Create route (`ui_view_document`) and template (`document_detail.html`). Fetch Document via DB. Call MCP tools (`list_document_versions`, `list_tags_for_document`) via `httpx` to get related data. Display all info.
3.  **Add Document:** Create Form (`document_form.html`) and GET/POST routes (`ui_new_document`, `ui_create_document`) probably linked from Project Detail (`/ui/projects/{proj_id}/documents/new`). POST handler calls `add_document` tool via `httpx`. Redirect.
4.  **Edit Document:** Form (`document_form.html`), GET/POST routes (`ui_edit_document`, `ui_update_document` at `/ui/documents/{id}/edit`). POST handler calls `update_document` tool via `httpx`. Redirect.
5.  **Delete Document:** POST route (`ui_delete_document` at `/ui/documents/{id}/delete`). Handler calls `delete_document` tool via `httpx`. Redirect. Add button/form to UI.
6.  **Tag Management:** On `document_detail.html`, add form/buttons to call `add_tag_to_document` / `remove_tag_from_document` tools (via dedicated POST routes and `httpx`). Display tags fetched via `list_tags_for_document`.
7.  **Version Management:** On `document_detail.html`, display version list fetched via `list_document_versions` tool. Add links/buttons to view specific version content (e.g., link to `/ui/versions/{version_id}` page which calls `get_document_version_content` tool). Create version detail route/template if needed.

**Phase 3: Implement Memory Entry Management UI**

* (Structure mirrors Phase 2, operating on Memory Entries)
1.  **List/Detail Pages:** (`/ui/memory`, `/ui/memory/{id}`). Fetch data, call tools (`list_memory_entries`, `get_memory_entry`, `list_tags...`, `list_related...`). Create templates (`memory_entries.html`, `memory_detail.html`). Add navigation links.
2.  **Add/Edit/Delete:** Forms (`memory_form.html`), GET/POST routes. Call respective tools (`add/update/delete_memory_entry`) via `httpx`. Add UI links/buttons.
3.  **Tag Management:** UI on detail page. Call tag tools via `httpx`.
4.  **Relationship Management:** UI on detail page to link/unlink. Call relationship tools via `httpx`.

**Phase 4: Styling and Refinements**

1.  **CSS:** Implement basic styling in `src/static/style.css`.
2.  **JavaScript:** Add JS for confirmations (delete), potential AJAX interactions, etc.
3.  **Error Handling:** Improve display of errors returned from backend calls in UI templates.
4.  **User Feedback:** Implement flash messages (requires session middleware like `starlette-session`) for better user feedback after actions.
5.  **Refactor:** Clean up code, potentially abstract form generation or common UI patterns.

**End Goal:** A functional web interface allowing users to view Projects, Documents, and Memory Entries, see their relationships and tags, and perform basic Create, Update, Delete operations via forms that interact with the backend MCP server tools.
