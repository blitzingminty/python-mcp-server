# src/main.py
# --- RESTRUCTURED FOR Uvicorn CMD Execution ---

import logging
import sys
import uvicorn # Keep import
import os
from pathlib import Path

# --- FastAPI Imports ---
from fastapi import FastAPI, Request # Keep Request for health check dependency
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --- MCP / SSE Imports ---
# Assume FastMCP handles SSE internally via sse_app()

# --- Project Imports ---
from src.config import settings
# Import the MCP instance AND the lifespan function separately
from src.mcp_server_instance import mcp_instance, app_lifespan
# Ensure web_routes is importable
try:
    from src.web_routes import router as web_ui_router
except ImportError:
    logging.error("Failed to import web_ui_router from src.web_routes", exc_info=True)
    web_ui_router = None # Set to None if import fails, handle below
# ** Ensure your SQLAlchemy models are imported somewhere before lifespan runs **
# This might be in models.py, which might be imported by mcp_server_instance or web_routes
# If not, explicitly import them here:
# from src import models # Or: from . import models

# --- Logging Setup ---
logger = logging.getLogger()
# Use .upper() only if settings.LOG_LEVEL is expected to be lowercase string
log_level_setting = getattr(settings, 'LOG_LEVEL', 'INFO') # Default to INFO
# Ensure level is valid
log_level_upper = log_level_setting.upper()
if log_level_upper not in logging._nameToLevel:
    log_level_upper = 'INFO' # Fallback to INFO if invalid level string
    logger.warning(f"Invalid LOG_LEVEL '{log_level_setting}', defaulting to INFO.")

logger.setLevel(log_level_upper)
if not logger.hasHandlers():
     handler = logging.StreamHandler(sys.stdout)
     # Consistent formatter
     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
     handler.setFormatter(formatter)
     logger.addHandler(handler)
logger.info(f"Logging configured with level: {logging.getLevelName(logger.level)}")

# --- REMOVED DIRECT WRITE TEST ---

# --- Base Directory ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
logger.info(f"Project root determined as: {PROJECT_ROOT}")

# --- Configure Templates ---
templates_dir = PROJECT_ROOT / "src/templates"
templates = Jinja2Templates(directory=str(templates_dir))
logger.info(f"Templates configured from directory: {templates_dir}")

# --- Create FastAPI App Instance at Top Level ---
logger.info("Creating FastAPI application instance...")
app = FastAPI(
    title=settings.PROJECT_NAME + " (HTTP Mode)",
    version=settings.VERSION,
    # --- Attach the lifespan DIRECTLY ---
    lifespan=app_lifespan
)
# --- REMOVED lifespan check log ---
logger.info("FastAPI application instance created with explicit lifespan.")

# --- Configure FastAPI App Instance ---

# Store templates object in app state (accessible in dependencies/routes via request.app.state.templates)
app.state.templates = templates
logger.info("Templates attached to app state.")

# Configure Static Files
static_dir = PROJECT_ROOT / "src/static"
try:
    if not static_dir.is_dir():
        logger.warning(f"Static directory {static_dir} not found, creating.")
        static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted from {static_dir} at /static")
except Exception as e:
    logger.error(f"Failed to mount static files from {static_dir}: {e}", exc_info=True)

# Include Web UI Router (if imported successfully)
if web_ui_router:
    logger.info("Including Web UI router at '/ui'...")
    # Make sure web_routes imports the get_db_session dependency correctly
    app.include_router(web_ui_router, prefix="/ui", tags=["Web UI"])
else:
    logger.warning("Web UI router not imported, skipping inclusion.")


# Mount the FastMCP SSE App directly under / (root)
try:
    sse_asgi_app = mcp_instance.sse_app()
    if sse_asgi_app:
         app.mount("/", sse_asgi_app, name="mcp_sse_app") # Mounted at root
         logger.info("Mounted FastMCP SSE application at '/'.")
         logger.info("--> Expected SSE connection endpoint: /sse")
         logger.info("--> Expected SSE message endpoint: /messages/")
    else:
         logger.error("mcp_instance.sse_app() did not return a valid application to mount.")
         raise RuntimeError("Failed to get SSE app from mcp_instance")

except AttributeError:
     logger.error("mcp_instance does not have an 'sse_app' method. Cannot mount SSE.")
     raise RuntimeError("mcp_instance has no sse_app method")
except Exception as e:
    logger.critical(f"Failed to mount FastMCP SSE application: {e}", exc_info=True)
    raise # Re-raise critical error


# Add Health Check for FastAPI itself (Optional)
@app.get("/_fastapi_health", tags=["Health"])
async def health_check():
    logger.info("FastAPI health check requested")
    return {"status": "ok", "message": "FastAPI wrapper is running"}
logger.info("Health check endpoint '/_fastapi_health' added.")

logger.info("FastAPI application configuration complete. Ready for Uvicorn.")

# --- Removed run_http_mode(), run_stdio_mode(), main_server_runner() ---
# --- Removed explicit asyncio.run(init_db()) call ---
# --- Removed if __name__ == '__main__': block ---
# Uvicorn running from CMD will now serve the 'app' object defined above.
