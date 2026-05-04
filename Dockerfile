# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build.
#
# Stage 1 (builder): Python dependencies
# Stage 2 (runtime): Application + SDR tools + current Go

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

# Go version to install from official distribution.
# Must be >= the version required by go.mod in any plugin.
# GrayWolf requires 1.26.x — using latest stable.
# Check https://go.dev/dl/ for current version.
ARG GO_VERSION=1.26.2
ARG GO_ARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PLUGIN_SKIP_PIP_INSTALL=true \
    # Go environment — paths under hamradio home
    GOROOT=/usr/local/go \
    GOPATH=/home/hamradio/go \
    GOCACHE=/home/hamradio/.cache/go-build \
    GOMODCACHE=/home/hamradio/go/pkg/mod \
    # PATH includes Go bin, hamradio local bin, and venv
    PATH="/usr/local/go/bin:/home/hamradio/.local/bin:/home/hamradio/go/bin:/opt/venv/bin:$PATH"

# ============================================================
# Install runtime system dependencies
#
# IMPORTANT: Comments must NEVER appear after package names
# on the same line in apt-get install blocks.
# Each comment must be on its own line BEFORE the package.
# Blank lines between packages also break the RUN command.
# ============================================================
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
    libpng-dev \
    libxft-dev \
    libudev-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Install FLdigi and companion applications
#
# fldigi  - Digital modes modem (PSK31, RTTY, Olivia, etc.)
# flmsg   - Message forms companion for FLdigi
#
# NOTE: flarq is NOT available as a Debian package.
#       It must be built from source separately below.
#       flarq source: https://sourceforge.net/p/fldigi/fldigi
# ============================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    fldigi \
    flmsg \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Build flarq from source
#
# flarq is the ARQ file transfer companion for FLdigi.
# It is not packaged separately for Debian Bookworm.
# The source is hosted on SourceForge in the same
# repository as FLdigi.
#
# Repository:
#   https://sourceforge.net/p/fldigi/fldigi
#
# Build requirements (already installed above):
#   build-essential, autoconf, libfltk1.3-dev,
#   libpng-dev, libxft-dev, libpulse-dev
# ============================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfltk1.3-dev \
    libpulse-dev \
    libasound2-dev \
    libsamplerate-dev \
    libsndfile1-dev \
    portaudio19-dev \
    libxinerama-dev \
    libxfixes-dev \
    libxcursor-dev \
    libfontconfig1-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    # Clone flarq source from SourceForge
    # The flarq project lives in the fldigi repository
    # under the flarq directory
    cd /tmp && \
    git clone \
        --depth 1 \
        --branch flarq-4.3.9 \
        https://git.code.sf.net/p/fldigi/fldigi \
        fldigi-src \
    || git clone \
        --depth 1 \
        https://git.code.sf.net/p/fldigi/fldigi \
        fldigi-src; \
    \
    # Navigate to flarq subdirectory
    # flarq has its own configure.ac in the flarq/ subdir
    cd /tmp/fldigi-src; \
    \
    # Check what we cloned
    ls -la; \
    \
    # If flarq directory exists use it, otherwise
    # try building from the root (older repo layout)
    if [ -d "flarq" ]; then \
        cd flarq; \
    fi; \
    \
    # Bootstrap autotools build system
    if [ -f "bootstrap" ]; then \
        ./bootstrap; \
    elif [ -f "autogen.sh" ]; then \
        ./autogen.sh; \
    else \
        autoreconf -fi; \
    fi; \
    \
    # Configure the build
    ./configure --prefix=/usr/local; \
    \
    # Build using all available CPU cores
    make -j$(nproc); \
    \
    # Install the binary
    make install; \
    \
    # Verify installation
    which flarq && flarq --version || true; \
    \
    # Clean up source
    cd / && rm -rf /tmp/fldigi-src; \
    \
    echo "flarq build complete"

# -------------------------------------------------------
# Install Go from official distribution
#
# Why not apt golang-go?
#   Debian Bookworm ships Go 1.19 which is too old for
#   many modern Go modules. GrayWolf requires Go 1.26+.
#   The official Go tarball always has the current version.
#
# Installation method:
#   1. Download go${VERSION}.linux-amd64.tar.gz from go.dev
#   2. Extract to /usr/local/go
#   3. Add /usr/local/go/bin to PATH (done in ENV above)
#   4. Verify with 'go version'
# -------------------------------------------------------
RUN set -eux; \
    GO_URL="https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"; \
    echo "Downloading Go ${GO_VERSION} from ${GO_URL}"; \
    wget -q "${GO_URL}" -O /tmp/go.tar.gz; \
    # Remove any existing Go installation
    rm -rf /usr/local/go; \
    # Extract to /usr/local
    tar -C /usr/local -xzf /tmp/go.tar.gz; \
    rm /tmp/go.tar.gz; \
    # Verify installation
    /usr/local/go/bin/go version; \
    echo "Go ${GO_VERSION} installed successfully"

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
# Copy and configure entrypoint script AS ROOT
# Must happen BEFORE USER hamradio
# -------------------------------------------------------
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# -------------------------------------------------------
# Copy RTL-SDR kernel module blacklist AS ROOT
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
# Create data and application directories
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
# Pre-create Go workspace directories for hamradio user
#
# These must exist and be owned by hamradio before the
# container starts. Without them go build fails with
# permission errors when trying to create cache dirs.
# -------------------------------------------------------
RUN mkdir -p \
        /home/hamradio/go/bin \
        /home/hamradio/go/pkg \
        /home/hamradio/go/src \
        /home/hamradio/.cache/go-build \
        /home/hamradio/.local/bin \
    && chown -R hamradio:hamradio /home/hamradio

# -------------------------------------------------------
# Copy venv from builder (readable by all users)
# -------------------------------------------------------
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rX /opt/venv

WORKDIR /app

# -------------------------------------------------------
# Copy application source files (owned by hamradio)
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
# Install Rust toolchain for building graywolf-modem.
# graywolf-modem is a Rust binary required by GrayWolf.
# Must be installed as root and made available to
# the hamradio user via PATH.
# -------------------------------------------------------
RUN curl --proto '=https' --tlsv1.2 \
        -sSf https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path \
        --default-toolchain stable 2>&1 && \
    echo "✓ Rust installed" && \
    /root/.cargo/bin/rustup --version && \
    /root/.cargo/bin/cargo --version

# Make Rust available system-wide so the hamradio user
# can use cargo during GrayWolf installation
RUN cp -r /root/.cargo /home/hamradio/.cargo 2>/dev/null || \
    true && \
    cp -r /root/.rustup /home/hamradio/.rustup 2>/dev/null \
    || true && \
    chown -R hamradio:hamradio \
        /home/hamradio/.cargo \
        /home/hamradio/.rustup 2>/dev/null || true

ENV CARGO_HOME=/home/hamradio/.cargo \
    RUSTUP_HOME=/home/hamradio/.rustup
ENV GOPATH=/home/hamradio/go \
    GOCACHE=/home/hamradio/.cache/go-build \
    GOMODCACHE=/home/hamradio/go/pkg/mod \
    CARGO_HOME=/home/hamradio/.cargo \
    RUSTUP_HOME=/home/hamradio/.rustup \
    PATH="/home/hamradio/.cargo/bin:/home/hamradio/.local/bin:/home/hamradio/go/bin:/usr/local/go/bin:/opt/venv/bin:$PATH"
# -------------------------------------------------------
# Switch to non-root user
# ALL subsequent RUN, COPY, CMD, ENTRYPOINT run as hamradio
# -------------------------------------------------------
USER hamradio

EXPOSE 5000

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
