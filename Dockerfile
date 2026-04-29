# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build for optimized image size and security.
#
# Stage 1 (builder): Installs all Python dependencies as root
#                    into a virtual environment.
# Stage 2 (runtime): Copies venv, builds SDR tools from source,
#                    and runs as non-root user (hamradio:1000).
#
# IMPORTANT ORDERING RULES:
#   1. All chmod/chown of system paths (/usr/local/bin, /etc)
#      must happen BEFORE USER hamradio
#   2. Files in /usr/local/bin must be owned by root
#   3. Files in /app and /data are owned by hamradio
#   4. The USER directive must be the LAST configuration
#      step before EXPOSE/HEALTHCHECK/ENTRYPOINT

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.11-slim-bookworm AS builder

LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio App - Dependency Builder Stage"
LABEL version="0.2.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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
COPY requirements.txt .

RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim-bookworm

LABEL maintainer="Ham Radio App Team"
LABEL description="Ham Radio Operator Web Application"
LABEL version="0.2.0"

# Runtime environment variables
# NOTE: All ENV directives are grouped here at the top
# of stage 2 for clarity and easy maintenance.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/hamradio/.local/bin:/home/hamradio/go/bin:/opt/venv/bin:$PATH" \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PLUGIN_SKIP_PIP_INSTALL=true \
    GOPATH=/home/hamradio/go \
    GOCACHE=/home/hamradio/.cache/go-build \
    GOMODCACHE=/home/hamradio/go/pkg/mod

# -------------------------------------------------------
# Install runtime system packages
# All RUN commands here execute as root (default)
# Comments are on their own lines - NOT after package
# names which would break the apt-get command
# -------------------------------------------------------
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

# -------------------------------------------------------
# Build SoapySDR from source
# -------------------------------------------------------
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

# -------------------------------------------------------
# Build Hamlib from source
# -------------------------------------------------------
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

# -------------------------------------------------------
# Build RTL-SDR from source
# -------------------------------------------------------
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

# -------------------------------------------------------
# Copy and configure the entrypoint script AS ROOT
# This MUST happen before USER hamradio because:
#   1. /usr/local/bin/ requires root to write to
#   2. chmod +x requires the file owner or root
#   3. After USER hamradio, neither condition is met
# -------------------------------------------------------
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# -------------------------------------------------------
# Copy the RTL-SDR kernel module blacklist AS ROOT
# /etc/modprobe.d/ requires root ownership
# -------------------------------------------------------
COPY blacklist-rtl.conf /etc/modprobe.d/blacklist-rtl.conf

# -------------------------------------------------------
# Create non-root runtime user
# -------------------------------------------------------
RUN groupadd -r hamradio -g 1000 && \
    useradd -r \
        -g hamradio \
        -u 1000 \
        -m \
        -s /bin/bash \
        -d /home/hamradio \
        hamradio && \
    usermod -a -G plugdev hamradio 2>/dev/null || true

# -------------------------------------------------------
# Create data directories and set ownership
# Must happen before USER hamradio
# -------------------------------------------------------
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

# -------------------------------------------------------
# Pre-create Go directories for the hamradio user
# Must happen before USER hamradio so chown works
# -------------------------------------------------------
RUN mkdir -p \
        /home/hamradio/go/bin \
        /home/hamradio/go/pkg \
        /home/hamradio/go/src \
        /home/hamradio/.cache/go-build \
        /home/hamradio/.local/bin \
    && chown -R hamradio:hamradio /home/hamradio

# -------------------------------------------------------
# Copy venv from builder stage
# Must happen before USER hamradio so chmod works
# -------------------------------------------------------
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rX /opt/venv

# -------------------------------------------------------
# Set working directory
# -------------------------------------------------------
WORKDIR /app

# -------------------------------------------------------
# Copy application source files
# These are owned by hamradio
# -------------------------------------------------------
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

# -------------------------------------------------------
# Create plugin implementations directory
# -------------------------------------------------------
RUN mkdir -p /app/plugins/implementations && \
    chown -R hamradio:hamradio /app/plugins

# -------------------------------------------------------
# Switch to non-root user
# THIS MUST BE THE LAST CONFIGURATION STEP
# After this line all RUN commands execute as hamradio
# which cannot write to /usr/local/bin, /etc, or /opt/venv
# -------------------------------------------------------
USER hamradio

# Document the port
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
