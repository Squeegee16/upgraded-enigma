#!/bin/bash
# Ham Radio Application - Docker Entrypoint Script
# =================================================
# NOTE: Do NOT use 'set -e' here.
# Many optional steps (PulseAudio, Xvfb, VNC) are
# non-fatal and will fail in some environments.
# 'set -e' would cause the container to restart on
# any non-fatal failure.
#
# Instead we check return codes explicitly where
# needed and use '|| true' for optional commands.

# Only enable xtrace in debug mode
# set -x  # Uncomment for verbose debugging

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
#echo -e "\n${BLUE}[6e/7]--- Check OpenWebRX Sidecar ---${NC}"
#OWRX_URL="${OPENWEBRX_URL:-http://0.0.0.0:8073}"
#echo "  OpenWebRX URL: $OWRX_URL"

# Non-fatal — openwebrx may still be starting
#OWRX_CHECK=$(python3 -c "
#import urllib.request, sys
#try:
#    r = urllib.request.urlopen('${OWRX_URL}', timeout=3)
#    print('reachable:' + str(r.status))
#except Exception as e:
#    print('unreachable:' + str(e))
#" 2>/dev/null || echo "unreachable:check failed")

#if echo "$OWRX_CHECK" | grep -q "^reachable:"; then
#    echo -e "${GREEN}  ✓ OpenWebRX is reachable${NC}"
#else
#    echo -e "${YELLOW}  ⚠ OpenWebRX not yet reachable${NC}"
#    echo "    (It may still be starting — this is normal)"
#    echo "    The plugin will retry when the page loads"
#fi

# =================================================================
# [6c/7] Starting PulseAudio virtual audio
#
# PulseAudio provides a virtual null audio device so FLdigi
# and other audio applications can initialise without real
# hardware. All commands use '|| true' so failure never
# causes the container to restart.
# =================================================================
echo ""
echo "[6c/7] Starting PulseAudio virtual audio..."

# Ensure we never exit due to PulseAudio failure
set +e

# Kill any stale PulseAudio from a previous run
pulseaudio --kill 2>/dev/null
pkill -x pulseaudio 2>/dev/null
sleep 1

# Remove stale socket files
rm -f /run/user/1000/pulse/pid 2>/dev/null
rm -f /tmp/pulse-*/pid 2>/dev/null

if command -v pulseaudio >/dev/null 2>&1; then

    # Create config directory
    mkdir -p /home/hamradio/.config/pulse

    # Write PulseAudio daemon config
    cat > /home/hamradio/.config/pulse/daemon.conf << 'PA_DAEMON'
# PulseAudio daemon config for Docker
# Prevent daemon from exiting when idle
exit-idle-time = -1
# Don't require real-time scheduling
realtime-scheduling = no
# Use lower latency
default-fragments = 2
default-fragment-size-msec = 25
PA_DAEMON

    # Write PulseAudio startup config
    cat > /home/hamradio/.config/pulse/default.pa << 'PA_CONFIG'
# PulseAudio startup for Docker
# Load minimum required modules

load-module module-native-protocol-unix

# Virtual null output (FLdigi audio output goes here)
load-module module-null-sink \
    sink_name=fldigi_out \
    sink_properties=device.description="FLdigi_Output"

# Virtual null input (FLdigi reads from here)
load-module module-null-source \
    source_name=fldigi_in \
    source_properties=device.description="FLdigi_Input"

# Always have a sink available
load-module module-always-sink

# Set defaults
set-default-sink fldigi_out
set-default-source fldigi_in
PA_CONFIG

    # Start PulseAudio — use || true so failure is non-fatal
    pulseaudio \
        --start \
        --log-target=syslog \
        --log-level=error \
        --exit-idle-time=-1 \
        --disallow-exit \
        2>/dev/null || true

    # Wait up to 8 seconds for PulseAudio to be ready
    PA_STARTED=false
    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        if pactl info >/dev/null 2>&1; then
            PA_STARTED=true
            break
        fi
    done

    if [ "$PA_STARTED" = "true" ]; then
        echo "  ✓ PulseAudio started"

        # Load null sink modules — ignore if already loaded
        pactl load-module module-null-sink \
            sink_name=fldigi_out \
            sink_properties=device.description="FLdigi_Output" \
            2>/dev/null || true

        pactl load-module module-null-source \
            source_name=fldigi_in \
            source_properties=device.description="FLdigi_Input" \
            2>/dev/null || true

        # Set defaults — ignore failures
        pactl set-default-sink fldigi_out 2>/dev/null || true
        pactl set-default-source fldigi_in 2>/dev/null || true

        echo "  ✓ PulseAudio null sink created"

    else
        echo "  ⚠ PulseAudio did not start (non-fatal)"
        echo "  FLdigi will use null ALSA device instead"
    fi

    # Write ALSA config regardless of PulseAudio status
    if [ "$PA_STARTED" = "true" ]; then
        cat > /home/hamradio/.asoundrc << 'ALSA_PA'
