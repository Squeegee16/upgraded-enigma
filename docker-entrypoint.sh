#!/bin/bash
# Ham Radio Application - Docker Entrypoint Script
# =================================================
# Runs before the Flask application starts.
# Sets up display, audio, GPS, and other services.
#
# IMPORTANT: Do NOT use 'set -e' globally.
# All optional steps use '|| true' to prevent
# the container from restarting on non-fatal failures.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Ham Radio Operator Web Application${NC}"
echo -e "${GREEN}Docker Container Initialization${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

# =================================================================
# [0/7] Check user and permissions
# =================================================================
echo -e "${YELLOW}[0/7] Checking user and permissions...${NC}"
echo "Running as user: $(whoami) (UID: $(id -u), GID: $(id -g))"

if [ ! -w "/data" ]; then
    echo -e "${RED}ERROR: /data is not writable${NC}"
    echo "Run on host: sudo chown -R 1000:1000 ./data"
    exit 1
fi
echo -e "${GREEN}✓ User and permissions validated${NC}"
echo ""

# =================================================================
# [1/7] Secret key management
# =================================================================
echo -e "${YELLOW}[1/7] Managing secret key...${NC}"

SECRET_KEY_FILE="/data/secret_key"

if [ -n "$SECRET_KEY" ] && \
   [ "$SECRET_KEY" != "change-this-in-production" ]; then
    echo "Using SECRET_KEY from environment"
    if [ ! -f "$SECRET_KEY_FILE" ]; then
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
    fi
else
    if [ -f "$SECRET_KEY_FILE" ]; then
        echo -e "${GREEN}✓ Existing secret key found${NC}"
        export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    else
        echo "Generating new secret key..."
        NEW_KEY=$(python3 -c \
            "import secrets; print(secrets.token_hex(32))")
        echo "$NEW_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
        export SECRET_KEY="$NEW_KEY"
        echo -e "${GREEN}✓ New secret key generated${NC}"
    fi
fi

KEY_LENGTH=$(echo -n "$SECRET_KEY" | wc -c)
if [ "$KEY_LENGTH" -lt 32 ]; then
    echo -e "${RED}ERROR: SECRET_KEY too short${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Secret key validated (length: ${KEY_LENGTH})${NC}"
echo ""

# =================================================================
# [2/7] Validate environment
# =================================================================
echo -e "${YELLOW}[2/7] Validating environment...${NC}"
echo -e "${GREEN}✓ Environment validated${NC}"
echo ""
# =================================================================
# [2b/7] Verify critical binary versions
# =================================================================
echo -e "${YELLOW}[2b/7] Verifying binary versions...${NC}"

# Check rigctld version
if command -v rigctld >/dev/null 2>&1; then
    RIGCTLD_PATH=$(which rigctld)
    RIGCTLD_VER=$(rigctld --version 2>&1 | \
        grep -oP 'Hamlib \K[\d.]+' | head -1 || echo "unknown")
    echo "  rigctld path    : $RIGCTLD_PATH"
    echo "  rigctld version : $RIGCTLD_VER"

    if [ "$RIGCTLD_VER" = "4.5.4" ]; then
        echo -e "${RED}  ✗ WRONG VERSION: 4.5.4 detected!${NC}"
        echo -e "${RED}    System Hamlib is overriding compiled version${NC}"
        echo -e "${RED}    Fix: Rebuild image with --no-cache${NC}"
    elif [ "$RIGCTLD_VER" = "4.7.0" ]; then
        echo -e "${GREEN}  ✓ rigctld $RIGCTLD_VER (correct)${NC}"
    else
        echo -e "${YELLOW}  ⚠ rigctld $RIGCTLD_VER (unexpected)${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ rigctld not found in PATH${NC}"
fi
echo ""
# =================================================================
# [3/7] Set up directories
# =================================================================
echo -e "${YELLOW}[3/7] Setting up directories...${NC}"

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
echo ""

# =================================================================
# [4/7] SSL certificates
# =================================================================
echo -e "${YELLOW}[4/7] Checking SSL certificates...${NC}"

SSL_CERT="${SSL_CERT:-/data/certs/cert.pem}"
SSL_KEY="${SSL_KEY:-/data/certs/key.pem}"

