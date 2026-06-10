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
# 6/7 a) RTL-SDR detection
# ---------------------------------------------------------------
echo -e "\n${YELLOW}[6/7] Initializing devices...${NC}"
echo -e "\n${BLUE}[6a/7]--- RTL-SDR Status ---${NC}"

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
            echo -e "${GREEN} ✓ RTL-SDR detected:${NC}"
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
        echo -e "${GREEN} ✓ RTL-SDR symlink: \
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
    echo -e "${GREEN} ✓ RTL-SDR symlink found: $(ls /dev/rtlsdr*)${NC}"
fi

# ---------------------------------------------------------------
# GPS device
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# GPS Serial Port Check
# ---------------------------------------------------------------
echo -e "\n${BLUE} [6b/7] --- GPS Status ---${NC}"

GPS_PORT="${GPS_SERIAL_PORT:-/dev/ttyAMA0}"
GPS_SOURCE="${GPS_SOURCE:-uart}"

if [ "$GPS_SOURCE" = "uart" ]; then
    if [ -e "$GPS_PORT" ]; then
        echo -e "${GREEN}  ✓ GPS port found: $GPS_PORT${NC}"

        # Check if serial console is using the port
        # This is the most common cause of the 'no data' error
        PORT_NAME=$(basename "$GPS_PORT")
        if systemctl is-active --quiet \
                "serial-getty@${PORT_NAME}.service" \
                2>/dev/null; then
            echo -e "${YELLOW}  ⚠ WARNING: Serial console is active on $GPS_PORT${NC}"
            echo "  This will conflict with GPS!"
            echo "  Fix on host:"
            echo "    sudo systemctl stop serial-getty@${PORT_NAME}.service"
            echo "    sudo systemctl disable serial-getty@${PORT_NAME}.service"
        else
            echo -e "${GREEN}  ✓ No serial console conflict${NC}"
        fi

        # Check permissions
        if [ -r "$GPS_PORT" ] && [ -w "$GPS_PORT" ]; then
            echo -e "${GREEN} ✓ Port is readable and writable${NC}"
        else
            echo -e "${YELLOW}  ⚠ Permission issue on $GPS_PORT${NC}"
            echo "  Add to docker-compose.yml devices:"
            echo "    - $GPS_PORT:$GPS_PORT"
        fi
    else
        echo -e "${YELLOW}  ⚠ GPS port not found: $GPS_PORT${NC}"
        echo "  Mock GPS will be used"
    fi
else
    echo "  GPS source: $GPS_SOURCE (not UART)"
fi

# ---------------------------------------------------------------
# [6c/7] Radio device
# ---------------------------------------------------------------
echo -e "\n${BLUE}[6c/7]--- Radio Status ---${NC}"
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
# [6d/7]Go toolchain check (for GrayWolf plugin)
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# Go toolchain check (for GrayWolf and other Go plugins)
# ---------------------------------------------------------------
echo -e "\n${BLUE}[6d/7]--- Checking Go Toolchain ---${NC}"

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
# [6e/7] OpenWebRX sidecar availability check
# ---------------------------------------------------------------
echo -e "\n${BLUE}[6e/7]--- Check OpenWebRX Sidecar ---${NC}"
OWRX_URL="${OPENWEBRX_URL:-http://0.0.0.0:8073}"
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
# [6c/7] Starting PulseAudio with null sink for FLdigi
#
# FLdigi requires an audio device to initialise.
# PulseAudio with a null sink provides a virtual audio
# device that satisfies FLdigi without real hardware.
#
# The null sink accepts all audio output without
# actually playing anything — perfect for Docker.
# =================================================================
echo -e "\n${YELLOW}[6f/7] Starting PulseAudio virtual audio...${NC}"

# Kill any stale PulseAudio instance
pulseaudio --kill 2>/dev/null || true
pkill -x pulseaudio 2>/dev/null || true
sleep 0.5

