# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build for optimized image size and security.
#
# Stage 1 (builder): Installs all Python dependencies as root
#                    into a virtual environment.
# Stage 2 (runtime): Copies venv, builds SDR tools from source,
#                    and runs as non-root user (hamradio:1000).
#
# All Python packages are installed at build time so the
# non-root runtime user never needs to write to /opt/venv.
#
# Usage:
#   docker compose build
#   docker compose up -d

# ============================================================
# Stage 1: Builder
# Installs Python dependencies into /opt/venv as root.
# ============================================================
FROM python:3.11-slim-bookworm AS builder

LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio App - Dependency Builder Stage"
LABEL version="0.2.0"

# Python build environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build dependencies required to compile Python C extensions
# (psutil, numpy, cryptography, etc.)
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

WORKDIR /build

# Copy requirements first for better layer cache reuse.
# Docker will skip pip install if requirements.txt is unchanged.
COPY requirements.txt .

# Create virtual environment and install all packages as root.
# Combining pip install commands reduces image layers.
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt


# ============================================================
# Stage 2: Runtime
# Minimal image with SDR tools built from source.
# ============================================================
FROM python:3.11-slim-bookworm

LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio Operator Web Application"
LABEL version="0.2.0"

# Runtime environment variables.
# NOTE: FLASK_ENV defaults to production here.
#       docker-compose.yml overrides this per environment.
# NOTE: PLUGIN_SKIP_PIP_INSTALL=true tells all plugin
#       installers not to attempt pip installs at runtime
#       since the non-root user cannot write to /opt/venv.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PLUGIN_SKIP_PIP_INSTALL=true

# Install runtime system dependencies.
# Comments are on separate lines — NOT after package names,
# which would break the apt-get command.
#
# NOTE: wget appears only once (was duplicated before).
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    autoconf \
    build-essential \
    cmake \
    git \
    pkg-config \
    libusb-1.0-0-dev \
    libusb-1.0-0 \
    gnuradio \
    gpsd \
    gpsd-clients \
    ca-certificates \
    openssl \
    procps \
    lsb-release \
    gnupg \
    apt-transport-https \
    usbutils \
    golang-go \
    && rm -rf /var/lib/apt/lists/*

# Build and install SoapySDR from source.
# SoapySDR is the SDR hardware abstraction layer used by
# OpenWebRX and other SDR applications.
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

# Build and install Hamlib from source.
# Hamlib provides radio control for 400+ radio models.
# Version 4.7.0 is used for stability and FT-891 support.
RUN cd /tmp && \
    wget -q \
        https://sourceforge.net/projects/hamlib/files/hamlib/4.7.0/hamlib-4.7.0.tar.gz/download \
        -O hamlib-4.7.0.tar.gz && \
    tar -xzf hamlib-4.7.0.tar.gz && \
    cd hamlib-4.7.0 && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/hamlib-4.7.0 /tmp/hamlib-4.7.0.tar.gz

# Build and install RTL-SDR from source.
# Provides rtl_sdr, rtl_test and related utilities
# for RTL2832U-based SDR dongles.
RUN cd /tmp && \
    git clone https://github.com/osmocom/rtl-sdr.git && \
    cd rtl-sdr && \
    mkdir build && \
    cd build && \
    cmake -DINSTALL_UDEV_RULES=ON .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/rtl-sdr

# Create non-root runtime user.
# Using a fixed UID/GID (1000:1000) ensures that volume-mounted
# directories on the host have matching ownership.
RUN groupadd -r hamradio -g 1000 && \
    useradd -r \
        -g hamradio \
        -u 1000 \
        -m \
        -s /bin/bash \
        -d /home/hamradio \
        hamradio && \
    usermod -a -G plugdev hamradio 2>/dev/null || true

# Create all required data directories and set ownership
# BEFORE switching to the non-root user.
# This ensures the hamradio user can write to these directories
# even when they are bind-mounted from the Docker host.
RUN mkdir -p \
        /data/db \
        /data/certs \
        /data/backups \
        /data/callsigns \
        /data/logs \
        /data/plugins \
        /app \
    && chown -R hamradio:hamradio /data /app \
    && chmod -R 755 /data

# Copy the RTL-SDR kernel module blacklist.
# This must be owned by root and copied without --chown
# because /etc/modprobe.d/ requires root ownership.
# The hamradio user does not need to modify this file.
COPY blacklist-rtl.conf /etc/modprobe.d/blacklist-rtl.conf

# Copy Python virtual environment from builder stage.
# The venv is owned by root but has a+rX so the hamradio
# user can execute binaries and import packages.
# The hamradio user CANNOT install new packages at runtime,
# which is the intended security boundary.
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rX /opt/venv

WORKDIR /app

# Copy application source files with hamradio ownership.
# Files are ordered from least to most frequently changed
# to maximise Docker build cache effectiveness.
COPY --chown=hamradio:hamradio requirements.txt .
COPY --chown=hamradio:hamradio config.py .
COPY --chown=hamradio:hamradio secret_key_manager.py .
COPY --chown=hamradio:hamradio app.py .
COPY --chown=hamradio:hamradio models ./models/
COPY --chown=hamradio:hamradio auth ./auth/
COPY --chown=hamradio:hamradio dashboard ./dashboard/
COPY --chown=hamradio:hamradio logbook ./logbook/
COPY --chown=hamradio:hamradio plugins ./plugins/
COPY --chown=hamradio:hamradio devices ./devices/
COPY --chown=hamradio:hamradio callsign_db ./callsign_db/
COPY --chown=hamradio:hamradio templates ./templates/
COPY --chown=hamradio:hamradio static ./static/

# Copy entrypoint script.
# Owned by root so the hamradio user cannot modify it.
# chmod +x must be run as root before USER hamradio.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create the plugin implementations directory.
# Users copy plugin packages here at runtime.
RUN mkdir -p /app/plugins/implementations && \
    chown -R hamradio:hamradio /app/plugins

# Switch to non-root user for all subsequent operations
# and for the running container process.
USER hamradio

# Document the port this container listens on.
EXPOSE 5000

# Health check.
# Uses plain HTTP because SSL context is only confirmed
# after the app fully starts. The app redirects HTTP to HTTPS
# or responds on HTTP for the health check path.
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