if [ "${USE_SSL:-true}" = "true" ]; then
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo "Generating self-signed SSL certificate..."
        openssl req -x509 -newkey rsa:4096 -nodes \
            -out "$SSL_CERT" \
            -keyout "$SSL_KEY" \
            -days 365 \
            -subj "/C=CA/ST=Province/L=City/O=HamRadio/CN=localhost" \
            2>/dev/null || true

        if [ -f "$SSL_CERT" ]; then
            chmod 644 "$SSL_CERT"
            chmod 600 "$SSL_KEY"
            echo -e "${GREEN}✓ SSL certificate generated${NC}"
        else
            echo -e "${YELLOW}⚠ SSL certificate generation failed${NC}"
        fi
    else
        echo -e "${GREEN}✓ SSL certificates found${NC}"
    fi
else
    echo "SSL disabled"
fi
echo ""

# =================================================================
# [5a/7] Database check
# =================================================================
echo -e "${YELLOW}[5a/7] Initializing database...${NC}"

DB_PATH=$(echo "${DATABASE_URL:-}" | sed 's|sqlite:///||')
if [ -n "$DB_PATH" ]; then
    echo "Database path: $DB_PATH"
    DB_DIR=$(dirname "$DB_PATH")
    if [ ! -d "$DB_DIR" ]; then
        echo -e "${RED}ERROR: DB directory missing: $DB_DIR${NC}"
        exit 1
    fi
    if [ -f "$DB_PATH" ]; then
        echo -e "${GREEN}✓ Database exists: $DB_PATH${NC}"
    else
        echo "Database will be created on first run"
    fi
fi
echo ""

# =================================================================
# [5b/7] Kill any services that may grab serial ports early
# This must run BEFORE GPS/Radio detection
# =================================================================
echo -e "${YELLOW}[5b/7] Releasing serial ports...${NC}"

# Kill gpsd if running - it can grab /dev/ttyAMA0 before our app
pkill -x gpsd 2>/dev/null || true
pkill -x gpsd.socket 2>/dev/null || true
sleep 1

# Confirm port is free
GPS_PORT="${GPS_SERIAL_PORT:-/dev/ttyAMA0}"
if command -v fuser >/dev/null 2>&1; then
    PORT_USER=$(fuser "$GPS_PORT" 2>/dev/null || echo "")
    if [ -n "$PORT_USER" ]; then
        echo -e "${YELLOW}  ⚠ Port $GPS_PORT still in use by PID: $PORT_USER${NC}"
    else
        echo -e "${GREEN}  ✓ Port $GPS_PORT is free${NC}"
    fi
fi
echo ""

# =================================================================
# [5c/7] RTL-SDR Python binding check
# =================================================================
echo -e "${BLUE}[5c/7]--- pyrtlsdr Check ---${NC}"

python3 -c "
import sys

# Test 1: Can we find the package?
import importlib.util
spec = importlib.util.find_spec('rtlsdr')
if spec:
    print('  pyrtlsdr package files: FOUND at', spec.origin)
else:
    print('  pyrtlsdr package files: NOT FOUND')
    print('  Add pyrtlsdr to requirements.txt')
    sys.exit(0)

# Test 2: Does it actually import?
try:
    import rtlsdr
    print('  pyrtlsdr import: OK')
    print('  RTL-SDR receive: ENABLED')
except OSError as e:
    print('  pyrtlsdr import: FAILED (native lib missing)')
    print('  Error:', str(e))
    print('  Fix: Ensure RTL-SDR source build ran ldconfig')
except ImportError as e:
    print('  pyrtlsdr import: FAILED')
    print('  Error:', str(e))
" 2>/dev/null || true
echo ""

# =================================================================
# [5d/7] RTL-SDR detection
# =================================================================
echo -e "${BLUE}[5d/7]--- RTL-SDR Status ---${NC}"

if [ -d "/dev/bus/usb" ]; then
    echo -e "${GREEN}✓ /dev/bus/usb accessible${NC}"

    USB_COUNT=$(find /dev/bus/usb -type c 2>/dev/null | wc -l)
    echo "  USB device nodes: $USB_COUNT"

    if command -v lsusb >/dev/null 2>&1; then
        RTL_USB=$(lsusb 2>/dev/null | \
            grep -iE "0bda:2832|0bda:2838|0bda:2839|realtek" \
            || true)
        if [ -n "$RTL_USB" ]; then
            echo -e "${GREEN}  ✓ RTL-SDR detected:${NC}"
            echo "    $RTL_USB"
        else
            echo -e "${YELLOW}  ⚠ RTL-SDR not detected via lsusb${NC}"
        fi
    fi

    if command -v rtl_test >/dev/null 2>&1; then
        RTL_RESULT=$(timeout 3 rtl_test -t 2>&1 || true)
        if echo "$RTL_RESULT" | grep -q "Found.*device"; then
            echo -e "${GREEN}  ✓ RTL-SDR responds to rtl_test${NC}"
        fi
    fi