# Remove stale PulseAudio socket files
rm -f /run/user/1000/pulse/pid 2>/dev/null || true
rm -f /tmp/pulse-* 2>/dev/null || true

if command -v pulseaudio >/dev/null 2>&1; then

    # Write PulseAudio config that loads null sink on start
    mkdir -p /home/hamradio/.config/pulse

    cat > /home/hamradio/.config/pulse/default.pa << 'PA_CONFIG'
# PulseAudio config for FLdigi in Docker
# Provides virtual audio without real hardware

# Load basic modules
load-module module-native-protocol-unix
load-module module-always-sink

# Virtual null output sink (FLdigi sends audio here)
load-module module-null-sink \
    sink_name=fldigi_out \
    sink_properties=device.description="FLdigi_Output"

# Virtual null input source (FLdigi reads from here)
load-module module-null-source \
    source_name=fldigi_in \
    source_properties=device.description="FLdigi_Input"

# Set as defaults
set-default-sink fldigi_out
set-default-source fldigi_in
PA_CONFIG

    cat > /home/hamradio/.config/pulse/client.conf << 'PA_CLIENT'
# Prevent PulseAudio from auto-spawning when not running
autospawn = yes
daemon-binary = /usr/bin/pulseaudio
PA_CLIENT

    # Start PulseAudio daemon
    pulseaudio \
        --start \
        --log-target=syslog \
        --log-level=error \
        --exit-idle-time=-1 \
        --disallow-exit \
        2>/dev/null

    # Wait for PulseAudio to be ready
    PA_READY=false
    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        if pactl info >/dev/null 2>&1; then
            PA_READY=true
            break
        fi
    done

    if [ "$PA_READY" = "true" ]; then
        echo -e "${GREEN}  ✓ PulseAudio started${NC}"

        # Load null sink if not already loaded by config
        pactl load-module module-null-sink \
            sink_name=fldigi_out \
            sink_properties=device.description="FLdigi_Output" \
            2>/dev/null || true

        pactl load-module module-null-source \
            source_name=fldigi_in \
            source_properties=device.description="FLdigi_Input" \
            2>/dev/null || true

        # Set defaults
        pactl set-default-sink fldigi_out 2>/dev/null || true
        pactl set-default-source fldigi_in 2>/dev/null || true

        # Show loaded sinks for verification
        echo "  Audio sinks:"
        pactl list sinks short 2>/dev/null | \
            awk '{print "    " $0}' || true

    else
        echo -e "${YELLOW}  ⚠ PulseAudio failed to start${NC}"
        echo "  FLdigi may have audio initialisation errors"
        echo "  (non-fatal — FLdigi will still run)"
    fi

    # Write ALSA config that routes to PulseAudio
    # This is the KEY fix — tells ALSA to use PulseAudio
    # as its backend so FLdigi finds 'card 0'
    cat > /home/hamradio/.asoundrc << 'ALSA_CONFIG'
# ALSA configuration for Docker
# Routes all ALSA audio through PulseAudio
# This prevents the "cannot find card '0'" errors

# Default PCM device: PulseAudio
pcm.!default {
    type pulse
    hint {
        show on
        description "Default (PulseAudio)"
    }
}

# Default CTL device: PulseAudio
ctl.!default {
    type pulse
}

# Explicit PulseAudio device
pcm.pulse {
    type pulse
}
ctl.pulse {
    type pulse
}

# Null device fallback (if PulseAudio unavailable)
pcm.null {
    type null
}
ctl.null {
    type null
}
ALSA_CONFIG

    echo -e "${GREEN}  ✓ ALSA configured for PulseAudio${NC}"
    echo "  ~/.asoundrc written"

else
    echo -e "${YELLOW}  ⚠ PulseAudio not installed${NC}"
    echo "  Add to Dockerfile:"
    echo "    apt-get install -y pulseaudio pulseaudio-utils"

    # Write minimal ALSA config with null device
    # so FLdigi does not crash
    cat > /home/hamradio/.asoundrc << 'ALSA_NULL'
