import asyncio
import pytest

from mcp_session_context_remote import use_mcp_tool

@pytest.mark.asyncio
async def test_memory_tools():
    # Create a project to associate memory entries with
    projects_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="list_projects",
        arguments={}
    )
    projects = projects_response.get("result", [])
    if not projects:
        project_response = await use_mcp_tool(
            server_name="mcp-session-context-remote",
            tool_name="create_project",
            arguments={
                "name": "Test Project",
                "description": "Test Desc",
                "path": "/tmp",
                "is_active": True
            }
        )
        project = project_response.get("result")
        project_id = project["id"]
    else:
        project_id = projects[0]["id"]

    # Test create_memory
    mem_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="create_memory",
        arguments={
            "project_id": project_id,
            "title": "Test Memory",
            "type": "test",
            "content": "Test content"
        }
    )
    mem = mem_response.get("result")
    mem_id = mem["id"]

    # Test get_memory
    mem_get_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_memory",
        arguments={"memory_id": mem_id}
    )
    mem_get = mem_get_response.get("result")
    assert mem_get["title"] == "Test Memory"

    # Test update_memory
    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="update_memory",
        arguments={"memory_id": mem_id, "title": "Updated Title", "type": None, "content": None}
    )
    mem_updated_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_memory",
        arguments={"memory_id": mem_id}
    )
    mem_updated = mem_updated_response.get("result")
    assert mem_updated["title"] == "Updated Title"

    # Test add_tag_to_memory_entry
    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="add_tag_to_memory_entry",
        arguments={"memory_id": mem_id, "tag_name": "tag1"}
    )
    # Test remove_tag_from_memory_entry
    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="remove_tag_from_memory_entry",
        arguments={"memory_id": mem_id, "tag_name": "tag1"}
    )

    # Test delete_memory
    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="delete_memory",
        arguments={"memory_id": mem_id}
    )

@pytest.mark.asyncio
async def test_document_tools():
    projects_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="list_projects",
        arguments={}
    )
    projects = projects_response.get("result", [])
    if not projects:
        project_response = await use_mcp_tool(
            server_name="mcp-session-context-remote",
            tool_name="create_project",
            arguments={
                "name": "Doc Test Project",
                "description": "Doc Test Desc",
                "path": "/tmp",
                "is_active": True
            }
        )
        project = project_response.get("result")
        project_id = project["id"]
    else:
        project_id = projects[0]["id"]

    doc_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="create_document",
        arguments={
            "project_id": project_id,
            "name": "Test Doc",
            "path": "test/path",
            "content": "Doc content",
            "type": "text"
        }
    )
    doc = doc_response.get("result")
    doc_id = doc["id"]

    doc_get_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_document",
        arguments={"document_id": doc_id}
    )
    doc_get = doc_get_response.get("result")
    assert doc_get["name"] == "Test Doc"

    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="update_document",
        arguments={"document_id": doc_id, "name": "Updated Doc", "path": None, "type": None}
    )
    doc_updated_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_document",
        arguments={"document_id": doc_id}
    )
    doc_updated = doc_updated_response.get("result")
    assert doc_updated["name"] == "Updated Doc"

    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="add_document_tag",
        arguments={"document_id": doc_id, "tag_name": "tag1"}
    )
    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="remove_document_tag",
        arguments={"document_id": doc_id, "tag_name": "tag1"}
    )

    versions_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="list_document_versions",
        arguments={"document_id": doc_id}
    )
    versions = versions_response.get("result", [])

    version_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="create_document_version",
        arguments={"document_id": doc_id, "content": "Version content", "version_string": "v1.0"}
    )
    version = version_response.get("result")
    version_id = version["id"]

    version_get_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_document_version",
        arguments={"version_id": version_id}
    )
    version_get = version_get_response.get("result")
    assert version_get["content"] == "Version content"

    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="delete_document_version",
        arguments={"version_id": version_id}
    )
    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="delete_document",
        arguments={"document_id": doc_id}
    )

@pytest.mark.asyncio
async def test_project_tools():
    projects_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="list_projects",
        arguments={}
    )
    projects = projects_response.get("result", [])
    initial_count = len(projects)

    project_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="create_project",
        arguments={"name": "New Project", "description": "Desc", "path": "/tmp", "is_active": False}
    )
    project = project_response.get("result")
    project_id = project["id"]

    proj_get_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_project",
        arguments={"project_id": project_id}
    )
    proj_get = proj_get_response.get("result")
    assert proj_get["name"] == "New Project"

    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="update_project",
        arguments={"project_id": project_id, "name": "Updated Project", "description": "Updated Desc"}
    )
    proj_updated_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="get_project",
        arguments={"project_id": project_id}
    )
    proj_updated = proj_updated_response.get("result")
    assert proj_updated["name"] == "Updated Project"

    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="set_active_project",
        arguments={"project_id": project_id}
    )
    # Optionally verify active project status if API supports it

    await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="delete_project",
        arguments={"project_id": project_id}
    )

    projects_after_response = await use_mcp_tool(
        server_name="mcp-session-context-remote",
        tool_name="list_projects",
        arguments={}
    )
    projects_after = projects_after_response.get("result", [])
    assert len(projects_after) == initial_count

# Note: This test file uses the use_mcp_tool function to call tools on the mcp-session-context-remote MCP server.
# Adjust the test code as needed to match the actual MCP client API and response formats.
