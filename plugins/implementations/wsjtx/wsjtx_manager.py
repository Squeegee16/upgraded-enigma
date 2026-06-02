"""
WSJT-X Manager
===============
Manages WSJT-X process lifecycle, UDP communication,
configuration, and data routing.

The manager coordinates:
    - WSJT-X process start/stop
    - UDP listener lifecycle
    - QSO logging integration
    - Configuration management
    - Status monitoring

Reference:
    https://github.com/WSJTX/wsjtx
"""

import os
import json
import shutil
import threading
import subprocess
import time
from datetime import datetime

from plugins.implementations.wsjtx.udp_listener import WSJTXUDPListener
from plugins.implementations.wsjtx.packet_decoder import WSJTXPacketDecoder


class WSJTXManager:
    """
    Manages WSJT-X process and data routing.

    Provides a unified interface for the plugin to
    interact with WSJT-X including process management,
    configuration, and real-time data access.
    """

    def __init__(self, config_dir, binary_path=None):
        """
        Initialize WSJT-X manager.

        Args:
            config_dir: Plugin data directory
            binary_path: Path to WSJT-X binary
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('wsjtx') or
            '/usr/bin/wsjtx'
        )

        # Process management
        self._process = None
        self._process_lock = threading.Lock()

        # UDP Listener (handles WSJT-X data stream)
        self._listener = None

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Status
        self._status = {
            'process_running': False,
            'udp_listening': False,
            'wsjtx_connected': False,
            'mode': None,
            'frequency': None,
            'de_call': None,
            'de_grid': None,
            'transmitting': False,
            'decoding': False,
            'pid': None,
            'version': None,
            'last_check': None,
            'error': None
        }

        # Pending QSOs for logbook
        self._pending_qsos = []
        self._qso_lock = threading.Lock()

        # Load configuration
        self.config = self._load_config()
        os.makedirs(config_dir, exist_ok=True)

    def _load_config(self):
        """
        Load WSJT-X plugin configuration.

        Returns:
            dict: Configuration with defaults
        """
        config_file = os.path.join(
            self.config_dir, 'wsjtx_config.json'
        )

        defaults = {
            # UDP settings
            'udp_host': '0.0.0.0',
            'udp_port': 2237,
            'multicast_group': None,

            # Launch settings
            'launch_mode': 'connect',   # 'launch' or 'connect'
            'display': ':0',

            # Station settings
            'callsign': '',
            'grid': '',

            # Plugin behavior
            'auto_start': False,
            'auto_listen': True,
            'auto_log_qsos': True,  # Auto-log QSO_LOGGED packets
            'show_cq_only': False,  # Filter to CQ spots only

            # Display settings
            'max_spots': 100,
            'spot_age_limit': 300,  # Seconds to keep spots
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[WSJTX][init] Config load error: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration to file.

        Args:
            config_data: Configuration dictionary

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(
            self.config_dir, 'wsjtx_config.json'
        )

        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print("[WSJTX][init] ✓ Config saved")
            return True
        except Exception as e:
            print(f"[WSJTX][init] Config save error: {e}")
            return False

    def _add_log(self, message, level='info'):
        """
        Add entry to in-memory log buffer.

        Args:
            message: Log message
            level: Severity (info, warning, error)
        """
        with self._log_lock:
            self._logs.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': str(message)
            })

            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """
        Get recent log entries.

        Returns:
            list: Log entries newest first
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def start_listener(self):
        """
        Start the UDP listener for WSJT-X data.

        Creates and starts the UDP listener which
        receives decoded messages from WSJT-X.

        Returns:
            tuple: (success, message)
        """
        if self._listener and self._listener._running:
            return False, "Listener already running"

        try:
            self._listener = WSJTXUDPListener(
                host=self.config.get('udp_host', '0.0.0.0'),
                port=self.config.get('udp_port', 2237),
                multicast_group=self.config.get('multicast_group')
            )

            # Register callback for QSO logging
            self._listener.register_callback(
                'on_qso_logged',
                self._on_qso_logged
            )

            # Register callback for status updates
            self._listener.register_callback(
                'on_status',
                self._on_status_update
            )

            if self._listener.start():
                self._status['udp_listening'] = True
                self._add_log(
                    f"[WSJTX][init] UDP listener started on port "
                    f"{self.config.get('udp_port', 2237)}"
                )
                return True, "[WSJTX][init] UDP listener started"
            else:
                return False, "[WSJTX][init] Failed to start UDP listener"

        except Exception as e:
            error = str(e)
            self._add_log(f"[WSJTX][init] Listener error: {error}", 'error')
            return False, error

    def stop_listener(self):
        """
        Stop the UDP listener.

        Returns:
            tuple: (success, message)
        """
        if not self._listener:
            return False, "[WSJTX][init] Listener not running"

        try:
            self._listener.stop()
            self._listener = None
            self._status['udp_listening'] = False
            self._status['wsjtx_connected'] = False
            self._add_log("UDP listener stopped")
            return True, "Listener stopped"
        except Exception as e:
            return False, str(e)

    def _on_qso_logged(self, packet):
        """
        Callback for QSO logged packets from WSJT-X.

        Called when WSJT-X logs a QSO internally.
        Adds to pending QSOs for logbook integration.

        Args:
            packet: Decoded QSO_LOGGED packet data
        """
        with self._qso_lock:
            self._pending_qsos.append(packet)

        callsign = packet.get('dx_call', 'Unknown')
        mode = packet.get('mode', '')
        self._add_log(
            f"QSO logged by WSJT-X: {callsign} {mode}"
        )

    def _on_status_update(self, packet):
        """
        Callback for status update packets.

        Updates internal status from WSJT-X status
        messages for real-time monitoring.

        Args:
            packet: Decoded STATUS packet data
        """
        self._status['wsjtx_connected'] = True
        self._status['mode'] = packet.get('mode')
        self._status['frequency'] = packet.get('dial_frequency')
        self._status['de_call'] = packet.get('de_call')
        self._status['de_grid'] = packet.get('de_grid')
        self._status['transmitting'] = packet.get('transmitting', False)
        self._status['decoding'] = packet.get('decoding', False)

    def get_pending_qsos(self):
        """
        Get and clear pending QSO log entries.

        Returns:
            list: Pending QSO data dictionaries
        """
        with self._qso_lock:
            qsos = list(self._pending_qsos)
            self._pending_qsos.clear()
            return qsos

    def start_wsjtx(self):
        """
        Launch WSJT-X with correct X11 display.

        Verifies that:
        1. WSJT-X binary exists
        2. An X11 display is available (Xvfb :99)
        3. Qt xcb plugin is loadable

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            if self._process and \
                    self._process.poll() is None:
                return False, "WSJT-X already running"

            if not shutil.which('wsjtx'):
                return False, (
                    "WSJT-X binary not found. "
                    "Install wsjtx: "
                    "docker compose build --no-cache"
                )

            try:
                # Get display — must use :99 (Xvfb)
                # NOT :0 which does not exist in Docker
                display = self._get_display()

                if not display:
                    return False, (
                        "No X11 display available. "
                        "Xvfb must be running on :99."
                    )

                self._add_log(
                    f"Using display: {display}"
                )

                # Build environment
                env = os.environ.copy()
                env['DISPLAY'] = display

                # Set Qt platform to xcb explicitly
                # Prevents Qt from trying other platforms
                env['QT_QPA_PLATFORM'] = 'xcb'

                # Disable Qt accessibility warnings
                env['QT_ACCESSIBILITY'] = '0'

                # Point Qt to xcb plugin location
                # (helps when xcb is in non-standard path)
                qt_plugin_path = self._find_qt_plugin_path()
                if qt_plugin_path:
                    env['QT_PLUGIN_PATH'] = qt_plugin_path
                    self._add_log(
                        f"Qt plugin path: {qt_plugin_path}"
                    )

                self._add_log(
                    f"Launching WSJT-X on {display}..."
                )

                self._process = subprocess.Popen(
                    ['wsjtx'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env
                )

                self._status['process_running'] = True
                self._status['pid'] = self._process.pid
                self._add_log(
                    f"✓ WSJT-X started "
                    f"(PID: {self._process.pid})"
                )

                # Start process monitor
                self._start_process_monitor()

                return True, (
                    f"WSJT-X started "
                    f"(PID: {self._process.pid})"
                )

            except Exception as e:
                error = str(e)
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Failed: {error}"

    def _get_display(self):
        """
        Get a valid X11 display for WSJT-X.

        Returns :99 if Xvfb is running there,
        otherwise falls back to DISPLAY env var.

        Returns:
            str: Display string or None if unavailable
        """
        # Prefer :99 (Xvfb set up by entrypoint)
        if self._is_display_available(':99'):
            os.environ['DISPLAY'] = ':99'
            return ':99'

        # Fall back to DISPLAY env var
        env_display = os.environ.get('DISPLAY', '').strip()
        if env_display and \
                self._is_display_available(env_display):
            return env_display

        # Try to start Xvfb as last resort
        if shutil.which('Xvfb'):
            if self._start_xvfb(':99'):
                return ':99'

        return None

    def _is_display_available(self, display):
        """
        Check if an X11 display is actually available.

        Checks both the socket file and verifies a
        connection can be made.

        Args:
            display: Display string e.g. ':99'

        Returns:
            bool: True if display is usable
        """
        num = display.replace(':', '')

        # Check socket file exists
        socket_path = f'/tmp/.X11-unix/X{num}'
        if not os.path.exists(socket_path):
            return False

        # Try connecting with xdpyinfo
        try:
            env = os.environ.copy()
            env['DISPLAY'] = display
            result = subprocess.run(
                ['xdpyinfo'],
                capture_output=True,
                env=env,
                timeout=3
            )
            return result.returncode == 0
        except Exception:
            # xdpyinfo not available — just trust the socket
            return True

    def _start_xvfb(self, display=':99'):
        """
        Start Xvfb virtual framebuffer.

        Args:
            display: Display to use

        Returns:
            bool: True if started
        """
        import time

        if not shutil.which('Xvfb'):
            self._add_log(
                "Xvfb not available", 'warning'
            )
            return False

        num = display.replace(':', '')

        # Clean up stale files
        for path in [
            f'/tmp/.X{num}-lock',
            f'/tmp/.X11-unix/X{num}'
        ]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        try:
            xvfb = subprocess.Popen(
                [
                    'Xvfb', display,
                    '-screen', '0', '1280x1024x24',
                    '-nolisten', 'tcp',
                    '-ac'
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            for _ in range(8):
                time.sleep(0.5)
                if os.path.exists(
                    f'/tmp/.X11-unix/X{num}'
                ):
                    os.environ['DISPLAY'] = display
                    self._add_log(
                        f"✓ Xvfb started on {display}"
                    )
                    return True

            self._add_log(
                "Xvfb did not start", 'warning'
            )
            return False

        except Exception as e:
            self._add_log(
                f"Xvfb error: {e}", 'warning'
            )
            return False

    def _find_qt_plugin_path(self):
        """
        Find the Qt platform plugins directory.

        Searches common locations for Qt xcb plugin
        to help Qt locate it if not in default path.

        Returns:
            str: Path to Qt plugins dir or None
        """
        search_paths = [
            '/usr/lib/qt5/plugins',
            '/usr/lib/aarch64-linux-gnu/qt5/plugins',
            '/usr/lib/x86_64-linux-gnu/qt5/plugins',
            '/usr/lib/arm-linux-gnueabihf/qt5/plugins',
            '/usr/local/lib/qt5/plugins',
        ]

        for path in search_paths:
            xcb = os.path.join(
                path, 'platforms', 'libqxcb.so'
            )
            if os.path.exists(xcb):
                return path

        # Try to find via dpkg
        try:
            result = subprocess.run(
                ['find', '/usr', '-name',
                 'libqxcb.so', '-type', 'f'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                # Return the platforms/ parent's parent
                xcb_path = result.stdout.strip().split(
                    '\n'
                )[0]
                return os.path.dirname(
                    os.path.dirname(xcb_path)
                )
        except Exception:
            pass

        return None

    def _start_process_monitor(self):
        """Monitor WSJT-X process output."""
        def monitor():
            if not self._process or \
                    not self._process.stdout:
                return

            try:
                for line in iter(
                    self._process.stdout.readline, ''
                ):
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        self._add_log(line)
                        # Detect Qt xcb error
                        if 'xcb' in line.lower() and \
                                'could not' in line.lower():
                            self._add_log(
                                "Qt xcb error detected. "
                                "Ensure libxcb packages "
                                "are installed in Docker "
                                "and DISPLAY=:99",
                                'error'
                            )
                        elif 'display' in line.lower() and \
                                'connect' in line.lower():
                            self._add_log(
                                f"Display error: {line}. "
                                f"DISPLAY should be :99 "
                                f"(Xvfb), not :0",
                                'error'
                            )
            except Exception:
                pass
            finally:
                self._status['process_running'] = False
                self._status['pid'] = None
                self._add_log(
                    "WSJT-X process terminated",
                    'warning'
                )

        import threading
        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='wsjtx-monitor'
        )
        thread.start()
    

    def stop_wsjtx(self):
        """
        Stop WSJT-X process gracefully.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if not self._process:
                return False, "WSJT-X not running"

            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait()

                self._process = None
                self._status['process_running'] = False
                self._status['pid'] = None
                self._add_log("✓ WSJT-X stopped")
                return True, "WSJT-X stopped"

            except Exception as e:
                return False, f"[WSJTX] Stop error: {str(e)}"

    def _start_process_monitor(self):
        """
        Start thread to monitor WSJT-X process output.

        Reads stdout from WSJT-X and adds to log buffer.
        Also detects process termination.
        """
        def monitor():
            if not self._process or not self._process.stdout:
                return

            try:
                for line in iter(
                    self._process.stdout.readline, ''
                ):
                    if not line:
                        break
                    self._add_log(line.strip())
            except Exception:
                pass

            # Process ended
            self._status['process_running'] = False
            self._status['pid'] = None
            self._add_log(
                "WSJT-X process ended", 'warning'
            )

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='wsjtx-process-monitor'
        )
        thread.start()

    def get_status(self):
        """
        Get comprehensive WSJT-X status.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check process
        if self._process:
            if self._process.poll() is not None:
                self._status['process_running'] = False
                self._status['pid'] = None

        # Check listener
        if self._listener:
            self._status['udp_listening'] = self._listener._running
            self._status['wsjtx_connected'] = (
                self._listener.is_connected()
            )

            # Get listener stats
            listener_stats = self._listener.get_stats()
            self._status['packets_received'] = (
                listener_stats.get('packets_received', 0)
            )

        return dict(self._status)

    def get_decodes(self, limit=50):
        """
        Get recent decoded messages.

        Args:
            limit: Maximum to return

        Returns:
            list: Recent decodes
        """
        if not self._listener:
            return []
        return self._listener.get_decodes(limit)

    def get_spots(self, limit=100, mode_filter=None):
        """
        Get decoded spots with optional filtering.

        Args:
            limit: Maximum spots to return
            mode_filter: Mode to filter by

        Returns:
            list: Spot data
        """
        if not self._listener:
            return []
        return self._listener.get_spots(limit, mode_filter)

    def get_wspr_decodes(self, limit=50):
        """
        Get WSPR decode data.

        Returns:
            list: WSPR decodes
        """
        if not self._listener:
            return []
        return self._listener.get_wspr_decodes(limit)

    def get_wsjtx_status(self):
        """
        Get status from WSJT-X (from latest status packet).

        Returns:
            dict: WSJT-X status data
        """
        if not self._listener:
            return {}
        return self._listener.get_status()

    def halt_tx(self, client_id='WSJTX', auto_only=False):
        """
        Send halt TX command to WSJT-X.

        Args:
            client_id: WSJT-X client identifier
            auto_only: Only halt auto-TX

        Returns:
            bool: True if sent successfully
        """
        if not self._listener:
            return False

        command = self._listener.decoder.encode_halt_tx(
            client_id, auto_only
        )
        return self._listener.send_command(command)

    def send_free_text(self, text, client_id='WSJTX', send=False):
        """
        Set WSJT-X free text message.

        Args:
            text: Text to set (max 13 chars)
            client_id: WSJT-X client ID
            send: Start transmission

        Returns:
            bool: True if sent
        """
        if not self._listener:
            return False

        command = self._listener.decoder.encode_free_text(
            client_id, text[:13], send
        )
        return self._listener.send_command(command)

    def clear_spots(self):
        """Clear all spot data from listener."""
        if self._listener:
            self._listener.clear_spots()
