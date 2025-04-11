# PowerShell Script to Scaffold Python MCP Server Project

# --- Configuration ---
$projectName = "python-mcp-server"
$pythonExecutable = "python" # Assumes python (or python3) is in your PATH. Change if needed.

# --- Check for Python ---
Write-Host "Checking for Python..."
try {
    & $pythonExecutable --version
    Write-Host "Python found." -ForegroundColor Green
} catch {
    Write-Host "Error: Python command '$pythonExecutable' not found or not executable." -ForegroundColor Red
    Write-Host "Please ensure Python 3 is installed and added to your PATH." -ForegroundColor Yellow
    return # Exit script
}

# --- Create Project Directory ---
if (Test-Path -Path $projectName) {
    Write-Host "Directory '$projectName' already exists. Please remove or choose a different name." -ForegroundColor Yellow
    # return # Optional: exit if directory exists
} else {
    New-Item -ItemType Directory -Path $projectName
    Write-Host "Created project directory: $projectName" -ForegroundColor Green
}
Set-Location -Path $projectName # Change into the project directory

# --- Create Source Structure ---
New-Item -ItemType Directory -Path "src"
New-Item -ItemType Directory -Path "src/templates"
New-Item -ItemType Directory -Path "src/static"
Write-Host "Created src directory structure."

# --- Create Placeholder Python Files ---
$filesToCreate = @(
    "src/__init__.py",
    "src/main.py",
    "src/mcp_server.py",
    "src/api_routes.py",
    "src/web_ui.py",
    "src/database.py",
    "src/models.py",
    "src/config.py",
    "src/utils.py"
)

foreach ($file in $filesToCreate) {
    $comment = "# Placeholder for $($file.Replace('/', '.')) logic"
    if ($file -like "*__init__.py") { $comment = "" } # No comment for __init__.py
    Set-Content -Path $file -Value $comment
}
Write-Host "Created placeholder Python files."

# --- Create requirements.txt ---
$requirements = @(
    "fastapi",
    "uvicorn[standard]",
    "modelcontextprotocol", # Assuming this is the correct PyPI package name for the SDK
    "python-dotenv",
    "SQLAlchemy",
    "alembic",
    "Jinja2",
    "starlette-session",
    "python-multipart" # Often needed with FastAPI for form data
)
Set-Content -Path "requirements.txt" -Value ($requirements -join "`n")
Write-Host "Created requirements.txt."

# --- Create .gitignore ---
$gitignoreContent = @(
    "# Python Bytecode and Cache",
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    "",
    "# Virtual Environment",
    ".venv/",
    "venv/",
    "ENV/",
    "env/",
    "",
    "# Environment Variables",
    ".env",
    ".env.*",
    "!*.env.example", # Keep example env files if any
    "",
    "# Database files",
    "*.db",
    "*.sqlite3",
    "",
    "# IDE / Editor specific",
    ".vscode/",
    ".idea/",
    "*.suo",
    "*.ntvs*",
    "*.njsproj",
    "*.sln",
    "*.swp"
)
Set-Content -Path ".gitignore" -Value ($gitignoreContent -join "`n")
Write-Host "Created .gitignore."

# --- Create README.md ---
$readmeContent = @"
# $projectName

Python MCP Server Implementation.

## Setup

1.  Ensure Python 3 is installed.
2.  Create a virtual environment: `python -m venv .venv`
3.  Activate the virtual environment:
    - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
    - Windows (Cmd): `.\.venv\Scripts\activate.bat`
    - Linux/macOS (Bash/Zsh): `source .venv/bin/activate`
4.  Install dependencies: `pip install -r requirements.txt`

## Running the Server

(Add instructions here later)
"@
Set-Content -Path "README.md" -Value $readmeContent
Write-Host "Created README.md."

# --- Create Virtual Environment ---
Write-Host "Creating Python virtual environment (.venv)..."
try {
    & $pythonExecutable -m venv .venv
    Write-Host "Virtual environment created." -ForegroundColor Green
} catch {
    Write-Host "Error creating virtual environment." -ForegroundColor Red
    return # Exit script
}

# --- Install Dependencies ---
Write-Host "Attempting to install dependencies from requirements.txt..."
Write-Host "This might take a moment."
try {
    # Activate and install in one command block for PowerShell
    & "$($pwd.ProviderPath)\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    Write-Host "Dependencies installed successfully." -ForegroundColor Green
} catch {
    Write-Host "Error installing dependencies. Try activating manually and running 'pip install -r requirements.txt'." -ForegroundColor Red
    Write-Host "To activate (PowerShell): .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    return # Exit script
}

# --- Final Instructions ---
Write-Host "`nProject '$projectName' setup complete." -ForegroundColor Cyan
Write-Host "To activate the virtual environment in your PowerShell terminal, run:" -ForegroundColor Yellow
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "You should see '(.venv)' at the beginning of your prompt." -ForegroundColor Yellow
Write-Host "You can now open the '$projectName' folder in VS Code." -ForegroundColor Cyan

# Deactivate if needed (usually not necessary as script ends)
# if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }

Set-Location .. # Go back to the parent directory
