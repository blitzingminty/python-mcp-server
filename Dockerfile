# --- MODIFIED: Use non-slim base image ---
    FROM python:3.12

    # Set environment variables
    ENV PYTHONDONTWRITEBYTECODE 1
    ENV PYTHONUNBUFFERED 1
    ENV PYTHONPATH /app
    ENV SERVER_PORT=8000
    
    # Set work directory
    WORKDIR /app
    
    # --- NEW: Install only libffi-dev (needed for cffi dependency) ---
    RUN apt-get update && \
        apt-get install -y --no-install-recommends libffi-dev && \
        rm -rf /var/lib/apt/lists/*
    
    # Install Python dependencies (allow wheels, remove --no-binary, remove --force-reinstall)
    COPY requirements.txt .
    RUN rm -rf /root/.cache/pip && \
        pip install --no-cache-dir -r requirements.txt
    
    # Copy project code
    COPY ./src /app/src
    
    # Clean .pyc files (Optional)
    # RUN find /app -name "*.pyc" -delete
    
    # --- FINAL CMD ---
    CMD ["python", "-m", "src.main"]
