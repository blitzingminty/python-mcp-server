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
# --- MODIFIED: Clear cache and install on ONE line ---
RUN rm -rf /root/.cache/pip && pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY ./src /app/src

# --- Ensure CMD is still the standard one ---
CMD ["python", "-m", "src.main"]