# Minimal ALSA config — no PulseAudio available
# Uses null device so FLdigi does not crash on audio init
pcm.!default {
    type null
}
ctl.!default {
    type null
}
pcm.null { type null }
ALSA_NULL

    echo "  ~/.asoundrc (null) written"
fi

# Suppress ALSA error spam by setting ALSA_CARD
# This tells ALSA which card to default to
export ALSA_CARD=0
export ALSA_PCM_CARD=0
export ALSA_CTL_CARD=0

# =================================================================
# [6g/7] Verify Qt xcb plugin is loadable
# =================================================================
echo -e "\n${BLUE}[6g/7] --- Qt Platform Check ---${NC}"

if [ "$XVFB_READY" = "true" ]; then
    # Check xcb library exists
    XCB_LIB=$(find /usr -name "libqxcb.so" \
        -type f 2>/dev/null | head -1)

    if [ -n "$XCB_LIB" ]; then
        echo -e "${GREEN}  ✓ Qt xcb plugin: $XCB_LIB${NC}"
        # Set QT_PLUGIN_PATH so Qt can find it
        QT_PLUGIN_DIR=$(dirname $(dirname "$XCB_LIB"))
        export QT_PLUGIN_PATH="$QT_PLUGIN_DIR"
        echo "  QT_PLUGIN_PATH=$QT_PLUGIN_PATH"
    else
        echo -e "${YELLOW}  ⚠ Qt xcb plugin not found${NC}"
        echo "  Add to Dockerfile:"
        echo "    apt-get install -y libxcb1 libxcb-icccm4 \\"
        echo "      libxcb-image0 libxcb-keysyms1 \\"
        echo "      libxcb-randr0 libxcb-render-util0 \\"
        echo "      libxcb-shape0 libxcb-xkb1 \\"
        echo "      libxkbcommon-x11-0"
    fi

    # Export for child processes
    export QT_QPA_PLATFORM=xcb
    export QT_ACCESSIBILITY=0
    echo "  QT_QPA_PLATFORM=xcb"
else
    echo -e "${YELLOW}  ⚠ Skipping Qt check (no display)${NC}"
fi

# =================================================================
# [6h/7] Starting virtual display (Xvfb) for Qt applications
#
# WSJT-X, FLdigi, and QSSTV all require an X11 display.
# Xvfb provides a virtual framebuffer — no monitor needed.
# DISPLAY must be :99 (not :0) inside the container.
# =================================================================
echo -e "\n${YELLOW}[6h/7] Starting virtual display (Xvfb)...${NC}"

XVFB_DISPLAY=":99"
XVFB_READY=false

# Ensure X11 socket directory exists with correct permissions
# This MUST be done before starting Xvfb
mkdir -p /tmp/.X11-unix 2>/dev/null || true
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

# Remove stale lock files from previous container runs
rm -f /tmp/.X99-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X99 2>/dev/null || true

if command -v Xvfb >/dev/null 2>&1; then

    # Start Xvfb on display :99
    Xvfb ${XVFB_DISPLAY} \
        -screen 0 1280x1024x24 \
        -nolisten tcp \
        -ac \
        +extension GLX \
        +extension RANDR \
        2>/tmp/xvfb.log &

    XVFB_PID=$!

    # Wait up to 8 seconds for Xvfb to be ready
    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        # Check socket file exists (Xvfb is ready)
        if [ -S "/tmp/.X11-unix/X99" ]; then
            XVFB_READY=true
            break
        fi
        # Also check lock file as fallback
        if [ -f "/tmp/.X99-lock" ]; then
            XVFB_READY=true
            break
        fi
    done

    if [ "$XVFB_READY" = "true" ]; then
        # Export DISPLAY so all child processes use :99
        export DISPLAY="${XVFB_DISPLAY}"
        echo -e "${GREEN}  ✓ Xvfb running on ${XVFB_DISPLAY} (PID: ${XVFB_PID})${NC}"
        echo "  DISPLAY=${DISPLAY}"

        # Verify xcb plugin is loadable
        if command -v python3 >/dev/null 2>&1; then
            python3 -c "
