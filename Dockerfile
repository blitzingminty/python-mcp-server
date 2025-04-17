# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app
ENV SERVER_PORT=8000

# Set work directory
WORKDIR /app

# --- NEW: Install build dependencies ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies from source
COPY requirements.txt .
RUN rm -rf /root/.cache/pip && \
    pip install --no-cache-dir --force-reinstall --no-binary :all: -r requirements.txt

# Copy project code
COPY ./src /app/src

# Clean .pyc files (Optional)
# RUN find /app -name "*.pyc" -delete

# --- FINAL CMD ---
CMD ["python", "-m", "src.main"]
