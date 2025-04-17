# Use standard non-slim base image
FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app
ENV SERVER_PORT=8000

# Set work directory
WORKDIR /app

# Remove apt-get install line if it was present

# Install Python dependencies using uv
COPY requirements.txt .
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -r requirements.txt

# Copy project code
COPY ./src /app/src

# FINAL CMD
CMD ["python", "-m", "src.main"]
