# src/main.py
# Main entry point - Refactored for FastMCP and direct execution

import logging
import sys
import uvicorn # For running FastAPI
import argparse # <-- Import argparse
import asyncio # <-- Need asyncio back for init_db

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

# --- Project Imports ---
# Use absolute imports from the 'src' package
from src.config import settings
from src.database import init_db # Import DB initialization function
from src.mcp_server_instance import mcp_instance
from .web_routes import router as web_ui_router

# --- SDK Imports ---
# Not needed directly here anymore

# --- Logging Setup ---
logger = logging.getLogger()
logger.setLevel(settings.LOG_LEVEL)
if not logger.hasHandlers():
     handler = logging.StreamHandler(sys.stdout)
     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
     handler.setFormatter(formatter)
     logger.addHandler(handler)


# --- Base Directory ---
# Define base dir if needed for templates/static relative paths
# Assumes main.py is in src, so project root is parent
# If running with `python -m src.main`, CWD is project root.
# Let's use Path for robustness.
# BASE_DIR = Path(__file__).resolve().parent # This would be src dir
PROJECT_ROOT = Path(__file__).resolve().parent.parent # Assumes main.py is in src

# --- Configure Templates ---
# Create templates object pointing to 'src/templates'
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "src/templates"))



# --- Main Application Logic ---

# Make this synchronous - mcp_instance.run() appears to be blocking
def run_stdio_mode():
    """Runs the server in STDIO mode using FastMCP."""
    logger.info("Starting server in STDIO mode (using mcp_instance.run())...")
    try:
        mcp_instance.run() # Call directly, it's blocking
        logger.info("MCP Server run() completed.") # Only logs on exit
    except Exception as e:
        logger.critical(f"Failed to run in STDIO mode: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down STDIO mode...")






def run_http_mode():
    """Runs the server in HTTP mode using FastAPI mounting FastMCP & WebUI."""
    logger.info(f"Starting server in HTTP mode (FastAPI + FastMCP + WebUI) on {settings.SERVER_HOST}:{settings.SERVER_PORT}...")

    app = FastAPI(
        title=settings.PROJECT_NAME + " (HTTP Mode)",
        version=settings.VERSION,
    )

    # --- Store templates object in app state for access in routes ---
    app.state.templates = templates # Make templates accessible to routes

    # --- Configure Static Files ---
    static_dir = PROJECT_ROOT / "src/static"
    if not static_dir.is_dir():
        # logger.warning(f"Static directory not found at {static_dir}, creating.") # Optional: remove warning if dir is always expected
        static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted from {static_dir} at /static")


    # --- Include Web UI Router FIRST ---
    # Mounted under '/ui' prefix
    logger.info("Including Web UI router at '/ui'...")
    app.include_router(web_ui_router, prefix="/ui", tags=["Web UI"])


    # --- Mount FastMCP's SSE App LAST (at root) ---
    # Mounting at '/' captures all traffic not matched by earlier routes/routers.
    try:
        logger.info("Mounting FastMCP SSE application at '/mcp'...")
        app.mount("/mcp", mcp_instance.sse_app()) # Handles MCP communication
        logger.info("FastMCP SSE application mounted successfully.")
    except Exception as e:
        logger.critical(f"Failed to mount FastMCP SSE application: {e}", exc_info=True)
        sys.exit(1)


    # --- Add Health Check for FastAPI itself ---
    @app.get("/_fastapi_health", tags=["Health"])
    async def health_check():
        logger.info("FastAPI health check requested")
        return {"status": "ok", "message": "FastAPI wrapper is running"}

    # --- Run Uvicorn ---
    uvicorn.run(
        app,
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )









# This remains synchronous
def main_server_runner():
    """Decides which server mode to run."""
    logger.info(f"Selected transport mode: {settings.MCP_TRANSPORT}")
    if settings.MCP_TRANSPORT == "stdio":
        run_stdio_mode() # Call synchronous function
    elif settings.MCP_TRANSPORT == "http":
        run_http_mode() # Call synchronous function
    else:
        logger.error(f"Invalid MCP_TRANSPORT setting: '{settings.MCP_TRANSPORT}'. Use 'http' or 'stdio'.")
        sys.exit(1)

# --- Script Entry Point ---
if __name__ == "__main__":
    # Call the main function directly.
    # It will read MCP_TRANSPORT and call the appropriate blocking runner.
    # Table creation now happens inside the app_lifespan.
    try:
        main_server_runner() # Renamed the function that checks transport mode
    except KeyboardInterrupt:
        logger.info("Server stopped manually.")
    except Exception as e:
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
        sys.exit(1)
        