else
    echo -e "${YELLOW}  ⚠ /dev/bus/usb not accessible${NC}"
fi
echo ""

# =================================================================
# [5e/7] GPS detection
# =================================================================
echo -e "${BLUE}--- GPS Status ---${NC}"
GPS_SOURCE="${GPS_SOURCE:-uart}"

if [ "$GPS_SOURCE" = "uart" ]; then
    if [ -e "$GPS_PORT" ]; then
        echo -e "${GREEN}  ✓ GPS port found: $GPS_PORT${NC}"
    else
        echo -e "${YELLOW}  ⚠ GPS port not found: $GPS_PORT${NC}"
        echo "  Mock GPS will be used"
    fi
else
    echo "  GPS source: $GPS_SOURCE"
fi
echo ""

# =================================================================
# [5f/7] Radio detection
# =================================================================
echo -e "${BLUE}--- Radio Status ---${NC}"
if [ "${USE_MOCK_DEVICES:-true}" = "false" ]; then
    RADIO_PORT="${RADIO_PORT:-/dev/ttyUSB1}"
    if [ -e "$RADIO_PORT" ]; then
        echo -e "${GREEN}  ✓ Radio port: $RADIO_PORT${NC}"
    else
        echo -e "${YELLOW}  ⚠ Radio port not found: $RADIO_PORT${NC}"
        echo "  Mock radio will be used"
    fi
else
    echo "  Mock radio enabled"
fi
echo ""

# =================================================================
# [5g/7] Go toolchain check
# =================================================================
echo -e "${BLUE}--- Go Toolchain ---${NC}"

if command -v go >/dev/null 2>&1; then
    GO_VER=$(go version 2>/dev/null | \
        grep -oP 'go\K[\d.]+' | head -1 || echo "unknown")
    echo -e "${GREEN}  ✓ Go ${GO_VER} available${NC}"
    echo "  GOROOT:  ${GOROOT:-$(go env GOROOT 2>/dev/null)}"
    echo "  GOPATH:  ${GOPATH:-not set}"
    echo "  GOCACHE: ${GOCACHE:-not set}"

    for go_dir in \
        "${GOPATH:-$HOME/go}" \
        "${GOCACHE:-$HOME/.cache/go-build}" \
        "$HOME/.local/bin"; do
        if [ ! -d "$go_dir" ]; then
            mkdir -p "$go_dir" 2>/dev/null || true
        fi
        if [ -w "$go_dir" ]; then
            echo -e "${GREEN}  ✓ Writable: $go_dir${NC}"
        else
            echo -e "${YELLOW}  ⚠ Not writable: $go_dir${NC}"
        fi
    done
    echo "  Full: $(go version 2>/dev/null || echo unknown)"
else
    echo -e "${YELLOW}  ⚠ Go not found in PATH${NC}"
fi
echo ""

# =================================================================
# [6a/7] Xvfb virtual display
# =================================================================
echo -e "${YELLOW}[6a/7] Starting virtual display (Xvfb)...${NC}"

DISPLAY_NUM="99"
LOCK_FILE="/tmp/.X${DISPLAY_NUM}-lock"
SOCKET_FILE="/tmp/.X11-unix/X${DISPLAY_NUM}"

if [ -f "$LOCK_FILE" ]; then
    STALE_PID=$(cat "$LOCK_FILE" 2>/dev/null | tr -d ' ' || echo "")
    if [ -n "$STALE_PID" ]; then
        if ! kill -0 "$STALE_PID" 2>/dev/null; then
            echo "  Removing stale X lock file (PID $STALE_PID not running)"
            rm -f "$LOCK_FILE" || true
            rm -f "$SOCKET_FILE" || true
        else
            echo "  Xvfb already running (PID $STALE_PID)"
            export DISPLAY=":${DISPLAY_NUM}"
            export QT_QPA_PLATFORM="xcb"
            export QT_ACCESSIBILITY="0"
            echo -e "${GREEN}  ✓ Using existing Xvfb on :${DISPLAY_NUM}${NC}"
        fi
    else
        rm -f "$LOCK_FILE" || true
        rm -f "$SOCKET_FILE" || true
    fi
