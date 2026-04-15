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
    cmake \
    libffi-dev \
    libssl-dev \
    build-essential \
    libusb-1.0-0-dev \
    python3-dev \
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
    gpsd \
    gpsd-clients \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build SoapySDR from source
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
# https://github.com/jketterl/openwebrx/wiki/Setup-Guide

# SDR monitor 
# RUN git clone https://github.com/shajen/sdr-monitor.git

# FLDIGI

# WINLINK

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
COPY --chown=hamradio:hamradio blacklist-rtl.conf /etc/modprobe.d/

# Create necessary directories with proper permissions
RUN mkdir -p \
    /data/db \
    /data/certs \
    /data/callsigns \
    /data/backups \
    /app/plugins/implementations \
    && chown -R hamradio:hamradio /data /app

COPY --chown=hamradio:hamradio amateur_delim.txt ./data/callsigns/

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
