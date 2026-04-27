# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build for optimized image size and security
# Base image: Python 3.11 on Debian Bookworm (slim variant)
# ============================================================
# Stage 1: Builder
# ============================================================
# Build stage - Install dependencies and compile Python packages
FROM python:3.11-slim-bookworm AS builder

# Set build-time metadata
LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio App - Dependency Builder Stage"
LABEL version="0.2.0"

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
    cmake \
    libffi-dev \
    libssl-dev \
    build-essential \
    libusb-1.0-0-dev \
    python3-dev \
    libpq-dev \
    libpython3-dev \
    python3-numpy \
    swig \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements file first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies in a virtual environment
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip && \
    pip install setuptools && \
    pip install wheel && \
    pip install -r requirements.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
# Runtime stage - Minimal image with only runtime dependencies
FROM python:3.11-slim-bookworm

# Set runtime metadata
LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio Operator Web Application"
LABEL version="0.2.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    FLASK_APP=app.py \
    FLASK_ENV=development \
    # Tell plugins NOT to attempt runtime pip installs
    PLUGIN_SKIP_PIP_INSTALL=true

# Install runtime dependencies (including build tools for compilation)
# - wget: For downloading packages
# - autoconf: For building from source
# - build-essential: Compiler toolchain
# - cmake: Build system for SDR projects
# - git: For cloning SDR projects
# - pkg-config: For finding libraries
# - libusb-1.0-0-dev: For rtl-sdr USB support
# - libhamlib-dev: For radio control via Hamlib
# - gnuradio: GNU Radio framework
# - gpsd: For GPS device support
# - ca-certificates: For SSL/TLS support

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    autoconf \
    build-essential \
    cmake \
    git \
    pkg-config \
    libusb-1.0-0-dev \
    libhamlib-dev \
    gnuradio \
    # GPS support
    gpsd \
    gpsd-clients \
    ca-certificates \
    # SSL certificate generation
    openssl \
    # Process utilities (used by plugins)
    procps \
    # Network utilities
    curl \
    wget \
    usbutils \
    && rm -rf /var/lib/apt/lists/*

# Build SoapySDR from source # Radio control
RUN cd /tmp && \
    git clone https://github.com/pothosware/SoapySDR.git && \
    cd SoapySDR && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/SoapySDR

# Build hamlib from source
RUN cd /tmp && \
    wget https://sourceforge.net/projects/hamlib/files/hamlib/4.7.0/hamlib-4.7.0.tar.gz/download -O hamlib-4.7.0.tar.gz && \
    tar -xzf hamlib-4.7.0.tar.gz && \
    cd hamlib-* && \
    ./configure && \
    make && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/hamlib-*

# Build rtl-sdr from source
RUN cd /tmp && \
    git clone git://git.osmocom.org/rtl-sdr.git && \
    cd rtl-sdr && \
    mkdir build && \
    cd build && \
    cmake -DINSTALL_UDEV_RULES=ON .. && \
    make && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/rtl-sdr


#Install native plugins
# graywolf
RUN apt-get update && apt-get install -y --no-install-recommends \
    golang-go \
    && rm -rf /var/lib/apt/lists/*


# Create non-root user for running the application
# IMPORTANT: Create user with specific UID/GID for volume permissions
RUN groupadd -r hamradio -g 1000 && \
    useradd -r -g hamradio -u 1000 -m -s /bin/bash hamradio

# Create data directories with proper ownership BEFORE switching user
# This is critical for volume mounts to work correctly
RUN mkdir -p /data/db /data/certs /data/backups /data/callsigns /data/logs /data/plugins /app && \
    chown -R hamradio:hamradio /data /app && \
    chmod -R 755 /data

# Copy Python virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Make venv readable by hamradio user
RUN chmod -R a+rX /opt/venv

# Set working directory and create it
WORKDIR /app
RUN chown hamradio:hamradio /app

# Copy application files with proper ownership
COPY --chown=hamradio:hamradio config.py .
COPY --chown=hamradio:hamradio secret_key_manager.py .
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
COPY --chown=hamradio:hamradio blacklist-rtl.conf /etc/modprobe.d/
#COPY --chown=hamradio:hamradio callsigns.txt ./data/callsigns/
COPY --chown=hamradio:hamradio callsign_db ./callsign_db/

# Create necessary directories with proper permissions
#RUN mkdir -p \
#    /data/db \
#    /data/certs \
#    /data/callsigns \
#    /data/backups \
#    /app/plugins/implementations \
#    && chown -R hamradio:hamradio /data /app
    

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

# Health check
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=60s \
    --retries=3 \
    CMD python -c \
    "import urllib.request; \
     urllib.request.urlopen('http://localhost:5000/').read()" \
    || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "app.py"]
