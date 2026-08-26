# Ham Radio Operator Web Application - Dockerfile
# =============================================
# Multi-stage build for optimized image size and security.
#
# Stage 1 (builder): Installs all Python dependencies into a virtual environment.
# Stage 2 (runtime): Uses the venv, builds SDR/radio tools, and runs as non-root.
#
# Architecture support: linux/amd64, linux/arm64

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.11-slim-bookworm AS builder

LABEL stage="builder"
LABEL description="[BUILDER] Ham Rad App - Python Dependency Builder"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    g++ \
    make \
    pkgconf \
    libffi-dev \
    libssl-dev \
    python3-dev \
    librtlsdr-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Install setuptools and wheel first to ensure pkg_resources is available
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install setuptools wheel && \
    pip install -r requirements.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim-bookworm

LABEL maintainer="Ham Rad App Team"
LABEL version="0.2.0"

ARG GO_VERSION=1.22.3
ARG TARGETARCH

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PLUGIN_SKIP_PIP_INSTALL=true

# Ensure locally compiled binaries always take precedence
# over any system-installed versions
ENV PATH="/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"

# ============================================================
# Package Group 1: Core utilities
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    wget curl git ca-certificates openssl procps \
    lsb-release gnupg apt-transport-https pkg-config \
    build-essential cmake autoconf automake libtool swig \
    libpq-dev librtlsdr0 librtlsdr-dev nano \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Audio libraries
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    pulseaudio pulseaudio-utils alsa-utils libasound2-plugins \
    libpulse0 libpulse-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# USB and device support
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    usbutils libusb-1.0-0-dev libusb-1.0-0 libudev-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# X11 display support + VNC
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    xvfb x11-utils tigervnc-standalone-server tigervnc-common \
    libxft-dev libpng-dev libxinerama-dev libxfixes-dev \
    libxcursor-dev libfontconfig1-dev libxext-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# GPS support
