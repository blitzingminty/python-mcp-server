# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

import logging
from src.mcp_server_core import mcp_instance
from typing import Any, Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from src.mcp_db_helpers_document import list_documents_in_db
from src.database import get_db_session

@asynccontextmanager
async def get_session_from_factory():
    async for session in get_db_session():
        yield session

@mcp_instance.tool(name="list_documents", description="List all documents")
async def list_documents(project_id: int | None = None):
    """
    List all documents, optionally filtered by project ID.
    """
    logger.info(f"MCP Tool 'list_documents' called for project_id: {project_id}.")
    async with get_session_from_factory() as session:
        documents = await list_documents_in_db(session, project_id=project_id)
        # Convert Document objects to dictionaries for JSON serialization
        document_list = []
        for doc in documents:
            document_list.append({
                "id": doc.id,
                "project_id": doc.project_id,
                "name": doc.name,
                "path": doc.path,
                "type": doc.type,
                "version": doc.version,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
                "tags": [tag.name for tag in doc.tags]
            })
        logger.info(f"MCP Tool 'list_documents' returning {len(document_list)} documents.")
        return {"documents": document_list}

from src.mcp_db_helpers_document import add_document_in_db

@mcp_instance.tool(name="create_document", description="Create a new document")
async def create_document(project_id: int, name: str, path: str, content: str, type: str, version: str = "1.0.0"):
    """
    Create a new document in a specified project.
    """
    logger.info(f"MCP Tool 'create_document' called for project_id: {project_id}, name: {name}.")
    async with get_session_from_factory() as session:
        document = await add_document_in_db(session, project_id=project_id, name=name, path=path, content=content, type=type, version=version)
        if document:
            logger.info(f"MCP Tool 'create_document' successfully created document ID: {document.id}.")
            return {
                "status": "created",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags]
                }
            }
        else:
            logger.error(f"MCP Tool 'create_document' failed to create document for project_id: {project_id}, name: {name}.")
            return {"status": "error", "message": "Failed to create document"}

from src.mcp_db_helpers_document import get_document_in_db

@mcp_instance.tool(name="get_document", description="Retrieve details for a document")
async def get_document(document_id: int):
    """
    Retrieve details for a single document by ID.
    """
    logger.info(f"MCP Tool 'get_document' called for document_id: {document_id}.")
    async with get_session_from_factory() as session:
        document = await get_document_in_db(session, document_id=document_id)
        if document:
            logger.info(f"MCP Tool 'get_document' found document ID: {document_id}.")
            return {
                "status": "success",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "content": document.content,  # Include content for get
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags],
                    "versions": [{"id": v.id, "version": v.version, "created_at": v.created_at.isoformat()} for v in document.versions]
                }
            }
        else:
            logger.warning(f"MCP Tool 'get_document' document ID {document_id} not found.")
            return {"status": "error", "message": f"Document ID {document_id} not found."}

from src.mcp_db_helpers_document import update_document_in_db

@mcp_instance.tool(name="update_document", description="Update an existing document")
async def update_document(document_id: int, name: str | None = None, path: str | None = None, type: str | None = None):
    """
    Update metadata for an existing document.
    """
    logger.info(f"MCP Tool 'update_document' called for document_id: {document_id} with data: name={name}, path={path}, type={type}.")
    async with get_session_from_factory() as session:
        document = await update_document_in_db(session, document_id=document_id, name=name, path=path, type=type)
        if document:
            logger.info(f"MCP Tool 'update_document' successfully updated document ID: {document_id}.")
            return {
                "status": "updated",
                "document": {
                    "id": document.id,
                    "project_id": document.project_id,
                    "name": document.name,
                    "path": document.path,
                    "type": document.type,
                    "version": document.version,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                    "tags": [tag.name for tag in document.tags]
                }
            }
        else:
            logger.warning(f"MCP Tool 'update_document' document ID {document_id} not found or no changes made.")
            return {"status": "error", "message": f"Document ID {document_id} not found or no changes made."}

from src.mcp_db_helpers_document import delete_document_in_db

@mcp_instance.tool(name="delete_document", description="Delete a document")
async def delete_document(document_id: int):
    """
    Delete a document by ID.
    """
    logger.info(f"MCP Tool 'delete_document' called for document_id: {document_id}.")
    async with get_session_from_factory() as session:
        success = await delete_document_in_db(session, document_id=document_id)
        if success:
            logger.info(f"MCP Tool 'delete_document' successfully deleted document ID: {document_id}.")
            return {"status": "deleted", "document_id": document_id}
        else:
            logger.error(f"MCP Tool 'delete_document' failed to delete document ID: {document_id}.")
            return {"status": "error", "message": f"Failed to delete document ID {document_id}."}

from src.mcp_db_helpers_document import add_tag_to_document_db, remove_tag_from_document_db

