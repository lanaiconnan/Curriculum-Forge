# Curriculum-Forge Gateway Dockerfile
# Python 3.7 compatible

FROM python:3.7-slim-bookworm

LABEL maintainer="Curriculum-Forge Team"
LABEL description="Curriculum-Forge Gateway - Multi-agent curriculum learning runtime"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash forge

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=forge:forge . .

# Create necessary directories
RUN mkdir -p /app/checkpoints /app/templates /app/workspace && \
    chown -R forge:forge /app

# Switch to non-root user
USER forge

# Expose gateway port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Default command: run gateway
CMD ["python", "main.py", "--gateway", "--port", "8765"]
