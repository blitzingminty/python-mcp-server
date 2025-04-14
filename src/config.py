# src/config.py
# Placeholder for config.py logic

import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file if it exists
# Useful for development (create a .env file in the project root)
load_dotenv()

class Settings(BaseSettings):
    """Application configuration settings."""

    PROJECT_NAME: str = "Python MCP Server"
    VERSION: str = "0.1.0" # Default version

    # Determine base directory relative to this file
    BASE_DIR: Path = Path(__file__).resolve().parent.parent # Project root (one level up from src)

    # Database configuration
    # Defaulting to an SQLite DB in the project root
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/mcp_server.db")
    # Example for PostgreSQL: "postgresql+asyncpg://user:password@host:port/dbname"

    # Server configuration
    SERVER_HOST: str = "127.0.0.1" # Host for Uvicorn/FastAPI
    SERVER_PORT: int = int(os.getenv("MCP_SESSION_SERVER_INTERNAL_PORT", 8000))       # Port for Uvicorn/FastAPI (matches default)

    # MCP configuration (add specifics as needed)
    MCP_SERVER_NAME: str = "python-mcp-server"

    # Transport mode ('http' or 'stdio') - controls how the server runs
    MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "http").lower() # Default to http

    # Environment detection (e.g., 'development', 'production', 'docker')
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Logging configuration (basic example)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Add other configurations as needed, e.g., API keys, web UI settings
    # WEB_SESSION_SECRET: str = os.getenv("WEB_SESSION_SECRET", "your-default-secret-key") # Example for sessions

    class Config:
        # If using a .env file, specify its location if not in root
        # env_file = '.env'
        case_sensitive = True # Match environment variable names exactly

# Instantiate settings
settings = Settings()

# --- Example Usage (can remove later) ---
if __name__ == "__main__":
    print(f"Project Name: {settings.PROJECT_NAME}")
    print(f"Version: {settings.VERSION}")
    print(f"Database URL: {settings.DATABASE_URL}")
    print(f"Server Port: {settings.SERVER_PORT}")
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Log Level: {settings.LOG_LEVEL}")
    print(f"Base Directory: {settings.BASE_DIR}")
