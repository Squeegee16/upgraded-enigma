#!/bin/bash
# Ham Radio Application - Docker Entrypoint Script
# =================================================
# Initialises the container before starting the app.
# Checks USB RTL-SDR availability and provides
# clear guidance if the device is not accessible.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Ham Radio Operator Web Application${NC}"
echo -e "${GREEN}Docker Container Initialization${NC}"
echo -e "${GREEN}=================================================${NC}"

# =================================================================
# [0/7] Check user and permissions
# =================================================================
echo -e "\n${YELLOW}[0/7] Checking user and permissions...${NC}"
echo "Running as user: $(whoami) (UID: $(id -u), GID: $(id -g))"

if [ ! -w "/data" ]; then
    echo -e "${RED}ERROR: /data directory is not writable!${NC}"
    echo "Run on host: sudo chown -R 1000:1000 ./data"
    exit 1
fi
echo -e "${GREEN}✓ User and permissions validated${NC}"

# =================================================================
# [1/7] Secret key management
# =================================================================
echo -e "\n${YELLOW}[1/7] Managing secret key...${NC}"
SECRET_KEY_FILE="/data/secret_key"

if [ -n "$SECRET_KEY" ] && \
   [ "$SECRET_KEY" != "change-this-in-production" ]; then
    echo "Using SECRET_KEY from environment variable"
    if [ ! -f "$SECRET_KEY_FILE" ]; then
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
    fi
else
    if [ -f "$SECRET_KEY_FILE" ]; then
        echo "✓ Existing secret key found"
        export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    else
        echo "Generating new secret key..."
        NEW_KEY=$(python3 -c \
            "import secrets; print(secrets.token_hex(32))")
        echo "$NEW_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
        export SECRET_KEY="$NEW_KEY"
        echo "✓ New secret key generated and saved"
    fi
fi

KEY_LENGTH=$(echo -n "$SECRET_KEY" | wc -c)
if [ "$KEY_LENGTH" -lt 32 ]; then
    echo -e "${RED}ERROR: SECRET_KEY too short (${KEY_LENGTH} chars)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Secret key validated (length: ${KEY_LENGTH})${NC}"

# =================================================================
# [2/7] Environment validation
# =================================================================
echo -e "\n${YELLOW}[2/7] Validating environment...${NC}"
echo -e "${GREEN}✓ Environment validated${NC}"

# =================================================================
# [3/7] Directory setup
# =================================================================
echo -e "\n${YELLOW}[3/7] Setting up directories...${NC}"
for dir in \
    /data/db \
    /data/certs \
    /data/callsigns \
    /data/backups \
    /data/logs \
    /data/plugins; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir" || {
            echo -e "${RED}ERROR: Cannot create $dir${NC}"
            exit 1
        }
    fi
done
echo -e "${GREEN}✓ All directories created${NC}"

# =================================================================
# [4/7] SSL certificates
# =================================================================
echo -e "\n${YELLOW}[4/7] Checking SSL certificates...${NC}"
if [ "$USE_SSL" = "true" ]; then
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo "Generating self-signed certificate..."
        openssl req -x509 -newkey rsa:4096 -nodes \
            -out "$SSL_CERT" \
            -keyout "$SSL_KEY" \
            -days 365 \
            -subj "/C=CA/ST=Province/L=City/O=HamRadio/CN=localhost" \
            2>/dev/null
        chmod 644 "$SSL_CERT"
        chmod 600 "$SSL_KEY"
        echo -e "${GREEN}✓ SSL certificate generated${NC}"
    else
        echo -e "${GREEN}✓ SSL certificates found${NC}"
    fi
else
    echo "SSL disabled"
fi

# =================================================================
# [5/7] Database check
# =================================================================
echo -e "\n${YELLOW}[5/7] Initializing database...${NC}"
DB_PATH=$(echo "$DATABASE_URL" | sed 's|sqlite:///||')
DB_DIR=$(dirname "$DB_PATH")
echo "Database path: $DB_PATH"

