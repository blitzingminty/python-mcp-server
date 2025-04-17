# FINAL ATTEMPT: Simplest possible install on non-slim image
FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app
ENV SERVER_PORT=8000

# Set work directory
WORKDIR /app

# DO NOT ADD any 'RUN apt-get install ...' lines here

# Install Python dependencies (standard install, allowing wheels)
COPY requirements.txt .
# Simplest pip install command
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY ./src /app/src

# FINAL CMD
CMD ["python", "-m", "src.main"]
