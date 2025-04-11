# src/main.py
# Main entry point - Refactored for FastMCP and direct execution

import logging
import sys
import uvicorn # For running FastAPI
import argparse # <-- Import argparse
import asyncio # <-- Need asyncio back for init_db

from fastapi import FastAPI

# --- Project Imports ---
from .config import settings
from .database import init_db # Import DB initialization function
from .mcp_server_instance import mcp_instance

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

# This remains synchronous as uvicorn.run() is blocking
def run_http_mode():
    """Runs the server in HTTP mode using FastAPI mounting FastMCP."""
    logger.info(f"Starting server in HTTP mode (FastAPI + FastMCP) on {settings.SERVER_HOST}:{settings.SERVER_PORT}...")
    app = FastAPI(
        title=settings.PROJECT_NAME + " (FastAPI Wrapper)",
        version=settings.VERSION,
    )
    # Mount FastMCP's SSE App
    try:
        logger.info("Mounting FastMCP SSE application...")
        app.mount("/", mcp_instance.sse_app())
        logger.info("FastMCP SSE application mounted successfully at '/'")
    except AttributeError:
        logger.critical("mcp_instance does not have 'sse_app()' method. Check SDK version or FastMCP setup.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed to mount FastMCP SSE application: {e}", exc_info=True)
        sys.exit(1)

    # Add additional non-MCP FastAPI routes
    @app.get("/_fastapi_health")
    async def health_check():
        logger.info("FastAPI health check requested")
        return {"status": "ok", "message": "FastAPI wrapper is running"}

    # Run Uvicorn
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
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Run the Python MCP Server.")
    parser.add_argument(
        "--init-db",
        action="store_true", # Makes it a flag, doesn't require a value
        help="Initialize the database schema and exit."
    )
    args = parser.parse_args()

    # Check if --init-db flag is set
    if args.init_db:
        logger.info("Database initialization requested.")
        try:
            # Run the async init_db function
            asyncio.run(init_db())
            logger.info("Database initialization finished.")
        except Exception as e:
            logger.critical(f"Database initialization failed: {e}", exc_info=True)
            sys.exit(1)
        sys.exit(0) # Exit successfully after initializing DB
    else:
        # If --init-db is not set, run the main server logic
        try:
            main_server_runner()
        except KeyboardInterrupt:
            logger.info("Server stopped manually.")
        except Exception as e:
            logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
            sys.exit(1)
            