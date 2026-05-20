# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build for optimized image size and security.
#
# Stage 1 (builder): Installs all Python dependencies as root
#                    into a virtual environment.
# Stage 2 (runtime): Copies venv, builds SDR/radio tools,
#                    installs system packages, and runs as
#                    non-root user (hamradio:1000).
#
# Architecture support:
#   linux/amd64  - Standard x86_64 PC / server
#   linux/arm64  - Raspberry Pi 4/5, Apple M1/M2
#
# All Python packages are installed at build time so the
# non-root runtime user (hamradio) never needs to write
# to /opt/venv.
#
# Usage:
#   docker compose build
#   docker compose up -d

# ============================================================
# Stage 1: Builder
# Installs Python dependencies into /opt/venv as root.
# ============================================================
FROM python:3.11-slim-bookworm AS builder

LABEL stage="builder"
LABEL description="Ham Radio App - Python Dependency Builder"

# Python build environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build dependencies for compiling Python C extensions
# (psutil, numpy, cryptography, bcrypt etc.)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    python3-dev \
    libpq-dev \
    librtlsdr0 \
    nano \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first for better layer cache reuse.
# pip install only re-runs when requirements.txt changes.
COPY requirements.txt .

# Create virtual environment and install all packages as root.
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

# Go version to install from go.dev/dl/
# Must be >= version required by any plugin go.mod
# GrayWolf currently requires Go 1.26.x
# Check https://go.dev/dl/ for the latest stable release
ARG GO_VERSION=1.22.3

# TARGETARCH is set automatically by Docker buildx to match
# the build target platform:
#   linux/amd64  -> amd64   (x86_64 PC/server)
#   linux/arm64  -> arm64   (Raspberry Pi 4/5, Apple M1)
ARG TARGETARCH

# Runtime environment variables.
# PATH is extended after Go/Rust/venv are installed below.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PLUGIN_SKIP_PIP_INSTALL=true