@mcp_instance.tool(name="add_document_tag", description="Add a tag to a document")
async def add_document_tag(document_id: int, tag_name: str):
    """
    Add a tag to a document.
    """
    logger.info(f"MCP Tool 'add_document_tag' called for document_id: {document_id}, tag_name: {tag_name}.")
    async with get_session_from_factory() as session:
        success = await add_tag_to_document_db(session, document_id=document_id, tag_name=tag_name)
        if success:
            logger.info(f"MCP Tool 'add_document_tag' successfully added tag '{tag_name}' to document ID: {document_id}.")
            return {"status": "tag added", "document_id": document_id, "tag_name": tag_name}
        else:
            logger.error(f"MCP Tool 'add_document_tag' failed to add tag '{tag_name}' to document ID: {document_id}.")
            return {"status": "error", "message": f"Failed to add tag '{tag_name}' to document ID {document_id}."}

from src.mcp_db_helpers_document import remove_tag_from_document_db

@mcp_instance.tool(name="remove_document_tag", description="Remove a tag from a document")
async def remove_document_tag(document_id: int, tag_name: str):
    """
    Remove a tag from a document.
    """
    logger.info(f"MCP Tool 'remove_document_tag' called for document_id: {document_id}, tag_name: {tag_name}.")
    async with get_session_from_factory() as session:
        success = await remove_tag_from_document_db(session, document_id=document_id, tag_name=tag_name)
        if success:
            logger.info(f"MCP Tool 'remove_document_tag' successfully removed tag '{tag_name}' from document ID: {document_id}.")
            return {"status": "tag removed", "document_id": document_id, "tag_name": tag_name}
        else:
            logger.error(f"MCP Tool 'remove_document_tag' failed to remove tag '{tag_name}' from document ID: {document_id}.")
        return {"status": "error", "message": f"Failed to remove tag '{tag_name}' from document ID {document_id}."}

from src.mcp_db_helpers_document import get_document_version_content_db, add_document_version_db, delete_document_version_db

@mcp_instance.tool(name="list_document_versions", description="List versions for a document")
async def list_document_versions(document_id: int):
    """
    List all versions for a single document by ID.
    """
    logger.info(f"MCP Tool 'list_document_versions' called for document_id: {document_id}.")
    async with get_session_from_factory() as session:
        document = await get_document_in_db(session, document_id=document_id)
        if document:
            version_list = []
            for v in document.versions:
                version_list.append({"id": v.id, "version": v.version, "created_at": v.created_at.isoformat()})
            logger.info(f"MCP Tool 'list_document_versions' found {len(version_list)} versions for document ID: {document_id}.")
            return {"status": "success", "document_id": document_id, "versions": version_list}
        else:
            logger.warning(f"MCP Tool 'list_document_versions' document ID {document_id} not found.")
        return {"status": "error", "message": f"Document ID {document_id} not found."}

from src.mcp_db_helpers_document import get_document_version_content_db

@mcp_instance.tool(name="get_document_version", description="Get content for a specific document version")
async def get_document_version(version_id: int):
    """
    Retrieve content for a single document version by ID.
    """
    logger.info(f"MCP Tool 'get_document_version' called for version_id: {version_id}.")
    async with get_session_from_factory() as session:
        version = await get_document_version_content_db(session, version_id=version_id)
        if version:
            logger.info(f"MCP Tool 'get_document_version' found version ID: {version_id}.")
            return {"status": "success", "version_id": version_id, "content": version.content, "version": version.version, "document_id": version.document_id, "created_at": version.created_at.isoformat()}
        else:
            logger.warning(f"MCP Tool 'get_document_version' version ID {version_id} not found.")
        return {"status": "error", "message": f"Document version ID {version_id} not found."}

from src.mcp_db_helpers_document import add_document_version_db, delete_document_version_db

@mcp_instance.tool(name="create_document_version", description="Create a new version for a document")
async def create_document_version(document_id: int, content: str, version_string: str):
    """
    Create a new version for a document.
    """
    logger.info(f"MCP Tool 'create_document_version' called for document_id: {document_id}, version_string: {version_string}.")
    async with get_session_from_factory() as session:
        document, version = await add_document_version_db(session, document_id=document_id, content=content, version_string=version_string)
        if document and version:
            logger.info(f"MCP Tool 'create_document_version' successfully created version '{version_string}' (ID: {version.id}) for document ID: {document_id}.")
            return {
                "status": "created",
                "document_id": document_id,
                "version": {
                    "id": version.id,
                    "version": version.version,
                    "created_at": version.created_at.isoformat()
                }
            }
        else:
            logger.error(f"MCP Tool 'create_document_version' failed to create version for document_id: {document_id}, version_string: {version_string}.")
            return {"status": "error", "message": f"Failed to create version for document ID {document_id}."}

from src.mcp_db_helpers_document import delete_document_version_db

@mcp_instance.tool(name="delete_document_version", description="Delete a version from a document")
async def delete_document_version(version_id: int):
    """
    Delete a version from a document.
    """
    logger.info(f"MCP Tool 'delete_document_version' called for version_id: {version_id}.")
    async with get_session_from_factory() as session:
        success = await delete_document_version_db(session, version_id=version_id)
        if success:
            logger.info(f"MCP Tool 'delete_document_version' successfully deleted version ID: {version_id}.")
            return {"status": "deleted", "version_id": version_id}
        else:
            logger.error(f"MCP Tool 'delete_document_version' failed to delete version ID: {version_id}.")
            return {"status": "error", "message": f"Failed to delete version ID {version_id}."}
