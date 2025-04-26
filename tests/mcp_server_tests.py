import requests
import json
import subprocess
import signal
import os
import time
import sseclient
import httpx
from httpx_sse import aconnect_sse
from anyio import create_memory_object_stream, create_task_group

# --- Configuration ---
# Adjust these URLs to match YOUR MCP server configuration
MCP_SERVER_ENDPOINT = "http://localhost:8000/mcp/sse"

# Add any necessary headers (e.g., Authorization if your server requires it)
REQUEST_HEADERS = {
    "Content-Type": "application/json",
    # "Authorization": "Bearer YOUR_API_KEY_IF_NEEDED"
}

# --- End Configuration ---

def launch_server():
    """Launches the MCP server in a separate process."""
    print("[TEST] Launching MCP server...")
    command = "python -m src.main"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"[TEST] MCP server process started with PID: {process.pid}")
    time.sleep(5)  # Add a 5-second delay to allow the server to start
    return process


def stop_server(process):
    """Stops the MCP server process."""
    print("[TEST] Stopping MCP server...")
    if process and process.poll() is None:
        # process.terminate()  # Try a graceful shutdown first
        os.kill(process.pid, signal.SIGTERM) # Use SIGTERM for graceful shutdown
        process.wait(timeout=10)  # Give it some time to shut down

        if process.poll() is None:
            try:
                print("[TEST] MCP server did not terminate gracefully, killing it...")
                process.kill() # If it's still running, force kill
            except Exception as e:
                print(f"Error killing process: {e}")
            finally:
                pass
        print("[TEST] MCP server stopped.")
    else:
        print("[TEST] MCP server process not found or already stopped.")


async def list_tools_test():
    """
    Launches the MCP server, establishes an SSE connection,
    sends a list_tools request as an SSE event, and prints the results.
    """
    server_process = launch_server()
    try:
        print("[TEST] Establishing SSE connection...")
        try:
            async with httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=30, follow_redirects=False) as client:
                try:
                    async with aconnect_sse(client, "GET", MCP_SERVER_ENDPOINT) as event_source:
                        event_source.response.raise_for_status()
                        print("[TEST] SSE connection established.")

                        print("[TEST] Sending list_tools request as SSE event...")
                        # Craft a JSON-RPC request to call the list_tools tool
                        tool_request = {
                            "jsonrpc": "2.0",
                            "method": "tools/list",
                            "params": {},
                            "id": 1
                        }
                        # Send the tool request as a data event
                        event_data = json.dumps(tool_request)
                        print(f"[TEST->SERVER] Sending: {event_data}")
                        # await client.post(MCP_SERVER_ENDPOINT, json=tool_request) # This is wrong
                        # await client.send(event_data)

                        try:
                            async for sse in event_source.aiter_sse():
                                print(f"[TEST<-SERVER] Received event: {sse.event}, data: {sse.data}")
                                if sse.event == 'message':
                                    try:
                                        result = json.loads(sse.data)
                                        print(f"[TEST<-SERVER] list_tools response: {result}")
                                        # Add assertions here to validate the response
                                        assert "result" in result, "Response should contain 'result'"
                                        assert isinstance(result["result"], list), "Result should be a list"
                                        print("[TEST] list_tools test passed.")
                                        break  # Stop listening after receiving the response
                                    except (json.JSONDecodeError, AssertionError) as e:
                                        print(f"[ERROR] list_tools test failed: {e}")
                                        break
                        except httpx.RequestError as e:
                            print(f"[ERROR] SSE connection or request failed: {e}")
                        except Exception as e:
                            print(f"[ERROR] An unexpected error occurred: {e}")
                except Exception as inner_e:
                    print(f"Error during SSE connection: {inner_e}")

        except Exception as e:
            print(f"Error during client setup: {e}")

    finally:
        try:
            stop_server(server_process)
        except Exception as e:
            print(f"Error stopping server: {e}")
        finally:
            pass

if __name__ == "__main__":
    import asyncio
    asyncio.run(list_tools_test())
