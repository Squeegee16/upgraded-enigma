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

# Go version to install.
# Must be >= the version required by any plugin's go.mod
# GrayWolf requires Go 1.26.x
# Check https://go.dev/dl/ for latest stable version
ARG GO_VERSION=1.22.3

# TARGETARCH is automatically set by Docker buildx
# to match the build target platform:
#   linux/amd64  -> amd64  (x86_64 PC)
#   linux/arm64  -> arm64  (Raspberry Pi 4/5, Apple M1)
ARG TARGETARCH

# Runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PLUGIN_SKIP_PIP_INSTALL=true

# Install runtime system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    autoconf \
    automake \
    libtool \
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
    xvfb \
    x11-utils \
    pulseaudio \
    pulseaudio-utils \
    alsa-utils \
    alsa-base \
    libasound2 \
    libasound2-plugins \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

# Install FLdigi and companion applications
RUN apt-get update && apt-get install -y --no-install-recommends \
    fldigi \
    flmsg \
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

# Build Hamlib from source
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

# Build RTL-SDR from source
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

# ============================================================
# Install Go from official distribution
#
# Uses TARGETARCH (set by Docker buildx) to select the
# correct binary for the build platform architecture.
# This supports both x86_64 (amd64) and ARM64 (Pi 4/5).
# ============================================================
RUN set -eux; \
    \
    case "${TARGETARCH}" in \
        "amd64")  GO_ARCH="amd64" ;; \
        "arm64")  GO_ARCH="arm64" ;; \
        "arm")    GO_ARCH="armv6l" ;; \
        "386")    GO_ARCH="386" ;; \
        *) \
            MACHINE=$(uname -m); \
            case "$MACHINE" in \
                "x86_64")  GO_ARCH="amd64" ;; \
                "aarch64") GO_ARCH="arm64" ;; \
                "armv7l")  GO_ARCH="armv6l" ;; \
                "armv6l")  GO_ARCH="armv6l" ;; \
                *) echo "Unsupported: $MACHINE"; exit 1 ;; \
            esac ;; \
    esac; \
    \
    echo "Platform: ${TARGETARCH:-runtime-detect}"; \
    echo "Go arch:  ${GO_ARCH}"; \
    echo "Machine:  $(uname -m)"; \
    \
    GO_URL="https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"; \
    echo "Downloading: ${GO_URL}"; \
    wget -q "${GO_URL}" -O /tmp/go.tar.gz; \
    \
    GO_SIZE=$(stat -c%s /tmp/go.tar.gz 2>/dev/null || echo 0); \
    echo "File size: ${GO_SIZE} bytes"; \
    if [ "${GO_SIZE}" -lt 10000000 ]; then \
        echo "ERROR: Download too small (${GO_SIZE} bytes)"; \
        exit 1; \
    fi; \
    \
    rm -rf /usr/local/go; \
    tar -C /usr/local -xzf /tmp/go.tar.gz; \
    rm /tmp/go.tar.gz; \
    /usr/local/go/bin/go version; \
    echo "Go installed successfully"

# Install Rust for building graywolf-modem
RUN curl --proto '=https' --tlsv1.2 \
        -sSf https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path \
        --default-toolchain stable 2>&1 && \
    /root/.cargo/bin/rustup --version && \
    /root/.cargo/bin/cargo --version

# Copy Rust to hamradio user (done after user creation below)

# Create non-root user
RUN groupadd -r hamradio -g 1000 && \
    useradd -r \
        -g hamradio \
        -u 1000 \
        -m \
        -s /bin/bash \
        -d /home/hamradio \
        hamradio && \
    usermod -a -G plugdev hamradio 2>/dev/null || true

# Create data directories
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

# Create X11 socket directory for Xvfb
RUN mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix && \
    chown root:root /tmp/.X11-unix

# Pre-create Go directories for hamradio user
RUN mkdir -p \
        /home/hamradio/go/bin \
        /home/hamradio/go/pkg \
        /home/hamradio/go/src \
        /home/hamradio/.cache/go-build \
        /home/hamradio/.local/bin \
    && chown -R hamradio:hamradio /home/hamradio

# Copy Rust installation to hamradio user
RUN cp -r /root/.cargo /home/hamradio/.cargo 2>/dev/null || true && \
    cp -r /root/.rustup /home/hamradio/.rustup 2>/dev/null || true && \
    chown -R hamradio:hamradio \
        /home/hamradio/.cargo \
        /home/hamradio/.rustup 2>/dev/null || true

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rX /opt/venv

# Set all environment variables
# Must come after Go and Rust installation
ENV GOROOT=/usr/local/go \
    GOPATH=/home/hamradio/go \
    GOCACHE=/home/hamradio/.cache/go-build \
    GOMODCACHE=/home/hamradio/go/pkg/mod \
    CARGO_HOME=/home/hamradio/.cargo \
    RUSTUP_HOME=/home/hamradio/.rustup \
    PATH="/usr/local/go/bin:/home/hamradio/.cargo/bin:/home/hamradio/.local/bin:/home/hamradio/go/bin:/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application source files
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
COPY --chown=hamradio:hamradio blacklist-rtl.conf /etc/modprobe.d/blacklist-rtl.conf

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/plugins/implementations && \
    chown -R hamradio:hamradio /app/plugins

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