if [ ! -d "$DB_DIR" ]; then
    echo -e "${RED}ERROR: Database directory $DB_DIR missing${NC}"
    exit 1
fi
if [ ! -w "$DB_DIR" ]; then
    echo -e "${RED}ERROR: Database directory not writable${NC}"
    exit 1
fi
if [ ! -f "$DB_PATH" ]; then
    echo "Database will be created on first run"
else
    echo -e "${GREEN}✓ Database exists: $DB_PATH${NC}"
fi

# ---------------------------------------------------------------
# RTL-SDR detection
# ---------------------------------------------------------------
echo -e "\n${BLUE}--- RTL-SDR Status ---${NC}"

if [ -d "/dev/bus/usb" ]; then
    echo -e "${GREEN}  ✓ /dev/bus/usb accessible${NC}"

    USB_COUNT=$(find /dev/bus/usb -type c 2>/dev/null \
        | wc -l)
    echo "  USB device nodes: ${USB_COUNT}"

    # Check for RTL-SDR via lsusb
    if command -v lsusb >/dev/null 2>&1; then
        RTL_USB=$(lsusb 2>/dev/null | \
            grep -iE "0bda:2832|0bda:2838|0bda:2839|\
realtek" || true)
        if [ -n "$RTL_USB" ]; then
            echo -e "${GREEN}  ✓ RTL-SDR detected:${NC}"
            echo "    $RTL_USB"
        else
            echo -e "${YELLOW}  ⚠ RTL-SDR not found via lsusb${NC}"
        fi
    fi

    # Test with rtl_test if available
    if command -v rtl_test >/dev/null 2>&1; then
        RTL_RESULT=$(timeout 3 rtl_test -t 2>&1 || true)
        if echo "$RTL_RESULT" | grep -q "Found.*device"; then
            echo -e "${GREEN}  ✓ RTL-SDR responds to rtl_test${NC}"
            echo "  RTL-SDR available for plugins"
        elif echo "$RTL_RESULT" | grep -q "No supported"; then
            echo -e "${YELLOW}  ⚠ No RTL-SDR found by rtl_test${NC}"
        fi
    fi

    # RTL-SDR symlink from udev rules
    if ls /dev/rtlsdr* >/dev/null 2>&1; then
        echo -e "${GREEN}  ✓ RTL-SDR symlink: \
$(ls /dev/rtlsdr*)${NC}"
    fi

    # NOTE: RTL-SDR usage depends on which plugins are loaded.
    # If OpenWebRX plugin is active it takes exclusive access.
    # If OpenWebRX is not used, the RTL-SDR is available
    # directly to other plugins (SDR Monitor, SatDump etc.)
    echo "  RTL-SDR will be assigned to whichever"
    echo "  plugin starts first. OpenWebRX sidecar"
    echo "  container (if running) has priority."

else
    echo -e "${YELLOW}  ⚠ /dev/bus/usb not accessible${NC}"
    echo "  To enable USB device access, add to"
    echo "  docker-compose.yml app service:"
    echo "    devices:"
    echo "      - /dev/bus/usb:/dev/bus/usb"
    echo "    privileged: true"
    echo ""
    echo "  RTL-SDR will use mock device until"
    echo "  USB passthrough is configured."
fi
# ---------------------------------------------------------------
# RTL-SDR detection and diagnosis
# ---------------------------------------------------------------
echo -e "\n${BLUE}--- RTL-SDR Status ---${NC}"

