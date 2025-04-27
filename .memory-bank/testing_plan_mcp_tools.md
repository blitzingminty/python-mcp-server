# Testing Plan for MCP-Session-Context-Remote Tools

This document outlines a comprehensive testing plan for all tools available in the `mcp-session-context-remote` MCP server. The goal is to thoroughly test each tool's functionality, including typical use cases, edge cases, and error handling.

---

## 1. Memory Entry Tools

### 1.1 list_memory
- **Purpose:** Retrieve a list of memory entries for a given project.
- **Test Cases:**
  - List memory entries for a valid project with existing entries.
  - List memory entries for a valid project with no entries (expect empty list).
  - List memory entries for an invalid/non-existent project (expect error or empty list).
  - List memory entries with missing project_id parameter (expect error).
- **Testing Instructions:**
  - Use `use_mcp_tool` with `tool_name` set to `"list_memory"` and provide `project_id` as argument.
  - Verify the returned list matches expected entries or is empty as appropriate.
  - Test with invalid or missing `project_id` to confirm error handling.

### 1.2 create_memory
- **Purpose:** Create a new memory entry.
- **Test Cases:**
  - Create memory entry with valid project_id, title, type, and content.
  - Create memory entry with missing required fields (expect error).
  - Create memory entry with very large content.
  - Create memory entry with special characters in title and content.
- **Testing Instructions:**
  - Use `use_mcp_tool` with `tool_name` set to `"create_memory"` and provide required arguments.
  - Verify the response contains the created memory entry with correct fields.
  - Test with missing or invalid fields to confirm error handling.

### 1.3 get_memory
- **Purpose:** Retrieve details of a specific memory entry by ID.
- **Test Cases:**
  - Get memory entry with valid memory_id.
  - Get memory entry with invalid/non-existent memory_id (expect error).
  - Get memory entry with missing memory_id parameter (expect error).

### 1.4 update_memory
- **Purpose:** Update an existing memory entry.
- **Test Cases:**
  - Update title, type, and content of an existing memory entry.
  - Update with partial fields (e.g., only title).
  - Update with invalid memory_id (expect error).
  - Update with no changes (expect no error).

### 1.5 delete_memory
- **Purpose:** Delete a memory entry.
- **Test Cases:**
  - Delete existing memory entry.
  - Delete non-existent memory entry (expect error).
  - Delete with missing memory_id parameter (expect error).

### 1.6 add_tag_to_memory_entry
- **Purpose:** Add a tag to a memory entry.
- **Test Cases:**
  - Add a new tag to an existing memory entry.
  - Add an existing tag again (expect idempotent or error).
  - Add tag with invalid memory_id or tag_name (expect error).

### 1.7 remove_tag_from_memory_entry
- **Purpose:** Remove a tag from a memory entry.
- **Test Cases:**
  - Remove an existing tag from a memory entry.
  - Remove a non-existent tag (expect idempotent or error).
  - Remove tag with invalid memory_id or tag_name (expect error).

### 1.8 add_memory_relation
- **Purpose:** Add a relation between two memory entries.
- **Test Cases:**
  - Add relation with valid source and target memory entry IDs.
  - Add relation with invalid memory entry IDs (expect error).
  - Add relation with missing parameters (expect error).

### 1.9 remove_memory_relation
- **Purpose:** Remove a relation between two memory entries.
- **Test Cases:**
  - Remove existing relation by relation_id.
  - Remove non-existent relation (expect error).
  - Remove relation with missing relation_id (expect error).

---

## 2. Document Tools

### 2.1 list_documents
- **Purpose:** List documents optionally filtered by project_id.
- **Test Cases:**
  - List documents for a valid project with documents.
  - List documents for a valid project with no documents (expect empty list).
  - List documents with no project_id (list all documents).
  - List documents with invalid project_id (expect error or empty list).

### 2.2 create_document
- **Purpose:** Create a new document.
- **Test Cases:**
  - Create document with valid project_id, name, path, content, and type.
  - Create document with missing required fields (expect error).
  - Create document with large content.
  - Create document with special characters in name and path.

### 2.3 get_document
- **Purpose:** Retrieve document details by document_id.
- **Test Cases:**
  - Get document with valid document_id.
  - Get document with invalid/non-existent document_id (expect error).
  - Get document with missing document_id (expect error).

### 2.4 update_document
- **Purpose:** Update document metadata.
- **Test Cases:**
  - Update name, path, and type of an existing document.
  - Update with partial fields.
  - Update with invalid document_id (expect error).
  - Update with no changes.

### 2.5 delete_document
- **Purpose:** Delete a document.
- **Test Cases:**
  - Delete existing document.
  - Delete non-existent document (expect error).
  - Delete with missing document_id (expect error).

### 2.6 add_document_tag
- **Purpose:** Add a tag to a document.
- **Test Cases:**
  - Add new tag to document.
  - Add existing tag again (idempotent or error).
  - Add tag with invalid document_id or tag_name.

### 2.7 remove_document_tag
- **Purpose:** Remove a tag from a document.
- **Test Cases:**
  - Remove existing tag.
  - Remove non-existent tag.
  - Remove tag with invalid document_id or tag_name.

