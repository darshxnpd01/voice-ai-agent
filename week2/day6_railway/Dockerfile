# Dockerfile for Pipecat Voice AI Agent
# Deploys the Day 4 server to Railway for 24/7 operation

FROM python:3.11-slim

# Install system dependencies needed by Pipecat (audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (Docker layer caching — only reinstalls when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port Railway will route to
# Railway sets the PORT environment variable automatically
EXPOSE 8000

# Health check so Railway knows the service is up
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

# Start the server
# Railway automatically sets PORT — uvicorn reads it via the app
CMD ["python", "server.py"]
