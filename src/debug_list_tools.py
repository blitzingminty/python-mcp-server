import asyncio
import sys
from pathlib import Path

# Add the project root's parent directory to sys.path to allow absolute imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.mcp_server_core import mcp_instance

async def list_tools():
    tools = await mcp_instance.list_tools()
    print("Registered MCP tools:")
    for tool in tools:
        print(f"- {tool.name}")

if __name__ == "__main__":
    asyncio.run(list_tools())