# ALSA -> PulseAudio (Docker)
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
pcm.pulse { type pulse }
ctl.pulse { type pulse }
pcm.null { type null }
ALSA_PA
        echo "  ✓ ALSA configured for PulseAudio"
    else
        cat > /home/hamradio/.asoundrc << 'ALSA_NULL'
# ALSA null device (no PulseAudio)
pcm.!default { type null }
ctl.!default { type null }
pcm.null { type null }
ALSA_NULL
        echo "  ✓ ALSA configured with null device"
    fi

else
    echo "  ⚠ PulseAudio not installed"
    echo "  Creating null ALSA config for FLdigi..."

    cat > /home/hamradio/.asoundrc << 'ALSA_BARE'
# Minimal ALSA null config
pcm.!default { type null }
ctl.!default { type null }
pcm.null { type null }
ALSA_BARE

    echo "  ✓ Null ALSA config written"
fi

# Re-enable exit on error for critical sections only
# (the database and application startup)
# Leave it off for the remaining optional sections

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
echo ""

set +e   # ← Always off for optional components

mkdir -p /tmp/.X11-unix 2>/dev/null || true
chmod 1777 /tmp/.X11-unix 2>/dev/null || true
rm -f /tmp/.X99-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X99 2>/dev/null || true

XVFB_STARTED=false

if command -v Xvfb >/dev/null 2>&1; then
    Xvfb :99 \
        -screen 0 1280x1024x24 \
        -nolisten tcp \
        -ac \
        2>/tmp/xvfb.log &
    XVFB_PID=$!

    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        if [ -S "/tmp/.X11-unix/X99" ] || \
           [ -f "/tmp/.X99-lock" ]; then
            XVFB_STARTED=true
            break
        fi
    done

    if [ "$XVFB_STARTED" = "true" ]; then
        export DISPLAY=":99"
        export QT_QPA_PLATFORM="xcb"
        export QT_ACCESSIBILITY="0"
        echo "  ✓ Xvfb started on :99"
        echo "  DISPLAY=:99"
    else
        echo "  ⚠ Xvfb did not start (non-fatal)"
        cat /tmp/xvfb.log 2>/dev/null | head -5 || true
    fi
else
    echo "  ⚠ Xvfb not installed (non-fatal)"
fi
# =================================================================
# [6i/7] Start VNC server for remote GUI access
# =================================================================
echo -e "\n${YELLOW}[6i/7] Starting VNC server...${NC}"

export VNCPASSWD="hamradio"
# VNC is completely optional — always || true
if command -v x11vnc >/dev/null 2>&1 && \
        [ "$XVFB_STARTED" = "true" ]; then
    x11vnc \
        -display :99 \
        -nopw \
        -forever \
        -quiet \
        -bg 2>/dev/null || true
    echo "  ✓ VNC started on :5900"
else
    echo "  ⚠ VNC not available (non-fatal)"
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
Fixing Docker Container Restart Loop at PulseAudio Step
Root Cause
The container is restarting because pulseaudio --start is exiting with a non-zero code which causes the set -e in docker-entrypoint.sh to abort the script. Docker then restarts the container, creating an infinite loop.

The set -e directive means any command that fails causes the entire script to exit immediately. PulseAudio startup is non-fatal but set -e treats it as fatal.

Fix: docker-entrypoint.sh
The fix has two parts:

Remove set -e from the entrypoint or wrap all non-fatal commands with || true
Fix the PulseAudio section to never cause the script to exit
Part A: Fix the script header
bash
Copy code
Download
#!/bin/bash
# Ham Radio Application - Docker Entrypoint Script
# =================================================
# NOTE: Do NOT use 'set -e' here.
# Many optional steps (PulseAudio, Xvfb, VNC) are
# non-fatal and will fail in some environments.
# 'set -e' would cause the container to restart on
# any non-fatal failure.
#
# Instead we check return codes explicitly where
# needed and use '|| true' for optional commands.

# Only enable xtrace in debug mode
# set -x  # Uncomment for verbose debugging
bash
Copy code
Download
Part B: Replace the entire PulseAudio section
bash
Copy code
Download
# =================================================================
# [6c/7] Starting PulseAudio virtual audio
#
# PulseAudio provides a virtual null audio device so FLdigi
# and other audio applications can initialise without real
# hardware. All commands use '|| true' so failure never
# causes the container to restart.
# =================================================================
echo ""
echo "[6c/7] Starting PulseAudio virtual audio..."