### 2.8 list_document_versions
- **Purpose:** List versions of a document.
- **Test Cases:**
  - List versions for a valid document with versions.
  - List versions for a document with no versions.
  - List versions with invalid document_id.

### 2.9 get_document_version
- **Purpose:** Get content of a specific document version.
- **Test Cases:**
  - Get version with valid version_id.
  - Get version with invalid version_id.
  - Get version with missing version_id.

### 2.10 create_document_version
- **Purpose:** Create a new version for a document.
- **Test Cases:**
  - Create version with valid document_id, content, and version_string.
  - Create version with missing fields.
  - Create version with large content.

### 2.11 delete_document_version
- **Purpose:** Delete a document version.
- **Test Cases:**
  - Delete existing version.
  - Delete non-existent version.
  - Delete with missing version_id.

---

## 3. Project Tools

### 3.1 list_projects
- **Purpose:** List all projects.
- **Test Cases:**
  - List projects when projects exist.
  - List projects when no projects exist.

### 3.2 create_project
- **Purpose:** Create a new project.
- **Test Cases:**
  - Create project with valid name, description, path, and is_active.
  - Create project with missing required fields.
  - Create project with special characters in name and description.

### 3.3 get_project
- **Purpose:** Get project details by project_id.
- **Test Cases:**
  - Get project with valid project_id.
  - Get project with invalid project_id.
  - Get project with missing project_id.

### 3.4 update_project
- **Purpose:** Update project name and description.
- **Test Cases:**
  - Update project with valid project_id.
  - Update with partial fields.
  - Update with invalid project_id.
  - Update with no changes.

### 3.5 delete_project
- **Purpose:** Delete a project.
- **Test Cases:**
  - Delete existing project.
  - Delete non-existent project.
  - Delete with missing project_id.

### 3.6 set_active_project
- **Purpose:** Set a project as active.
- **Test Cases:**
  - Set active project with valid project_id.
  - Set active project with invalid project_id.
  - Set active project with missing project_id.

---

## Notes
- For all tools, test error handling for invalid inputs and missing required parameters.
- Test concurrency and race conditions where applicable.
- Test authorization and permissions if applicable (not specified here).
- Test performance with large data inputs.

---

This testing plan should be reviewed and then implemented as automated tests or manual test cases as appropriate.

---

## Test Results Summary

### Memory Entry Tools
- Creation of memory entries sometimes returns success but subsequent retrieval fails with "not found" errors.
- Listing memory entries returns empty even after creation attempts.
- Tagging and relation tools were not fully tested due to creation issues.
- Indicates potential issues with memory entry persistence or retrieval.

### Document Tools
- Document creation succeeded with existing projects; initial failures with newly created projects.
- Document retrieval, tagging, version listing, and deletion operations functioned correctly.
- Document update tool triggered an async context error during testing.
- Overall, document tools are mostly stable with minor issues.

### Project Tools
- Project creation succeeded but retrieval of newly created projects failed (returned null).
- Project update and set active operations returned null or unexpected results for new projects.
- Project deletion and listing operations worked as expected.
- Existing projects behaved correctly during tests.
- Indicates potential issues with project persistence or retrieval for new entries.

### General Observations
- Some inconsistencies with newly created entities not being immediately accessible.
- Existing entities behave as expected.
- Async context management errors observed in some update operations.
- Further investigation recommended for creation, retrieval, and async handling issues.

---

## Investigation Summary: Boolean Parameter Validation Issue

### Background
- The `create_project` MCP tool expects an `is_active` boolean parameter.
- Tests showed validation errors indicating the input was not recognized as a valid boolean.
- The Web UI handles `is_active` correctly, likely due to FastAPI's form data parsing and type coercion.

### Findings
- The MCP framework uses Pydantic models to generate input schemas from tool function signatures.
- Boolean parameters require strict typing as `bool`.
- Incoming MCP tool calls may provide parameters as strings or nulls, which Pydantic does not automatically coerce to boolean.
- This mismatch causes validation errors during MCP tool invocation.

### Comparison with Web UI
- Web UI form submissions convert `is_active` to a proper boolean before passing to the helper functions.
- MCP tool calls may lack this conversion, leading to validation failures.

### Potential Solutions
- Implement input coercion or validation in MCP tool handlers to convert string or null inputs to boolean.
- Adjust MCP client calls to ensure boolean parameters are passed as actual booleans.
- Add explicit Pydantic validators or custom input models for MCP tools to handle type coercion.

### Next Steps
- Discuss and decide on the preferred approach to fix the boolean parameter handling.
- Implement the fix and update tests accordingly.
- Verify that the fix resolves the validation errors without impacting other functionality.

This summary provides a clear understanding of the issue and guides the next steps for resolution.


### Error when creating a new project

Error executing tool create_project: 1 validation error for create_projectArguments
is_active
  Input should be a valid boolean [type=bool_type, input_value=None, input_type=NoneType]
    For further information visit https://errors.pydantic.dev/2.11/v/bool_type
