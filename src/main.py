# src/main.py (Temporary Diagnostic Version)
import logging
import sys
from pathlib import Path
import traceback # Add traceback

# Use stderr for initial prints in case logging isn't configured yet
print("--- Importing main.py ---", file=sys.stderr)

try:
    print("--- main.py: Importing settings from src.config ---", file=sys.stderr)
    from src.config import settings
    print(f"--- main.py: Successfully imported settings. DATABASE_URL: {getattr(settings, 'DATABASE_URL', 'Not Found')} ---", file=sys.stderr)
    print(f"--- main.py: LOG_LEVEL from settings: {getattr(settings, 'LOG_LEVEL', 'Not Found')} ---", file=sys.stderr)

    # Setup logger AFTER settings are presumably loaded
    logger = logging.getLogger()
    log_level_setting = getattr(settings, 'LOG_LEVEL', 'INFO') # Default to INFO
    logger.setLevel(log_level_setting.upper())
    if not logger.hasHandlers():
         handler = logging.StreamHandler(sys.stdout) # Or sys.stderr
         formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
         handler.setFormatter(formatter)
         logger.addHandler(handler)
    logger.info("--- main.py: Logging configured ---")

    print("--- main.py: Importing other components ---", file=sys.stderr)
    # Try importing other necessary components AFTER config
    from fastapi import FastAPI
    # from src.mcp_server_instance import mcp_instance # Keep this commented for now
    # from src.web_routes import router as web_ui_router # Keep commented

    print("--- main.py: Defining minimal FastAPI app ---", file=sys.stderr)
    app = FastAPI() # Define a minimal app to satisfy Uvicorn
    @app.get("/")
    def read_root(): return {"message": "Minimal diagnostic app"}

    print("--- main.py: Finished imports and app definition ---", file=sys.stderr)

except Exception as e:
    print(f"--- ERROR during main.py import/setup: {e} ---", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    # Ensure app is defined even on error so Uvicorn doesn't complain about that too
    if 'app' not in locals():
        from fastapi import FastAPI
        app = FastAPI()
        @app.get("/")
        def read_root_error(): return {"message": "Error during startup"}

# --- Keep no other code below this line for the diagnostic version ---