# Disable gpsd socket/service so it does not grab
# the serial port before our application does.
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gpsd gpsd-clients \
    && rm -rf /var/lib/apt/lists/*

RUN systemctl disable gpsd 2>/dev/null || true && \
    systemctl disable gpsd.socket 2>/dev/null || true

# ============================================================
# Audio support (Bookworm compat)
# ============================================================
RUN apt-get update && \
    (apt-get install -y --no-install-recommends libasound2t64 \
    || apt-get install -y --no-install-recommends libasound2) && \
    apt-get install -y --no-install-recommends \
    libasound2-dev libasound2-plugins alsa-utils \
    libsamplerate-dev libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# GNURadio (optional)
# NOTE: gnuradio pulls in libhamlib4 as a dependency.
# This will be purged after Hamlib 4.7.0 is compiled below.
# ============================================================
RUN apt-get update && \
    (apt-get install -y --no-install-recommends gnuradio \
    || echo "[BUILDER] INFO: gnuradio not available") && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Qt5 platform plugins
# ============================================================
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 \
    libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 \
    libxkbcommon-x11-0 libxkbcommon0 libgl1-mesa-glx libgl1 \
    libglib2.0-0 libdbus-1-3 libfontconfig1 libfreetype6 \
    libx11-6 libx11-xcb1 x11-utils xvfb \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# FLdigi
# ============================================================
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    libfltk1.3 libpulse0 libsamplerate0 libsndfile1 portaudio19-dev; \
    (apt-get install -y --no-install-recommends libasound2t64 \
    || apt-get install -y --no-install-recommends libasound2); \
    apt-get install -y --no-install-recommends fldigi \
    || echo "[BUILDER] INFO: fldigi not in apt repos"; \
    apt-get install -y --no-install-recommends flrig \
    || echo "[BUILDER] INFO: flrig not available"; \
    rm -rf /var/lib/apt/lists/*; \
    echo "[BUILDER] === FLdigi setup complete ==="

# ============================================================
# SoapySDR from source
# ============================================================
RUN set -eux; \
    cd /tmp; \
    git clone --depth 1 https://github.com/pothosware/SoapySDR.git; \
    cd SoapySDR; mkdir build; cd build; \
    cmake -DCMAKE_BUILD_TYPE=Release ..; \
    make -j$(nproc); make install; ldconfig; \
    cd /; rm -rf /tmp/SoapySDR; \
    echo "[BUILDER] === SoapySDR build complete ==="

# ============================================================
# Remove any system Hamlib BEFORE building from source.
# This prevents the system version from interfering with
# our compiled version during the build step.
# NOTE: gnuradio/wsjtx may reinstall libhamlib4 later.
# That is handled by the purge step AFTER all apt installs.
# ============================================================
RUN apt-get update && \
    apt-get remove -y --purge \
        libhamlib4 \
        libhamlib-dev \
        hamlib-utils \
        2>/dev/null || true && \
    apt-get autoremove -y 2>/dev/null || true && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Hamlib 4.7.0 from source
# ============================================================
RUN set -eux; \
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
    echo "[BUILDER] === Hamlib 4.7.0 build complete ==="; \
    # Verify correct version installed
    /usr/local/bin/rigctld --version

# ============================================================
# RTL-SDR from source
# ============================================================
RUN set -eux; \
    cd /tmp; \
    git clone --depth 1 https://github.com/osmocom/rtl-sdr.git; \
    cd rtl-sdr; mkdir build; cd build; \
    cmake -DCMAKE_BUILD_TYPE=Release -DINSTALL_UDEV_RULES=ON ..; \
    make -j$(nproc); make install; ldconfig; \
    cd /; rm -rf /tmp/rtl-sdr; \
    echo "[BUILDER] === RTL-SDR build complete ==="

# ============================================================
# Go installation
# ============================================================
RUN set -eux; \
    if [ -n "${TARGETARCH}" ]; then \
        case "${TARGETARCH}" in \
            amd64) GO_ARCH=amd64 ;; \
            arm64) GO_ARCH=arm64 ;; \
            *) echo "Unsupported: ${TARGETARCH}"; exit 1 ;; \
        esac; \
    else \
        GO_ARCH=amd64; \
    fi; \
    GO_URL="https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"; \
    wget -q "${GO_URL}" -O /tmp/go.tar.gz; \
    tar -C /usr/local -xzf /tmp/go.tar.gz; rm /tmp/go.tar.gz; \
    /usr/local/go/bin/go version; \
    echo "[BUILDER] === Go ${GO_VERSION} installed ==="

# ============================================================
# Rust installation
# ============================================================
RUN set -eux; \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
    sh -s -- -y --no-modify-path --default-toolchain stable; \
    /root/.cargo/bin/rustup --version; \
    /root/.cargo/bin/cargo --version; \
    echo "[BUILDER] === Rust installed ==="

# ============================================================
# QSSTV
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends qsstv && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# SatDump dependencies
# ============================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    libvolk2-dev libnng-dev zenity libzstd-dev libomp-dev \
    libarmadillo-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Install SatDump from official .deb (v1.2.2)
# ============================================================
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    curl -fsSL \
        -o /tmp/satdump.deb \
        'https://github.com/SatDump/SatDump/releases/download/1.2.2/satdump_1.2.2_arm64.deb'; \
    dpkg -i /tmp/satdump.deb || apt-get install -f -y; \
    rm /tmp/satdump.deb; \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# WSJTX
# NOTE: wsjtx pulls in libhamlib4 as a dependency.
# This will be purged in the cleanup step below.
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends wsjtx && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Pat for Winlink
# ============================================================
RUN /usr/local/go/bin/go install github.com/la5nta/pat@latest

# ============================================================
# Op25 P25 decoder dependencies
# NOTE: gnuradio-dev may pull in libhamlib4.
# This will be purged in the cleanup step below.
# ============================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcppunit-dev gnuradio-dev && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Op25 P25 decoder build
# ============================================================
RUN set -eux; \
    cd /tmp; \
    git clone https://github.com/boatbod/op25.git; \
    cd op25; sed -i 's/sudo //g' install.sh; \
    ./install.sh; ldconfig; \
    cd /; rm -rf /tmp/op25; \
    echo "[BUILDER] === P25 decoder build complete ==="

# ============================================================
# FIX 3: Purge system Hamlib reinstalled by gnuradio/wsjtx/op25
# ============================================================
# gnuradio, wsjtx, and gnuradio-dev all pull libhamlib4 back
# in as an apt dependency. We remove the system binaries here
# AFTER all apt installs are complete, then verify our
# compiled Hamlib 4.7.0 is the active version.
# ============================================================
RUN set -eux; \
    echo "=== Purging system Hamlib pulled in by gnuradio/wsjtx ==="; \
    # Remove system hamlib utilities/binaries
    apt-get remove -y --purge hamlib-utils 2>/dev/null || true; \
    apt-get autoremove -y 2>/dev/null || true; \
    # Force-remove system rigctld/rigctl binaries if they exist
    rm -f /usr/bin/rigctld 2>/dev/null || true; \
    rm -f /usr/bin/rigctl 2>/dev/null || true; \
    rm -f /usr/bin/rigmem 2>/dev/null || true; \
    rm -f /usr/bin/rigsmtr 2>/dev/null || true; \
    rm -f /usr/bin/rigswr 2>/dev/null || true; \
    rm -f /usr/bin/rotctl 2>/dev/null || true; \
    rm -f /usr/bin/rotctld 2>/dev/null || true; \
    # Re-run ldconfig so our /usr/local/lib libs are found
    ldconfig; \
    rm -rf /var/lib/apt/lists/*; \
    echo "=== System Hamlib binaries removed ==="; \
    # Verify our compiled version is still intact
    echo "Checking /usr/local/bin/rigctld..."; \
    ls -la /usr/local/bin/rigctld; \
    /usr/local/bin/rigctld --version; \
    # Verify PATH resolves to correct binary
    echo "PATH resolves rigctld to: $$(which rigctld)"; \
    # Hard version check - fails build if wrong version
    INSTALLED_VER=$$(/usr/local/bin/rigctld --version 2>&1 | \
        grep -oP 'Hamlib \K[\d.]+' | head -1); \
    echo "Active rigctld version: $${INSTALLED_VER}"; \
    if [ "$${INSTALLED_VER}" != "4.7.0" ]; then \
        echo "BUILD ERROR: Expected Hamlib 4.7.0 but got $${INSTALLED_VER}"; \
        echo "Check if a new package is pulling in system libhamlib4"; \
        exit 1; \
    fi; \
    echo "=== Hamlib 4.7.0 confirmed active and correct ==="

# ============================================================
# Entrypoint and RTL-SDR blacklist
# ============================================================
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
COPY blacklist-rtl.conf /etc/modprobe.d/blacklist-rtl.conf

# ============================================================
# Create hamradio user
# ============================================================
RUN groupadd -r hamradio -g 1000 && \
    useradd -r -g hamradio -u 1000 \
        -m -s /bin/bash \
        -d /home/hamradio hamradio && \
    usermod -a -G plugdev hamradio 2>/dev/null || true && \
    usermod -a -G dialout hamradio 2>/dev/null || true && \
    usermod -a -G tty hamradio 2>/dev/null || true

# ============================================================
# Data directories
# ============================================================
RUN mkdir -p \
    /data/db \
    /data/certs \
    /data/backups \
    /data/callsigns \
    /data/logs \
    /data/plugins \
    /app && \
    chown -R hamradio:hamradio /data /app && \
    chmod -R 755 /data

# ============================================================
# X11 socket directory
# ============================================================
RUN mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix && \
    chown root:root /tmp/.X11-unix

# ============================================================
# Go workspace for hamradio user
# ============================================================
RUN mkdir -p \
    /home/hamradio/go/bin \
    /home/hamradio/go/pkg \
    /home/hamradio/go/src \
    /home/hamradio/.cache/go-build \
    /home/hamradio/.local/bin && \
    chown -R hamradio:hamradio /home/hamradio

# ============================================================
# Copy Rust installation to hamradio user
# ============================================================
RUN cp -r /root/.cargo /home/hamradio/.cargo 2>/dev/null || true && \
    cp -r /root/.rustup /home/hamradio/.rustup 2>/dev/null || true && \
    chown -R hamradio:hamradio \
        /home/hamradio/.cargo \
        /home/hamradio/.rustup 2>/dev/null || true

# ============================================================
# PulseAudio config
# ============================================================
RUN mkdir -p /home/hamradio/.config/pulse && \
    cat > /home/hamradio/.config/pulse/default.pa << 'PULSE_CONFIG'
.include /etc/pulse/default.pa
load-module module-null-sink sink_name=fldigi_null sink_properties=device.description="FLdigi_Virtual_Sink"
set-default-sink fldigi_null
load-module module-null-source source_name=fldigi_null_source source_properties=device.description="FLdigi_Virtual_Source"
set-default-source fldigi_null_source
PULSE_CONFIG

# ============================================================
# ALSA config
# ============================================================
RUN cat > /home/hamradio/.asoundrc << 'ALSA_CONFIG'
pcm.!default { type pulse; fallback "sysdefault"; hint { show on; description "Default ALSA via PulseAudio"; } }
ctl.!default { type pulse; fallback "sysdefault"; }
pcm.null { type null; }
pcm.pulse { type pulse; }
ALSA_CONFIG

RUN chown -R hamradio:hamradio \
    /home/hamradio/.config \
    /home/hamradio/.asoundrc 2>/dev/null || true

# ============================================================
# Copy venv from builder stage
# ============================================================
COPY --from=builder /opt/venv /opt/venv
RUN chmod -R a+rX /opt/venv

# Ensure setuptools is present in the venv at runtime
# This fixes: No module named 'pkg_resources'
RUN /opt/venv/bin/pip install --upgrade setuptools wheel

# ============================================================
# Runtime environment variables
# ============================================================
ENV GOROOT=/usr/local/go \
    GOPATH=/home/hamradio/go \
    GOCACHE=/home/hamradio/.cache/go-build \
    GOMODCACHE=/home/hamradio/go/pkg/mod \
    CARGO_HOME=/home/hamradio/.cargo \
    RUSTUP_HOME=/home/hamradio/.rustup \
    PATH="/usr/local/bin:/usr/local/go/bin:/home/hamradio/.cargo/bin:/home/hamradio/.local/bin:/home/hamradio/go/bin:/opt/venv/bin:/usr/bin:/bin"

# ============================================================
# Application files
# ============================================================
WORKDIR /app

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

RUN mkdir -p /app/plugins/implementations && \
    chown -R hamradio:hamradio /app/plugins

# ============================================================
# Switch to non-root user
# ============================================================
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