import subprocess, os
env = os.environ.copy()
env['DISPLAY'] = '${XVFB_DISPLAY}'
r = subprocess.run(
    ['xdpyinfo'],
    capture_output=True, env=env, timeout=3
)
if r.returncode == 0:
    print('  ✓ X11 display verified with xdpyinfo')
else:
    print('  ⚠ xdpyinfo failed (non-fatal)')
" 2>/dev/null || true
        fi
    else
        echo -e "${YELLOW}  ⚠ Xvfb did not start in time${NC}"
        cat /tmp/xvfb.log 2>/dev/null | head -10
        echo "  Qt GUI applications will not work."
        echo "  Ensure /tmp/.X11-unix exists with mode 1777"
    fi

else
    echo -e "${YELLOW}  ⚠ Xvfb not installed${NC}"
    echo "  Add to Dockerfile:"
    echo "    apt-get install -y xvfb"
fi
# =================================================================
# [6i/7] Start VNC server for remote GUI access
# =================================================================
echo -e "\n${YELLOW}[6i/7] Starting VNC server...${NC}"

if command -v vncserver >/dev/null 2>&1; then
    # Start VNC server on display :99 (same as Xvfb)
    # SecurityTypes None allows passwordless access (for internal use only)
    export VNCPASSWD="hamradio"
    vncserver :99 \
        -geometry 1024x768 \
        -depth 24 \
        -SecurityTypes None \
        2>/dev/null &
    sleep 2
    
    if ps aux | grep -q "[V]ncserver.*:99"; then
        echo -e "${GREEN}  ✓ VNC server started on :99 (port 5999)${NC}"
        echo "    Connect with: vncviewer localhost:5999"
    else
        echo -e "${YELLOW}  ⚠ VNC server failed to start${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ VNC server not installed${NC}"
    echo "  Add to Dockerfile: apt-get install -y tigervnc-standalone-server"
fi

# =================================================================
# [6j/7] Initialize FLdigi XML-RPC configuration
# =================================================================
echo -e "\n${YELLOW}[6j/7] Configuring FLdigi XML-RPC...${NC}"

if command -v fldigi >/dev/null 2>&1; then
    # FLdigi config directory
    FLDIGI_CONFIG="$HOME/.fldigi"
    FLDIGI_DEF="$FLDIGI_CONFIG/fldigi_def.xml"
    
    # Create initial config by running FLdigi in headless mode
    if [ ! -f "$FLDIGI_DEF" ]; then
        echo "  Initializing FLdigi configuration..."
        timeout 5 fldigi --no-gui >/dev/null 2>&1 || true
        sleep 2
        pkill -f "fldigi" 2>/dev/null || true
        sleep 1
    fi
    
    # Enable XML-RPC in config if file exists
    if [ -f "$FLDIGI_DEF" ]; then
        # Enable XML-RPC server
        sed -i 's/<xmlrpc_server>[0-9]/<xmlrpc_server>1/g' "$FLDIGI_DEF"
        # Ensure port is set to 7362
        sed -i 's/<xmlrpc_port>[0-9]*/<xmlrpc_port>7362/g' "$FLDIGI_DEF"
        echo -e "${GREEN}  ✓ FLdigi XML-RPC enabled (port 7362)${NC}"
    else
        echo -e "${YELLOW}  ⚠ FLdigi config not found${NC}"
        echo "    Will be created when FLdigi starts"
    fi
else
    echo -e "${YELLOW}  ⚠ FLdigi not installed${NC}"
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
