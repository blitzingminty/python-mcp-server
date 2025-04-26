# Main entry point - Refactored for FastMCP and direct execution
# --- REVERTED TO USING mcp_instance.sse_app() ---

import logging
import sys
import uvicorn # For running FastAPI
# import argparse # No longer needed
# import asyncio # No longer needed

# --- FastAPI Imports ---
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

# --- MCP / SSE Imports ---
# *** No longer need SseServerTransport, Route, Mount here ***
# Assume FastMCP handles this internally via sse_app()

# --- Project Imports ---
from .config import settings
from .mcp_server_lifespan import fastapi_lifespan as app_lifespan
from .web_routes import router as web_ui_router
from .mcp_server_core import mcp_instance

# --- Logging Setup ---
# Keep your existing logging setup
logger = logging.getLogger()
logger.setLevel(settings.LOG_LEVEL)
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# --- Base Directory ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Configure Templates ---
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "src/templates"))

# --- Create the main FastAPI App ---
app = FastAPI(
    title=settings.PROJECT_NAME + " (HTTP Mode)",
    version=settings.VERSION,
    # *** Pass the imported app_lifespan function directly ***
    lifespan=app_lifespan  # <--- CORRECTED LIFESPAN ARGUMENT
)
app.state.templates = templates



# --- Main Application Logic ---

def run_stdio_mode():
    """Runs the server in STDIO mode using FastMCP."""
    logger.info("Starting server in STDIO mode (using mcp_instance.run())...")
    try:
        mcp_instance.run()
        logger.info("MCP Server run() completed.")
    except Exception as e:
        logger.critical(f"Failed to run in STDIO mode: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down STDIO mode...")
    pass 

def run_http_mode():
    logger.info(f"Starting server in HTTP mode (FastAPI + FastMCP + WebUI) on {settings.SERVER_HOST}:{settings.SERVER_PORT}...")

    # --- Configure Static Files ---
    static_dir = PROJECT_ROOT / "src/static"
    if not static_dir.is_dir():
         static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted from {static_dir} at /static")

    # --- Include Web UI Router ---
    logger.info("Including Web UI router at '/ui'...")
    app.include_router(web_ui_router, prefix="/ui", tags=["Web UI"])


    # --- Mount the FastMCP SSE App ---
    try:
        sse_asgi_app = mcp_instance.sse_app()
        if sse_asgi_app:
            app.mount("/mcp", sse_asgi_app, name="mcp_sse_app")
            logger.info("Mounted FastMCP SSE application at '/mcp'.")

            # Add redirect route for trailing slash on /mcp/
            # Removed unused function redirect_mcp_trailing_slash to fix Pylance warning
            # @app.get("/mcp/", include_in_schema=False)
            # async def redirect_mcp_trailing_slash(request: Request):
            #     target_url = str(request.url).rstrip("/")
            #     return RedirectResponse(url=target_url, status_code=307)

            # Add POST forwarding route for /messages/ to MCP SSE app
            from starlette.middleware.base import BaseHTTPMiddleware
            from starlette.requests import Request as StarletteRequest
            from starlette.responses import Response
            from typing import Callable, Awaitable, List, Dict, Tuple
            from starlette.types import ASGIApp, Receive, Scope, Message

            class MCPMessageForwarder(BaseHTTPMiddleware):
                def __init__(self, app: ASGIApp) -> None:
                    super().__init__(app)

                async def dispatch(self, request: StarletteRequest, call_next: Callable[[StarletteRequest], Awaitable[Response]]) -> Response:
                    if request.url.path.startswith("/messages/") and request.method == "POST":
                        scope: Scope = dict(request.scope)
                        scope["path"] = request.url.path
                        scope["query_string"] = request.url.query.encode("utf-8")
                        receive: Receive = request.receive

                        # Collect response messages from mcp_instance.sse_app()
                        response_messages: List[Message] = []

                        async def send(message: Message) -> None:
                            response_messages.append(message)
                            # Add debug logging for each message sent by MCP app
                            logger.debug(f"MCP SSE message sent: {message}")

                        logger.info(f"Forwarding POST request to MCP app: path={scope['path']}")
                        await sse_asgi_app(scope, receive, send)
                        logger.info(f"Completed forwarding POST request to MCP app, collected {len(response_messages)} messages")

                        # Add logging to inspect tools list response
                        for message in response_messages:
                            if message["type"] == "http.response.body":
                                try:
                                    body_content = message.get("body", b"").decode("utf-8")
                                    logger.info(f"MCP tools list response body: {body_content}")
                                except Exception as e:
                                    logger.error(f"Failed to decode MCP tools list response body: {e}")

                        # Find the HTTP response start message
                        for message in response_messages:
                            if message["type"] == "http.response.start":
                                status_code: int = message.get("status", 200)
                                headers_raw: List[Tuple[bytes, bytes]] = message.get("headers", [])
                                break
                        else:
                            status_code = 200
                            headers_raw = []

                        # Decode headers from bytes to str
                        headers: Dict[str, str] = {}
                        for key_bytes, value_bytes in headers_raw:
                            headers[key_bytes.decode("latin1")] = value_bytes.decode("latin1")

                        # Find the HTTP response body message
                        body = b""
                        for message in response_messages:
                            if message["type"] == "http.response.body":
                                body += message.get("body", b"")
                                if not message.get("more_body", False):
                                    break

                        logger.info(f"Returning response from MCP app with status {status_code} and headers {headers}")
                        return Response(content=body, status_code=status_code, headers=headers)
                    else:
                        response = await call_next(request)
                        return response

            app.add_middleware(MCPMessageForwarder)

        if not sse_asgi_app:
             raise RuntimeError("mcp_instance.sse_app() did not return a valid application to mount.")
    except AttributeError:
        logger.error("mcp_instance does not have an 'sse_app' method. Cannot mount SSE.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed to mount FastMCP SSE application: {e}", exc_info=True)
        sys.exit(1)

    # --- Add Health Check ---
    @app.get("/_fastapi_health", tags=["Health"])
    async def health_check(): # type: ignore
        logger.info("FastAPI health check requested")
        return {"status": "ok", "message": "FastAPI wrapper is running"}

    # --- Run Uvicorn ---
    logger.info(f"Starting Uvicorn server process (Middleware handles proxy headers)...")
    uvicorn.run(
        app,
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*"
    )



def main_server_runner():
    """Decides which server mode to run."""
    logger.info(f"Selected transport mode: {settings.MCP_TRANSPORT}")
    if settings.MCP_TRANSPORT == "stdio":
        run_stdio_mode()
    elif settings.MCP_TRANSPORT == "http":
        run_http_mode()
    else:
        logger.error(f"Invalid MCP_TRANSPORT setting: '{settings.MCP_TRANSPORT}'. Use 'http' or 'stdio'.")
        sys.exit(1)
    pass

if __name__ == "__main__":
    try:
        main_server_runner()
    except KeyboardInterrupt:
        logger.info("Server stopped manually.")
    except Exception as e:
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
        sys.exit(1)
    pass
