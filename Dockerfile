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

# ---- TEMPORARY DIAGNOSTIC CMD - ADDED LS COMMANDS ----
CMD ["sh", "-c", "echo '--- DIAGNOSTICS START ---' && echo 'Python version:' && python --version && echo 'PIP version:' && pip --version && echo '--- PIP LIST ---' && pip list && echo '--- PIP SHOW STARLETTE ---' && pip show starlette && echo '--- SYS.PATH ---' && python -c 'import sys; print(sys.path)' && echo '--- LS /app ---' && ls -la /app && echo '--- LS /app/src ---' && ls -la /app/src && echo '--- DIAGNOSTICS END ---' && echo '--- RUNNING APP ---' && python -m src.main"]

# ---- ORIGINAL CMD (Comment out the diagnostic one and uncomment this when done) ----
# CMD ["python", "-m", "src.main"]
