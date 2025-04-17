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
# Keep clear cache and Force Reinstall
RUN rm -rf /root/.cache/pip && \
    pip install --no-cache-dir --force-reinstall -r requirements.txt

# Copy project code
COPY ./src /app/src

# Clean .pyc files
RUN find /app -name "*.pyc" -delete

# --- Keep diagnostic CMD that lists middleware dir ---
CMD ["sh", "-c", "echo '--- DIAGNOSTICS START ---' && \
# ... (rest of diagnostic commands including ls) ...
echo '--- LS /usr/local/lib/python3.11/site-packages/starlette/middleware/ ---' && ls -la /usr/local/lib/python3.11/site-packages/starlette/middleware/ && \
echo '--- DIAGNOSTICS END ---' && \
echo '--- RUNNING APP ---' && python -m src.main"]

# ---- ORIGINAL CMD (Comment out the diagnostic one and uncomment this when done) ----
# CMD ["python", "-m", "src.main"]