# ============================================================
# Package Group 1: Core utilities
# Always available on all architectures and Debian versions.
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    wget \
    curl \
    git \
    ca-certificates \
    openssl \
    procps \
    lsb-release \
    gnupg \
    apt-transport-https \
    pkg-config \
    build-essential \
    cmake \
    autoconf \
    automake \
    libtool \
    swig \
    && rm -rf /var/lib/apt/lists/*

# Audio libraries for USB sound card support
# Required by sounddevice Python package
# SoundBlaster Play 3 uses standard USB Audio Class
# and is supported by ALSA/PulseAudio automatically
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    portaudio19-dev \
    libportaudio2 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Package Group 2: USB and device support
# Required for RTL-SDR, GPS serial, and radio CAT control.
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    usbutils \
    libusb-1.0-0-dev \
    libusb-1.0-0 \
    libudev-dev \
    && rm -rf /var/lib/apt/lists/*

# RTL-SDR development library for pyrtlsdr Python bindings
# Must be present before 'pip install pyrtlsdr'
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    librtlsdr-dev \
    librtlsdr0 \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Package Group 3: X11 display support + VNC
# Required for FLdigi and QSSTV which are GUI applications.
# Xvfb provides a virtual framebuffer — no real monitor needed.
# TigerVNC allows remote access to the virtual display.
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    xvfb \
    x11-utils \
    tigervnc-standalone-server \
    tigervnc-common \
    libxft-dev \
    libpng-dev \
    libxinerama-dev \
    libxfixes-dev \
    libxcursor-dev \
    libfontconfig1-dev \
    libxext-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Package Group 4: GPS support
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gpsd \
    gpsd-clients \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Package Group 5: Audio support
#
# IMPORTANT: libasound2 was renamed to libasound2t64 in
# Debian Bookworm (12). We try the new name first and fall
# back to the old name for compatibility.
#
# alsa-base was removed from Debian Bookworm entirely.
# Do NOT include it.
# ============================================================
RUN apt-get update && \
    ( \
        apt-get install -y --no-install-recommends \
            libasound2t64 \
        || \
        apt-get install -y --no-install-recommends \
            libasound2 \
    ) && \
    apt-get install -y --no-install-recommends \
        libasound2-dev \
        libasound2-plugins \
        alsa-utils \
        libsamplerate-dev \
        libsndfile1-dev \
        portaudio19-dev \
        libpulse0 \
        libpulse-dev \
        pulseaudio \
        pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Package Group 6: GNURadio (optional)
#
# GNURadio is a large dependency chain and may not be
# available on all ARM64 distributions. It is optional —
# RTL-SDR via rtl-sdr tools works without it.
# The build continues if GNURadio is not available.
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends gnuradio \
    || echo "INFO: gnuradio not available on $(uname -m) — skipping" && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Install FLdigi and dependencies
# NOTE: libasound2 renamed to libasound2t64 in Bookworm
# NOTE: rm -rf must be a SEPARATE command, not a package name
# ============================================================
RUN set -eux; \
    echo "=== Installing FLdigi ==="; \
    apt-get update; \
    \
    # Install runtime libraries first
    apt-get install -y --no-install-recommends \
        libfltk1.3 \
        libpulse0 \
        libsamplerate0 \
        libsndfile1 \
        portaudio19-dev \
    ; \
    \
    # Try libasound2t64 first (Debian Bookworm),
    # fall back to libasound2 (older Debian/Ubuntu)
    ( apt-get install -y --no-install-recommends \
        libasound2t64 \
    || apt-get install -y --no-install-recommends \
        libasound2 \
    ); \
    \
    # Install fldigi package
    apt-get install -y --no-install-recommends fldigi \
    || echo "INFO: fldigi not in apt repos"; \
    \
    # Install optional companion (non-fatal)
    apt-get install -y --no-install-recommends flrig \
    || echo "INFO: flrig not available"; \
    \
    # Clean up apt cache
    rm -rf /var/lib/apt/lists/*; \
    \
    # Verify installation
    if command -v fldigi >/dev/null 2>&1; then \
        echo "✓ FLdigi: $(fldigi --version 2>&1 | head -1)"; \
    else \
        echo "INFO: fldigi not installed via apt"; \
    fi; \
    \
    echo "=== FLdigi setup complete ==="

# ============================================================
# Build SoapySDR from source
#
# SoapySDR is the SDR hardware abstraction layer used by
# OpenWebRX and other SDR applications. Building from source
# ensures the correct version for the target architecture.
# ============================================================
RUN set -eux; \
    echo "=== Building SoapySDR ==="; \
    cd /tmp; \
    git clone \
        --depth 1 \
        https://github.com/pothosware/SoapySDR.git; \
    cd SoapySDR; \
    mkdir build; \
    cd build; \
    cmake \
        -DCMAKE_BUILD_TYPE=Release \
        ..; \
    make -j$(nproc); \
    make install; \
    ldconfig; \
    cd /; \
    rm -rf /tmp/SoapySDR; \
    echo "=== SoapySDR build complete ==="

# ============================================================
# Build Hamlib from source
#
# Hamlib provides radio control for 400+ radio models
# including the Yaesu FT-891.
# Version 4.7.0 used for stability and broad compatibility.
# ============================================================
RUN set -eux; \
    echo "=== Building Hamlib 4.7.0 ==="; \
    cd /tmp; \
    wget -q \
        "https://sourceforge.net/projects/hamlib/files/hamlib/4.7.0/hamlib-4.7.0.tar.gz/download" \
        -O hamlib-4.7.0.tar.gz; \
    tar -xzf hamlib-4.7.0.tar.gz; \
    cd hamlib-4.7.0; \
    ./configure --prefix=/usr/local; \
    make -j$(nproc); \
    make install; \
    ldconfig; \
    cd /; \
    rm -rf /tmp/hamlib-4.7.0 /tmp/hamlib-4.7.0.tar.gz; \
    echo "=== Hamlib build complete ==="

# ============================================================
# Build RTL-SDR from source
#
# Provides rtl_sdr, rtl_test, and other utilities for
# RTL2832U-based SDR USB dongles.
# ============================================================
RUN set -eux; \
    echo "=== Building RTL-SDR ==="; \
    cd /tmp; \
    git clone \
        --depth 1 \
        https://github.com/osmocom/rtl-sdr.git; \
    cd rtl-sdr; \
    mkdir build; \
    cd build; \
    cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DINSTALL_UDEV_RULES=ON \
        ..; \
    make -j$(nproc); \
    make install; \
    ldconfig; \
    cd /; \
    rm -rf /tmp/rtl-sdr; \
    echo "=== RTL-SDR build complete ==="

# ============================================================
# Install Go from official distribution
#
# Uses TARGETARCH (set by Docker buildx) to select the
# correct binary for the build platform.
#
# Architecture mapping:
#   TARGETARCH   Go arch    Platform
#   amd64        amd64      x86_64 PC / server
#   arm64        arm64      Raspberry Pi 4/5, Apple M1
#   arm          armv6l     Raspberry Pi 3 (32-bit)
#   386          386        32-bit x86
# ============================================================
RUN set -eux; \
    \
    # Determine Go architecture from Docker TARGETARCH.
    # Fall back to uname -m if TARGETARCH is not set
    # (e.g. plain docker build without buildx).
    if [ -n "${TARGETARCH}" ]; then \
        case "${TARGETARCH}" in \
            amd64)  GO_ARCH=amd64 ;; \
            arm64)  GO_ARCH=arm64 ;; \
            arm)    GO_ARCH=armv6l ;; \
            386)    GO_ARCH=386 ;; \
            *) \
                echo "Unknown TARGETARCH: ${TARGETARCH}"; \
                exit 1 ;; \
        esac; \
    else \
        MACHINE=$(uname -m); \
        case "$MACHINE" in \
            x86_64)  GO_ARCH=amd64 ;; \
            aarch64) GO_ARCH=arm64 ;; \
            armv7l)  GO_ARCH=armv6l ;; \
            armv6l)  GO_ARCH=armv6l ;; \
            *) \
                echo "Unsupported machine: $MACHINE"; \
                exit 1 ;; \
        esac; \
    fi; \
    \
    echo "TARGETARCH : ${TARGETARCH:-not set}"; \
    echo "uname -m   : $(uname -m)"; \
    echo "GO_ARCH    : ${GO_ARCH}"; \
    echo "GO_VERSION : ${GO_VERSION}"; \
    \
    GO_URL="https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"; \
    echo "Downloading: ${GO_URL}"; \
    wget -q "${GO_URL}" -O /tmp/go.tar.gz; \
    \
    # Verify the download is a reasonable size (>10 MB)
    GO_SIZE=$(stat -c%s /tmp/go.tar.gz 2>/dev/null || echo 0); \
    echo "Downloaded : ${GO_SIZE} bytes"; \
    if [ "${GO_SIZE}" -lt 10000000 ]; then \
        echo "ERROR: Downloaded file is too small."; \
        echo "Expected >10 MB, got ${GO_SIZE} bytes."; \
        echo "Check URL: ${GO_URL}"; \
        exit 1; \
    fi; \
    \
    rm -rf /usr/local/go; \
    tar -C /usr/local -xzf /tmp/go.tar.gz; \
    rm /tmp/go.tar.gz; \
    \
    # Verify Go runs on this architecture
    /usr/local/go/bin/go version; \
    echo "=== Go ${GO_VERSION} installed ==="

# ============================================================
# Install Rust for building graywolf-modem
#
# graywolf-modem is a Rust binary required by the GrayWolf
# Winlink plugin. Installed system-wide then copied to the
# hamradio user home directory.
# ============================================================
RUN set -eux; \
    echo "=== Installing Rust ==="; \
    curl --proto '=https' --tlsv1.2 \
        -sSf https://sh.rustup.rs \
        | sh -s -- -y \
            --no-modify-path \
            --default-toolchain stable; \
    /root/.cargo/bin/rustup --version; \
    /root/.cargo/bin/cargo --version; \
    echo "=== Rust installed ==="

# ============================================================
# Install qsstv
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends qsstv && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# SatDump — Optional from repo, skipped if unavailable
#
# Debian Bookworm has limited SDR packages. The official
# SatDump repo is tried later. If it fails, the plugin
# runs in demo mode and shows install instructions.
# ============================================================

# ============================================================
# Install wsjtx
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends wsjtx && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Copy and configure entrypoint script AS ROOT
#
# Must happen BEFORE USER hamradio because:
#   /usr/local/bin/ requires root to write to
#   chmod +x requires file owner or root
# ============================================================
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# ============================================================
# Copy RTL-SDR kernel module blacklist AS ROOT
# /etc/modprobe.d/ requires root ownership
# ============================================================
COPY blacklist-rtl.conf /etc/modprobe.d/blacklist-rtl.conf

# ============================================================
# Create non-root runtime user
#
# Fixed UID/GID (1000:1000) ensures volume-mounted
# directories on the host have matching ownership.
# ============================================================
RUN groupadd -r hamradio -g 1000 && \
    useradd -r \
        -g hamradio \
        -u 1000 \
        -m \
        -s /bin/bash \
        -d /home/hamradio \
        hamradio && \
    usermod -a -G plugdev hamradio 2>/dev/null || true

# Add hamradio user to dialout group for serial access
RUN usermod -a -G dialout hamradio 2>/dev/null || true && \
    usermod -a -G tty hamradio 2>/dev/null || true

# ============================================================
# Create data directories
# Must happen as root before USER hamradio so chown works.
# ============================================================
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

# ============================================================
# Create X11 socket directory for Xvfb
#
# Xvfb needs /tmp/.X11-unix to exist with sticky bit set.
# Must be created as root. The hamradio user can then
# start Xvfb without permission errors.
# ============================================================
RUN mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix && \
    chown root:root /tmp/.X11-unix

# ============================================================
# Pre-create Go workspace directories for hamradio user
#
# go build needs writable GOPATH and GOCACHE directories.
# Creating them here as root (then chown) ensures they exist
# before the hamradio user tries to use them.
# ============================================================
RUN mkdir -p \
        /home/hamradio/go/bin \
        /home/hamradio/go/pkg \
        /home/hamradio/go/src \
        /home/hamradio/.cache/go-build \
        /home/hamradio/.local/bin \
    && chown -R hamradio:hamradio /home/hamradio

# ============================================================
# Copy Rust installation to hamradio user
#
# Rust was installed as root. Copy .cargo and .rustup
# to the hamradio home so the user can run cargo.
# ============================================================
RUN cp -r /root/.cargo /home/hamradio/.cargo \
        2>/dev/null || true && \
    cp -r /root/.rustup /home/hamradio/.rustup \
        2>/dev/null || true && \
    chown -R hamradio:hamradio \
        /home/hamradio/.cargo \
        /home/hamradio/.rustup \
        2>/dev/null || true

# ============================================================
# SatDump — Try official repo, fall back to skip
#
# SatDump ARM64 may not be in the official repo for
# Debian Bookworm. The plugin will work in demo mode
# without the binary and show install instructions.
# ============================================================
RUN set -eux; \
    apt-get update; \
    \
    # Try to install from official SatDump repo
    if apt-get install -y --no-install-recommends \
        curl gnupg 2>/dev/null; then \
        \
        # Add SatDump GPG key (non-fatal if fails)
        curl -fsSL https://downloads.satdump.org/key.gpg \
            | apt-key add - 2>/dev/null || true; \
        \
        # Detect distro for repo URL
        DISTRO=$(. /etc/os-release 2>/dev/null && \
            echo "$VERSION_CODENAME" || echo "bookworm"); \
        \
        echo "deb [arch=$(dpkg --print-architecture)] \
https://downloads.satdump.org/apt ${DISTRO} main" \
            > /etc/apt/sources.list.d/satdump.list \
            2>/dev/null || true; \
        \
        apt-get update -q 2>/dev/null || true; \
        \
        # Install SatDump (non-fatal if not available)
        apt-get install -y --no-install-recommends \
            satdump 2>/dev/null \
        && echo "✓ SatDump installed" \
        || echo "INFO: SatDump not available for \
$(dpkg --print-architecture) — plugin runs in demo mode"; \
    fi; \
    \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Configure PulseAudio for the hamradio user
#
# Creates a PulseAudio config with a null sink so FLdigi
# can initialise its audio subsystem in Docker without
# real audio hardware.
# ============================================================
RUN mkdir -p /home/hamradio/.config/pulse && \
    cat > /home/hamradio/.config/pulse/default.pa << 'PULSE_CONFIG'
# PulseAudio configuration for FLdigi in Docker
# Provides a virtual audio device so FLdigi can start
# without real audio hardware being present.

.include /etc/pulse/default.pa

# Virtual output sink (no actual audio output)
load-module module-null-sink \
    sink_name=fldigi_null \
    sink_properties=device.description="FLdigi_Virtual_Sink"

set-default-sink fldigi_null

# Virtual input source (no actual microphone input)
load-module module-null-source \
    source_name=fldigi_null_source \
    source_properties=device.description="FLdigi_Virtual_Source"

set-default-source fldigi_null_source
PULSE_CONFIG

# ============================================================
# Configure ALSA to use PulseAudio
#
# Routes ALSA audio calls through PulseAudio so FLdigi
# finds an audio device even without real hardware.
# ============================================================
RUN cat > /home/hamradio/.asoundrc << 'ALSA_CONFIG'
# ALSA configuration routing audio through PulseAudio.
# This is needed for FLdigi to find an audio device in Docker.

pcm.!default {
    type pulse
    fallback "sysdefault"
    hint {
        show on
        description "Default ALSA via PulseAudio"
    }
}

ctl.!default {
    type pulse
    fallback "sysdefault"
}

# Explicit null device for applications that need it
pcm.null {
    type null
}

pcm.pulse {
    type pulse
}
ALSA_CONFIG

RUN chown -R hamradio:hamradio \
    /home/hamradio/.config \
    /home/hamradio/.asoundrc \
    2>/dev/null || true

# ============================================================
# Copy Python virtual environment from builder stage.
#
# The venv is owned by root but has a+rX permissions so
# the hamradio user can USE installed packages but cannot
# INSTALL new packages (the intended security boundary).
# ============================================================
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rX /opt/venv

# ============================================================
# Set all runtime environment variables.
#
# Must come AFTER Go, Rust, and venv are installed so the
# paths are valid when the container starts.
# ============================================================
ENV GOROOT=/usr/local/go \
    GOPATH=/home/hamradio/go \
    GOCACHE=/home/hamradio/.cache/go-build \
    GOMODCACHE=/home/hamradio/go/pkg/mod \
    CARGO_HOME=/home/hamradio/.cargo \
    RUSTUP_HOME=/home/hamradio/.rustup \
    PATH="/usr/local/go/bin:/home/hamradio/.cargo/bin:/home/hamradio/.local/bin:/home/hamradio/go/bin:/opt/venv/bin:$PATH"

# ============================================================
# Set working directory
# ============================================================
WORKDIR /app

# ============================================================
# Copy application source files
#
# Files are ordered from least to most frequently changed
# to maximise Docker build cache reuse.
# All files are owned by hamradio.
# ============================================================
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

# ============================================================
# Create plugin implementations directory
#
# Users copy plugin packages here at runtime.
# ============================================================
RUN mkdir -p /app/plugins/implementations && \
    chown -R hamradio:hamradio /app/plugins

# ============================================================
# Switch to non-root user
#
# ALL subsequent operations run as hamradio (UID 1000).
# This is the final configuration step — nothing requiring
# root should appear after this line.
# ============================================================
USER hamradio

# Document the application port
EXPOSE 5000

# Health check
# Uses plain HTTP because the app may redirect to HTTPS.
# The health check only needs a response, not a 200 status.
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
