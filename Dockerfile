# Multi-stage production Dockerfile for TaskForge AI Backend
# Stage 1: Build stage
FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Final runtime stage
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/taskforge/.local/bin:${PATH}" \
    APP_ENV="production" \
    APP_DEBUG="false"

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 10001 taskforge && \
    useradd -u 10001 -g taskforge -m -s /bin/bash taskforge

# Copy Python packages from builder to non-root user home
COPY --from=builder --chown=taskforge:taskforge /root/.local /home/taskforge/.local

# Create artifacts and data directory with proper ownership
RUN mkdir -p /app/artifacts /app/data && \
    chown -R taskforge:taskforge /app

# Copy application source code
COPY --chown=taskforge:taskforge . /app

# Switch to non-root user for enhanced security
USER taskforge

EXPOSE 8000

# Container liveness health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default execution using uvicorn with multi-worker ASGI support
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
