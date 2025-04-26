import asyncio
import sys
from pathlib import Path

# Add the project root's parent directory to sys.path to allow absolute imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.mcp_server_core import mcp_instance

async def list_tools():
    tools = await mcp_instance.list_tools()
    print("Server Name: python-mcp-server")
    print("Registered MCP tools:")
    for tool in tools:
        print(f"- {tool.name}")

    # Create a mock context
    class MockRequestContext:
        def __init__(self, lifespan_context):
            self.lifespan_context = lifespan_context

    class MockLifespanContext:
        def __init__(self, db_session_factory):
            self.db_session_factory = db_session_factory

    # Replace with your actual database session factory if you have one
    async def mock_db_session_factory():
        # This is just a placeholder, replace with actual session creation logic
        return None

    lifespan_context = MockLifespanContext(db_session_factory=mock_db_session_factory())
    request_context = MockRequestContext(lifespan_context=lifespan_context)
    context = {"request_context": request_context, "project_id": 1}

    # Call the list_memory tool
    print("\nCalling list_memory tool:")
    try:
        from src.mcp_memory_tools import list_memory
        result = await list_memory(context)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_tools())
