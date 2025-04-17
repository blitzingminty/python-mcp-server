# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app
ENV SERVER_PORT=8000

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
# --- MODIFIED: Force install FROM SOURCE ---
RUN rm -rf /root/.cache/pip && \
    pip install --no-cache-dir --force-reinstall --no-binary :all: -r requirements.txt

# Copy project code
COPY ./src /app/src

# Clean .pyc files (Optional but can leave it for now)
# RUN find /app -name "*.pyc" -delete

# --- REVERTED FINAL CMD ---
CMD ["python", "-m", "src.main"]