# Check if /dev/bus/usb is accessible inside the container
if [ -d "/dev/bus/usb" ]; then
    echo "✓ /dev/bus/usb is accessible"

    # Count USB devices visible in container
    USB_COUNT=$(find /dev/bus/usb -type c 2>/dev/null | wc -l)
    echo "  USB device nodes visible: $USB_COUNT"

    # Try to find RTL-SDR using lsusb if available
    if command -v lsusb >/dev/null 2>&1; then
        RTL_USB=$(lsusb 2>/dev/null | \
            grep -iE "0bda:2832|0bda:2838|0bda:2839|realtek" || true)
        if [ -n "$RTL_USB" ]; then
            echo -e "${GREEN}  ✓ RTL-SDR detected via lsusb:${NC}"
            echo "    $RTL_USB"
        else
            echo -e "${YELLOW}  ⚠ RTL-SDR not found via lsusb${NC}"
        fi
    fi

    # Try rtl_test if available in this container
    if command -v rtl_test >/dev/null 2>&1; then
        echo "  Testing RTL-SDR with rtl_test..."
        RTL_TEST_OUTPUT=$(timeout 5 rtl_test -t 2>&1 || true)
        if echo "$RTL_TEST_OUTPUT" | \
                grep -q "Found.*device\|No supported"; then
            if echo "$RTL_TEST_OUTPUT" | \
                    grep -q "Found.*device"; then
                echo -e "${GREEN}  ✓ RTL-SDR responds to rtl_test${NC}"
            else
                echo -e "${YELLOW}  ⚠ rtl_test: No RTL-SDR found${NC}"
                echo "    This container uses OpenWebRX sidecar"
                echo "    for SDR. RTL-SDR should be passed to"
                echo "    the openwebrx container instead."
            fi
        fi
    fi

else
    echo -e "${YELLOW}  ⚠ /dev/bus/usb not accessible${NC}"
    echo "    RTL-SDR is handled by the openwebrx sidecar."
    echo "    Ensure docker-compose.yml has:"
    echo "    devices:"
    echo "      - /dev/bus/usb:/dev/bus/usb"
    echo "    in the openwebrx service block."
fi

# ---------------------------------------------------------------
# Check if kernel drivers are blocking the device
# ---------------------------------------------------------------
if [ -f /proc/modules ]; then
    BLOCKING_MODULES=""
    for mod in dvb_usb_rtl28xxu rtl2832 rtl2830; do
        if grep -q "^${mod}" /proc/modules 2>/dev/null; then
            BLOCKING_MODULES="${BLOCKING_MODULES} ${mod}"
        fi
    done

    if [ -n "$BLOCKING_MODULES" ]; then
        echo -e "${YELLOW}  ⚠ Kernel modules loaded that may"
        echo "    block RTL-SDR access:${BLOCKING_MODULES}"
        echo "    Fix on HOST: sudo modprobe -r dvb_usb_rtl28xxu"
        echo "    Add to HOST /etc/modprobe.d/blacklist-rtl.conf:"
        echo "      blacklist dvb_usb_rtl28xxu"
        echo "      blacklist rtl2832${NC}"
    fi
fi

# ---------------------------------------------------------------
# Check rtlsdr symlink from udev rules
# ---------------------------------------------------------------
if ls /dev/rtlsdr* >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ RTL-SDR symlink found: $(ls /dev/rtlsdr*)${NC}"
fi

# ---------------------------------------------------------------
# GPS device
# ---------------------------------------------------------------
echo -e "\n${BLUE}--- GPS Status ---${NC}"
if [ "$USE_MOCK_DEVICES" = "false" ]; then
    if [ -e "$GPS_SERIAL_PORT" ]; then
        echo -e "${GREEN}  ✓ GPS device: $GPS_SERIAL_PORT${NC}"
    else
        echo -e "${YELLOW}  ⚠ GPS device not found: $GPS_SERIAL_PORT${NC}"
        echo "    Falling back to mock GPS"
    fi
else
    echo "  Mock GPS enabled"
fi

