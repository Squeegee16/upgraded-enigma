# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build for optimized image size and security
# Base image: Python 3.11 on Debian Bookworm (slim variant)

# Build stage - Install dependencies and compile Python packages
FROM python:3.11-slim-bookworm AS builder

# Set build-time metadata
LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio Operator Web Application - Builder Stage"
LABEL version="1.0.0"

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies for compiling Python packages
# These packages are needed for bcrypt, numpy, and other compiled dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements file first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies in a virtual environment
# Using venv ensures clean separation and easier troubleshooting
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Runtime stage - Minimal image with only runtime dependencies
FROM python:3.11-slim-bookworm

# Set runtime metadata
LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio Operator Web Application"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    FLASK_APP=app.py \
    FLASK_ENV=production

# Install runtime dependencies
# - hamlib-utils: For radio control via Hamlib
# - rtl-sdr: For RTL-SDR device support
# - gpsd: For GPS device support (optional)
# - ca-certificates: For SSL/TLS support
RUN apt-get update && apt-get install -y --no-install-recommends \
    hamlib-utils \
    rtl-sdr \
    gpsd \
    gpsd-clients \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running the application
# Security best practice: never run containers as root
RUN groupadd -r hamradio && \
    useradd -r -g hamradio -u 1000 -m -s /bin/bash hamradio && \
    mkdir -p /app /data && \
    chown -R hamradio:hamradio /app /data

# Copy Python virtual environment from builder stage
COPY --from=builder --chown=hamradio:hamradio /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Copy application files
# Organized in order of least to most frequently changing for optimal caching
COPY --chown=hamradio:hamradio config.py .
COPY --chown=hamradio:hamradio models ./models/
COPY --chown=hamradio:hamradio auth ./auth/
COPY --chown=hamradio:hamradio dashboard ./dashboard/
COPY --chown=hamradio:hamradio logbook ./logbook/
COPY --chown=hamradio:hamradio plugins ./plugins/
COPY --chown=hamradio:hamradio devices ./devices/
COPY --chown=hamradio:hamradio templates ./templates/
COPY --chown=hamradio:hamradio static ./static/
COPY --chown=hamradio:hamradio app.py .
COPY --chown=hamradio:hamradio requirements.txt .

# Create necessary directories with proper permissions
RUN mkdir -p \
    /data/db \
    /data/certs \
    /data/callsigns \
    /data/backups \
    /app/plugins/implementations \
    && chown -R hamradio:hamradio /data /app

# Switch to non-root user
USER hamradio

# Expose application port
# Port 5000 is the default Flask development port
# In production, consider using 8000 or 8080
EXPOSE 5000

# Health check to ensure container is functioning properly
# Checks if the application responds to HTTP requests
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()" || exit 1

# Default command to run the application
# Can be overridden in docker-compose.yml or docker run
CMD ["python", "app.py"]
