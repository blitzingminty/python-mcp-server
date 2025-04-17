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
# Clear cache and install on one line
RUN rm -rf /root/.cache/pip && pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY ./src /app/src

# Clean .pyc files
RUN find /app -name "*.pyc" -delete

# --- MODIFIED TEMPORARY DIAGNOSTIC CMD ---
CMD ["sh", "-c", "echo '--- DIAGNOSTICS START ---' && \
echo 'Attempting direct import...' && \
python -c 'print(\"Importing...\"); from starlette.middleware.proxy_headers import ProxyHeadersMiddleware; print(\"Import OK!\")' && \
echo '--- DIAGNOSTICS END ---' && \
echo '--- RUNNING APP ---' && python -m src.main"]

# ---- ORIGINAL CMD (Comment out the diagnostic one and uncomment this when done) ----
# CMD ["python", "-m", "src.main"]