# ---------------------------------------------------------------
# Radio device
# ---------------------------------------------------------------
echo -e "\n${BLUE}--- Radio Status ---${NC}"
if [ "$USE_MOCK_DEVICES" = "false" ]; then
    if [ -e "$RADIO_PORT" ]; then
        echo -e "${GREEN}  ✓ Radio device: $RADIO_PORT${NC}"
    else
        echo -e "${YELLOW}  ⚠ Radio device not found: $RADIO_PORT${NC}"
        echo "    Falling back to mock radio"
    fi
else
    echo "  Mock radio enabled"
fi
# ---------------------------------------------------------------
# Go toolchain check (for GrayWolf plugin)
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# Go toolchain check (for GrayWolf and other Go plugins)
# ---------------------------------------------------------------
echo -e "\n${BLUE}--- Go Toolchain ---${NC}"

if command -v go >/dev/null 2>&1; then
    GO_INSTALLED=$(go version 2>/dev/null | \
        grep -oP 'go\K[\d.]+' | head -1)
    echo -e "${GREEN}  ✓ Go ${GO_INSTALLED} available${NC}"
    echo "  GOROOT:   ${GOROOT:-$(go env GOROOT)}"
    echo "  GOPATH:   ${GOPATH:-not set}"
    echo "  GOCACHE:  ${GOCACHE:-not set}"

    # Ensure Go directories are writable
    for dir in \
        "${GOPATH:-$HOME/go}" \
        "${GOCACHE:-$HOME/.cache/go-build}" \
        "${HOME}/.local/bin"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir" 2>/dev/null && \
                echo -e "${GREEN}  ✓ Created: $dir${NC}" || \
                echo -e "${YELLOW}  ⚠ Cannot create: $dir${NC}"
        fi
        if [ -w "$dir" ]; then
            echo -e "${GREEN}  ✓ Writable: $dir${NC}"
        else
            echo -e "${RED}  ERROR: Not writable: $dir${NC}"
        fi
    done

    # Show version for diagnostic purposes
    echo "  Full: $(go version)"

else
    echo -e "${RED}  ERROR: Go not found in PATH${NC}"
    echo "  PATH=${PATH}"
    echo "  Rebuild the Docker image with a current Go version"
fi
# ---------------------------------------------------------------
# OpenWebRX sidecar availability check
# ---------------------------------------------------------------
echo -e "\n${BLUE}--- OpenWebRX Sidecar ---${NC}"
OWRX_URL="${OPENWEBRX_URL:-http://openwebrx:8073}"
echo "  OpenWebRX URL: $OWRX_URL"

