# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

# Set work directory
WORKDIR /app

# Install dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY ./src /app/src

# Command to run the application using the main script
# Configuration (host, port) will be picked up from environment variables via config.py
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--proxy-headers", "--forwarded-allow-ips", "*"]