# Ensure we never exit due to PulseAudio failure
set +e

# Kill any stale PulseAudio from a previous run
pulseaudio --kill 2>/dev/null
pkill -x pulseaudio 2>/dev/null
sleep 1

# Remove stale socket files
rm -f /run/user/1000/pulse/pid 2>/dev/null
rm -f /tmp/pulse-*/pid 2>/dev/null

if command -v pulseaudio >/dev/null 2>&1; then

    # Create config directory
    mkdir -p /home/hamradio/.config/pulse

    # Write PulseAudio daemon config
    cat > /home/hamradio/.config/pulse/daemon.conf << 'PA_DAEMON'
# PulseAudio daemon config for Docker
# Prevent daemon from exiting when idle
exit-idle-time = -1
# Don't require real-time scheduling
realtime-scheduling = no
# Use lower latency
default-fragments = 2
default-fragment-size-msec = 25
PA_DAEMON

    # Write PulseAudio startup config
    cat > /home/hamradio/.config/pulse/default.pa << 'PA_CONFIG'
# PulseAudio startup for Docker
# Load minimum required modules

load-module module-native-protocol-unix

# Virtual null output (FLdigi audio output goes here)
load-module module-null-sink \
    sink_name=fldigi_out \
    sink_properties=device.description="FLdigi_Output"

# Virtual null input (FLdigi reads from here)
load-module module-null-source \
    source_name=fldigi_in \
    source_properties=device.description="FLdigi_Input"

# Always have a sink available
load-module module-always-sink

# Set defaults
set-default-sink fldigi_out
set-default-source fldigi_in
PA_CONFIG

    # Start PulseAudio — use || true so failure is non-fatal
    pulseaudio \
        --start \
        --log-target=syslog \
        --log-level=error \
        --exit-idle-time=-1 \
        --disallow-exit \
        2>/dev/null || true

    # Wait up to 8 seconds for PulseAudio to be ready
    PA_STARTED=false
    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        if pactl info >/dev/null 2>&1; then
            PA_STARTED=true
            break
        fi
    done

    if [ "$PA_STARTED" = "true" ]; then
        echo "  ✓ PulseAudio started"

        # Load null sink modules — ignore if already loaded
        pactl load-module module-null-sink \
            sink_name=fldigi_out \
            sink_properties=device.description="FLdigi_Output" \
            2>/dev/null || true

        pactl load-module module-null-source \
            source_name=fldigi_in \
            source_properties=device.description="FLdigi_Input" \
            2>/dev/null || true

        # Set defaults — ignore failures
        pactl set-default-sink fldigi_out 2>/dev/null || true
        pactl set-default-source fldigi_in 2>/dev/null || true

        echo "  ✓ PulseAudio null sink created"

    else
        echo "  ⚠ PulseAudio did not start (non-fatal)"
        echo "  FLdigi will use null ALSA device instead"
    fi

    # Write ALSA config regardless of PulseAudio status
    if [ "$PA_STARTED" = "true" ]; then
        cat > /home/hamradio/.asoundrc << 'ALSA_PA'
# ALSA -> PulseAudio (Docker)
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
pcm.pulse { type pulse }
ctl.pulse { type pulse }
pcm.null { type null }
ALSA_PA
        echo "  ✓ ALSA configured for PulseAudio"
    else
        cat > /home/hamradio/.asoundrc << 'ALSA_NULL'
# ALSA null device (no PulseAudio)
pcm.!default { type null }
ctl.!default { type null }
pcm.null { type null }
ALSA_NULL
        echo "  ✓ ALSA configured with null device"
    fi

else
    echo "  ⚠ PulseAudio not installed"
    echo "  Creating null ALSA config for FLdigi..."

    cat > /home/hamradio/.asoundrc << 'ALSA_BARE'
# Minimal ALSA null config
pcm.!default { type null }
ctl.!default { type null }
pcm.null { type null }
ALSA_BARE

    echo "  ✓ Null ALSA config written"
fi

# Re-enable exit on error for critical sections only
# (the database and application startup)
# Leave it off for the remaining optional sections
bash
Copy code
Download
Part C: Apply || true to ALL other optional sections
Every optional section in the entrypoint must be protected. Here is the complete safe pattern to apply:

bash
Copy code
Download
# =================================================================
# [6b/7] Starting Xvfb virtual display
# =================================================================
echo ""
echo "[6b/7] Starting virtual display (Xvfb)..."

set +e   # ← Always off for optional components

mkdir -p /tmp/.X11-unix 2>/dev/null || true
chmod 1777 /tmp/.X11-unix 2>/dev/null || true
rm -f /tmp/.X99-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X99 2>/dev/null || true