# Non-fatal — openwebrx may still be starting
OWRX_CHECK=$(python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('${OWRX_URL}', timeout=3)
    print('reachable:' + str(r.status))
except Exception as e:
    print('unreachable:' + str(e))
" 2>/dev/null || echo "unreachable:check failed")

if echo "$OWRX_CHECK" | grep -q "^reachable:"; then
    echo -e "${GREEN}  ✓ OpenWebRX is reachable${NC}"
else
    echo -e "${YELLOW}  ⚠ OpenWebRX not yet reachable${NC}"
    echo "    (It may still be starting — this is normal)"
    echo "    The plugin will retry when the page loads"
fi
# =================================================================
# Start PulseAudio with a null sink for FLdigi audio
# FLdigi requires an audio device to start. Without a real
# sound card in Docker we create a virtual null sink.
# This allows FLdigi to initialise and XML-RPC to start.
# =================================================================
echo -e "\n${YELLOW}[6c/7] Starting PulseAudio virtual audio...${NC}"

# Kill any stale PulseAudio instance
pulseaudio --kill 2>/dev/null || true
rm -f /run/user/1000/pulse/pid 2>/dev/null || true
rm -f /tmp/pulse-* 2>/dev/null || true

# Start PulseAudio as a daemon with null output
# --system=false  run as user daemon (not system-wide)
# --exit-idle-time=-1  never exit due to inactivity
# --log-level=error  suppress verbose ALSA warnings
if command -v pulseaudio >/dev/null 2>&1; then
    pulseaudio \
        --start \
        --log-target=syslog \
        --log-level=error \
        --exit-idle-time=-1 \
        2>/dev/null

    # Wait for PulseAudio to start
    sleep 1

    # Load the null sink module
    # This creates a virtual audio device that accepts
    # audio data without actually playing it
    pactl load-module module-null-sink \
        sink_name=fldigi_null \
        sink_properties=device.description="FLdigi_Null_Sink" \
        2>/dev/null && \
        echo -e "${GREEN}  ✓ PulseAudio null sink created${NC}" || \
        echo -e "${YELLOW}  ⚠ PulseAudio null sink failed${NC}"

    # Set the null sink as default
    pactl set-default-sink fldigi_null 2>/dev/null || true

    echo -e "${GREEN}  ✓ PulseAudio started${NC}"
else
    echo -e "${YELLOW}  ⚠ PulseAudio not available${NC}"
    echo "  FLdigi audio will be limited"
fi

# Create ALSA config to redirect to PulseAudio
# This ensures ALSA applications (like FLdigi) use
# PulseAudio as their backend automatically
cat > /home/hamradio/.asoundrc << 'ASOUNDRC'
# ALSA configuration redirecting to PulseAudio
# This allows FLdigi to find an audio device via ALSA
# even when no real hardware is present

pcm.!default {
    type pulse
    fallback "sysdefault"
    hint {
        show on
        description "Default ALSA Output (PulseAudio)"
    }
}

ctl.!default {
    type pulse
    fallback "sysdefault"
}

# Null device fallback if PulseAudio is not available
pcm.null {
    type null
}
ASOUNDRC

chmod 644 /home/hamradio/.asoundrc
echo -e "${GREEN}  ✓ ALSA configured for PulseAudio${NC}"

# =================================================================
# Start Xvfb virtual display for GUI applications
# FLdigi and QSSTV require an X11 display to launch.
# Xvfb provides a virtual framebuffer with no real output.
# =================================================================
echo -e "\n${YELLOW}[6b/7] Starting virtual display (Xvfb)...${NC}"

# Kill any existing Xvfb on display :99
pkill -f "Xvfb :99" 2>/dev/null || true
rm -f /tmp/.X99-lock 2>/dev/null || true

# Start Xvfb on display :99
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp &
XVFB_PID=$!

# Wait briefly for Xvfb to initialise
sleep 1

# Verify Xvfb started
if kill -0 $XVFB_PID 2>/dev/null; then
    echo -e "${GREEN}  ✓ Xvfb started (PID: $XVFB_PID, DISPLAY=:99)${NC}"
    export DISPLAY=:99
else
    echo -e "${YELLOW}  ⚠ Xvfb failed to start${NC}"
    echo "  GUI applications (FLdigi, QSSTV) will not work"
    echo "  without a display server."
fi
# =================================================================
# [7/7] Starting application
# =================================================================
echo -e "\n${YELLOW}[7/7] Starting application...${NC}"
echo -e "\n${GREEN}Configuration Summary:${NC}"
echo "  Flask Environment : ${FLASK_ENV:-production}"
echo "  Debug Mode        : ${FLASK_DEBUG:-0}"
echo "  SSL Enabled       : ${USE_SSL:-true}"
echo "  Mock Devices      : ${USE_MOCK_DEVICES:-true}"
echo "  Database          : ${DATABASE_URL}"
echo "  Listen Address    : ${FLASK_HOST:-0.0.0.0}:${FLASK_PORT:-5000}"
echo "  OpenWebRX URL     : ${OPENWEBRX_URL:-http://openwebrx:8073}"
echo "  Secret Key        : [SECURED] (${KEY_LENGTH} characters)"

echo -e "\n${GREEN}=================================================${NC}"
echo -e "${GREEN}Starting Ham Radio Application...${NC}"
echo -e "${GREEN}=================================================${NC}\n"

exec "$@"
