# src/config.py (Temporary Diagnostic Version)
import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path
import sys # Add sys import
import traceback # Add traceback import

print("--- Importing config.py ---", file=sys.stderr)

try:
    print("--- config.py: Loading .env ---", file=sys.stderr)
    load_dotenv()
    print("--- config.py: Defining Settings class ---", file=sys.stderr)
    class Settings(BaseSettings):
         print("--- config.py: Inside Settings class definition ---", file=sys.stderr)
         PROJECT_NAME: str = "Python MCP Server"
         VERSION: str = "0.1.0"
         BASE_DIR: Path = Path(__file__).resolve().parent.parent
         print(f"--- config.py: BASE_DIR calculated: {BASE_DIR} ---", file=sys.stderr)
         _db_url_default = f"sqlite+aiosqlite:///{BASE_DIR}/mcp_server.db"
         print(f"--- config.py: Default DB URL calculated: {_db_url_default} ---", file=sys.stderr)
         # Read DATABASE_URL from env, using default if not found
         DATABASE_URL: str = os.getenv("DATABASE_URL", _db_url_default)
         print(f"--- config.py: DATABASE_URL definition processed (Value read by getenv: {os.getenv('DATABASE_URL')}) ---", file=sys.stderr)
         SERVER_HOST: str = "127.0.0.1"
         # Get port as string first, handle potential errors during int conversion later if needed
         _port_str = os.getenv("MCP_SESSION_SERVER_INTERNAL_PORT", "8000")
         print(f"--- config.py: Read MCP_SESSION_SERVER_INTERNAL_PORT as string: '{_port_str}' ---", file=sys.stderr)
         # The int conversion happens during Pydantic validation when Settings() is called
         SERVER_PORT: int = int(_port_str) # Keep this for type hinting, actual conversion/validation by Pydantic
         print(f"--- config.py: SERVER_PORT definition processed ---", file=sys.stderr)
         MCP_SERVER_NAME: str = "python-mcp-server"
         MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "http").lower()
         ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
         LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
         class Config:
             case_sensitive = True
             print("--- config.py: Inside Settings.Config definition ---", file=sys.stderr)
         print("--- config.py: Finished Settings class definition ---", file=sys.stderr)

    print("--- config.py: Instantiating Settings() ---", file=sys.stderr)
    settings = Settings()
    print(f"--- config.py: Settings() instantiated successfully. DATABASE_URL is: {settings.DATABASE_URL} ---", file=sys.stderr)
    print(f"--- config.py: SERVER_PORT is: {settings.SERVER_PORT} ---", file=sys.stderr)


except Exception as e:
    print(f"--- ERROR during config.py execution: {e} ---", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    raise # Re-raise to ensure failure is visible

print("--- Finished config.py import ---", file=sys.stderr)
