# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app
ENV SERVER_PORT=8000 # Keep default port

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
# --- CORRECTED: Comment moved before RUN ---
# Clear pip cache before install
RUN rm -rf /root/.cache/pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY ./src /app/src

# --- REVERTED CMD ---
CMD ["python", "-m", "src.main"]