fi

mkdir -p /tmp/.X11-unix 2>/dev/null || true
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

XVFB_STARTED=false

if command -v Xvfb >/dev/null 2>&1; then
    if [ ! -f "$LOCK_FILE" ]; then
        Xvfb ":${DISPLAY_NUM}" \
            -screen 0 1280x1024x24 \
            -nolisten tcp \
            -ac \
            2>/tmp/xvfb.log &
        XVFB_PID=$!

        for i in 1 2 3 4 5 6 7 8; do
            sleep 1
            if [ -S "$SOCKET_FILE" ] || [ -f "$LOCK_FILE" ]; then
                XVFB_STARTED=true
                break
            fi
        done
    else
        XVFB_STARTED=true
    fi

    if [ "$XVFB_STARTED" = "true" ]; then
        export DISPLAY=":${DISPLAY_NUM}"
        export QT_QPA_PLATFORM="xcb"
        export QT_ACCESSIBILITY="0"

        XCB_LIB=$(find /usr -name "libqxcb.so" \
            -type f 2>/dev/null | head -1 || echo "")
        if [ -n "$XCB_LIB" ]; then
            QT_PLUGIN_DIR=$(dirname "$(dirname "$XCB_LIB")")
            export QT_PLUGIN_PATH="$QT_PLUGIN_DIR"
        fi

        echo -e "${GREEN}  ✓ Xvfb on :${DISPLAY_NUM}${NC}"
        echo "  DISPLAY=${DISPLAY}"
    else
        echo -e "${YELLOW}  ⚠ Xvfb did not start (non-fatal)${NC}"
        if [ -f /tmp/xvfb.log ]; then
            head -3 /tmp/xvfb.log | sed 's/^/    /' || true
        fi
    fi
else
    echo -e "${YELLOW}  ⚠ Xvfb not installed${NC}"
fi
echo ""

# =================================================================
# [6b/7] VNC server (optional)
# =================================================================
echo -e "${YELLOW}[6b/7] Starting VNC server...${NC}"

if command -v x11vnc >/dev/null 2>&1 && \
        [ "$XVFB_STARTED" = "true" ]; then
    x11vnc \
        -display ":${DISPLAY_NUM}" \
        -nopw \
        -forever \
        -quiet \
        -bg 2>/dev/null || true
    echo -e "${GREEN}  ✓ VNC on :5900${NC}"
else
    echo -e "${YELLOW}  ⚠ VNC not available (non-fatal)${NC}"
fi
echo ""

# =================================================================
# [6c/7] PulseAudio virtual audio
# =================================================================
echo -e "${YELLOW}[6c/7] Starting PulseAudio virtual audio...${NC}"

PA_STARTED=false

if command -v pulseaudio >/dev/null 2>&1; then

    pulseaudio --kill 2>/dev/null || true
    pkill -x pulseaudio 2>/dev/null || true
    sleep 1

    rm -f /tmp/pulse-*/pid 2>/dev/null || true

    mkdir -p /home/hamradio/.config/pulse

    cat > /home/hamradio/.config/pulse/daemon.conf << 'EOF'
exit-idle-time = -1
realtime-scheduling = no
default-fragments = 2
default-fragment-size-msec = 25
EOF

    cat > /home/hamradio/.config/pulse/default.pa << 'EOF'
load-module module-native-protocol-unix
load-module module-null-sink sink_name=fldigi_out sink_properties=device.description="FLdigi_Output"
load-module module-null-source source_name=fldigi_in source_properties=device.description="FLdigi_Input"
load-module module-always-sink
set-default-sink fldigi_out
set-default-source fldigi_in
EOF

    pulseaudio \
        --start \
        --log-target=syslog \
        --log-level=error \
        --exit-idle-time=-1 \
        --disallow-exit \
        2>/dev/null || true

    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        if pactl info >/dev/null 2>&1; then
            PA_STARTED=true
            break
        fi
    done

    if [ "$PA_STARTED" = "true" ]; then
        echo -e "${GREEN}  ✓ PulseAudio started${NC}"

        pactl load-module module-null-sink \
            sink_name=fldigi_out \
            "sink_properties=device.description=FLdigi_Output" \
            2>/dev/null || true

        pactl load-module module-null-source \
            source_name=fldigi_in \
            "source_properties=device.description=FLdigi_Input" \
            2>/dev/null || true

        pactl set-default-sink fldigi_out 2>/dev/null || true
        pactl set-default-source fldigi_in 2>/dev/null || true
        echo -e "${GREEN}  ✓ PulseAudio null sink created${NC}"
    else
        echo -e "${YELLOW}  ⚠ PulseAudio did not start (non-fatal)${NC}"
        echo "  FLdigi will use null ALSA device instead"
    fi