XVFB_STARTED=false

if command -v Xvfb >/dev/null 2>&1; then
    Xvfb :99 \
        -screen 0 1280x1024x24 \
        -nolisten tcp \
        -ac \
        2>/tmp/xvfb.log &
    XVFB_PID=$!

    for i in 1 2 3 4 5 6 7 8; do
        sleep 1
        if [ -S "/tmp/.X11-unix/X99" ] || \
           [ -f "/tmp/.X99-lock" ]; then
            XVFB_STARTED=true
            break
        fi
    done

    if [ "$XVFB_STARTED" = "true" ]; then
        export DISPLAY=":99"
        export QT_QPA_PLATFORM="xcb"
        export QT_ACCESSIBILITY="0"
        echo "  ✓ Xvfb started on :99"
        echo "  DISPLAY=:99"
    else
        echo "  ⚠ Xvfb did not start (non-fatal)"
        cat /tmp/xvfb.log 2>/dev/null | head -5 || true
    fi
else
    echo "  ⚠ Xvfb not installed (non-fatal)"
fi


# =================================================================
# [6a/7] VNC server (optional)
# =================================================================
echo ""
echo "[6a/7] Starting VNC server..."

# VNC is completely optional — always || true
if command -v x11vnc >/dev/null 2>&1 && \
        [ "$XVFB_STARTED" = "true" ]; then
    x11vnc \
        -display :99 \
        -nopw \
        -forever \
        -quiet \
        -bg 2>/dev/null || true
    echo "  ✓ VNC started on :5900"
else
    echo "  ⚠ VNC not available (non-fatal)"
fi


# =================================================================
# [6d/7] FLdigi XML-RPC config
# =================================================================
echo ""
echo "[6d/7] Configuring FLdigi XML-RPC..."

FLDIGI_HOME="/data/plugins/fldigi/fldigi_home"
mkdir -p "$FLDIGI_HOME" 2>/dev/null || true

if command -v fldigi >/dev/null 2>&1; then
    echo "  ✓ FLdigi found: $(which fldigi)"
else
    echo "  ⚠ FLdigi not found (plugin will show install instructions)"
fi


# =================================================================
# [6e/7] Audio device detection (USB SoundBlaster etc.)
# =================================================================
echo ""
echo "[6e/7] Detecting audio devices..."

set +e

if command -v aplay >/dev/null 2>&1; then
    USB_CARD=$(aplay -l 2>/dev/null | \
        grep -iE "usb|soundblaster|creative" | \
        head -1 | \
        grep -oP 'card \K[0-9]+' 2>/dev/null || echo "")

    if [ -n "$USB_CARD" ]; then
        export AUDIO_OUTPUT_DEVICE="hw:${USB_CARD},0"
        export AUDIO_INPUT_DEVICE="hw:${USB_CARD},0"
        echo "  ✓ USB audio detected: card ${USB_CARD}"
        echo "  AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE}"
    else
        echo "  ⚠ No USB audio card found"
    fi
else
    echo "  ⚠ aplay not available"
fi


# =================================================================
# [6f/7] Go toolchain check
# =================================================================
echo ""
echo "[6f/7] Checking Go toolchain..."

set +e

if command -v go >/dev/null 2>&1; then
    GO_VER=$(go version 2>/dev/null | \
        grep -oP 'go\K[\d.]+' | head -1 || echo "unknown")
    echo "  ✓ Go ${GO_VER} available"
    echo "  GOPATH:  ${GOPATH:-not set}"
    echo "  GOCACHE: ${GOCACHE:-not set}"
    echo "  Full: $(go version 2>/dev/null || echo unknown)"
else
    echo "  ⚠ Go not found"
fi

# =================================================================
# [7/7] Starting application
# =================================================================
echo ""
echo "[7/7] Starting application..."
echo ""
echo "Configuration Summary:"
echo "  Flask Environment : ${FLASK_ENV:-production}"
echo "  Debug Mode        : ${FLASK_DEBUG:-0}"
echo "  SSL Enabled       : ${USE_SSL:-true}"
echo "  Mock Devices      : ${USE_MOCK_DEVICES:-true}"
echo "  Database          : ${DATABASE_URL}"
echo "  Listen Address    : ${FLASK_HOST:-0.0.0.0}:${FLASK_PORT:-5000}"
echo "  OpenWebRX URL     : ${OPENWEBRX_URL:-not configured}"
echo "  Secret Key        : [SECURED] (${#SECRET_KEY} characters)"
echo ""
echo "================================================="
echo "Starting Ham Radio Application..."
echo "================================================="
echo ""

# Execute the main application command
# Use 'exec' so the application is PID 1 and receives
# Docker stop signals correctly
exec "$@"
