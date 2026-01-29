# Dockerfile for Integrador Backend (REST API + WS Gateway)
# Multi-stage build for smaller image size
#
# Build: docker build -t integrador-backend .
# Run:   docker run -p 8000:8000 --env-file .env integrador-backend

FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy ws_gateway code (needs access to shared modules in backend)
COPY ws_gateway/ ./ws_gateway/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Expose ports
EXPOSE 8000 8001

# Default command (REST API)
CMD ["python", "-m", "uvicorn", "rest_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
