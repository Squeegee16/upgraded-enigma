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
RUN apt-get update && apt-get install -y --no-install-recommends \
    hamlib-utils \
    rtl-sdr \
    gpsd \
    gpsd-clients \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running the application
# IMPORTANT: Create user with specific UID/GID for volume permissions
RUN groupadd -r hamradio -g 1000 && \
    useradd -r -g hamradio -u 1000 -m -s /bin/bash hamradio

# Create data directories with proper ownership BEFORE switching user
# This is critical for volume mounts to work correctly
RUN mkdir -p /data/db /data/certs /data/backups /data/callsigns /data/logs && \
    chown -R hamradio:hamradio /data && \
    chmod -R 755 /data

# Copy Python virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set working directory and create it
WORKDIR /app
RUN chown hamradio:hamradio /app

# Copy application files with proper ownership
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

# Copy and set permissions for entrypoint script
COPY --chown=hamradio:hamradio docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create plugin implementations directory
RUN mkdir -p /app/plugins/implementations && \
    chown -R hamradio:hamradio /app/plugins

# Switch to non-root user
USER hamradio

# Expose application port
EXPOSE 5000

# Health check to ensure container is functioning properly
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()" || exit 1

# Use entrypoint script
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command to run the application
CMD ["python", "app.py"]