else
    echo -e "${YELLOW}  ⚠ PulseAudio not installed${NC}"
fi

# Write ALSA config
if [ "$PA_STARTED" = "true" ]; then
    cat > /home/hamradio/.asoundrc << 'EOF'
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
pcm.pulse { type pulse }
ctl.pulse { type pulse }
pcm.null { type null }
EOF
    echo -e "${GREEN}  ✓ ALSA configured for PulseAudio${NC}"
else
    cat > /home/hamradio/.asoundrc << 'EOF'
pcm.!default { type null }
ctl.!default { type null }
pcm.null { type null }
EOF
    echo -e "${GREEN}  ✓ ALSA configured with null device${NC}"
fi
echo ""

# =================================================================
# [6d/7] FLdigi configuration
# =================================================================
echo -e "${YELLOW}[6d/7] Configuring FLdigi XML-RPC...${NC}"

FLDIGI_CONFIG_DIR="/data/plugins/fldigi/fldigi_home"
mkdir -p "$FLDIGI_CONFIG_DIR" 2>/dev/null || true

if command -v fldigi >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ FLdigi found: $(which fldigi)${NC}"
else
    echo -e "${YELLOW}  ⚠ FLdigi not found${NC}"
    echo "  Plugin will show install instructions"
fi
echo ""

# =================================================================
# [6e/7] Audio device detection
# =================================================================
echo -e "${YELLOW}[6e/7] Detecting audio devices...${NC}"

if command -v aplay >/dev/null 2>&1; then
    USB_CARD=$(aplay -l 2>/dev/null | \
        grep -iE "usb|soundblaster|creative" | \
        head -1 | \
        grep -oP 'card \K[0-9]+' || echo "")

    if [ -n "$USB_CARD" ]; then
        export AUDIO_OUTPUT_DEVICE="hw:${USB_CARD},0"
        export AUDIO_INPUT_DEVICE="hw:${USB_CARD},0"
        echo -e "${GREEN}  ✓ USB audio: card ${USB_CARD}${NC}"
        echo "  AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE}"
    else
        echo -e "${YELLOW}  ⚠ No USB audio card found${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ aplay not available${NC}"
fi
echo ""

# =================================================================
# [6f/7] OpenWebRX sidecar check
# =================================================================
OPENWEBRX_URL="${OPENWEBRX_URL:-}"
if [ -n "$OPENWEBRX_URL" ]; then
    echo -e "${YELLOW}--- OpenWebRX Sidecar ---${NC}"
    echo "  URL: $OPENWEBRX_URL"

    OWRX_CHECK=$(python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('${OPENWEBRX_URL}', timeout=3)
    print('reachable')
except Exception:
    print('unreachable')
" 2>/dev/null || echo "unreachable")

    if [ "$OWRX_CHECK" = "reachable" ]; then
        echo -e "${GREEN}  ✓ OpenWebRX is reachable${NC}"
    else
        echo -e "${YELLOW}  ⚠ OpenWebRX not reachable yet${NC}"
        echo "    (It may still be starting)"
    fi
    echo ""
fi

# =================================================================
# [7/7] Start application
# =================================================================
echo -e "${YELLOW}[7/7] Starting application...${NC}"
echo ""
echo "Configuration Summary:"
echo "  Flask Environment : ${FLASK_ENV:-production}"
echo "  Debug Mode        : ${FLASK_DEBUG:-0}"
echo "  SSL Enabled       : ${USE_SSL:-true}"
echo "  Mock Devices      : ${USE_MOCK_DEVICES:-true}"
echo "  Database          : ${DATABASE_URL:-not set}"
echo "  Listen Address    : ${FLASK_HOST:-0.0.0.0}:${FLASK_PORT:-5000}"
echo "  OpenWebRX URL     : ${OPENWEBRX_URL:-not configured}"
echo "  Secret Key        : [SECURED] (${KEY_LENGTH} characters)"
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Starting Ham Radio Application...${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

exec "$@"
