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
                print(f"[WSJTX] Config load error: {e}")

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
            print("[WSJTX] ✓ Config saved")
            return True
        except Exception as e:
            print(f"[WSJTX] Config save error: {e}")
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
                    f"UDP listener started on port "
                    f"{self.config.get('udp_port', 2237)}"
                )
                return True, "UDP listener started"
            else:
                return False, "Failed to start UDP listener"

        except Exception as e:
            error = str(e)
            self._add_log(f"Listener error: {error}", 'error')
            return False, error

    def stop_listener(self):
        """
        Stop the UDP listener.

        Returns:
            tuple: (success, message)
        """
        if not self._listener:
            return False, "Listener not running"

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
        Launch WSJT-X process.

        Starts WSJT-X with UDP multicast enabled so
        this plugin can receive decoded data.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if self._process and self._process.poll() is None:
                return False, "WSJT-X already running"

            if not shutil.which('wsjtx'):
                return False, (
                    "WSJT-X binary not found. "
                    "Please install WSJT-X."
                )

            try:
                # Build WSJT-X command
                cmd = ['wsjtx']

                # Set UDP server address for multicast
                # WSJT-X reads these from its config file
                # We launch it normally - UDP is configured in WSJT-X

                env = os.environ.copy()
                env['DISPLAY'] = self.config.get('display', ':0')

                self._add_log("Launching WSJT-X...")

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env
                )

                self._status['process_running'] = True
                self._status['pid'] = self._process.pid

                self._add_log(
                    f"✓ WSJT-X started (PID: {self._process.pid})"
                )

                # Start process monitor
                self._start_process_monitor()

                return True, (
                    f"WSJT-X started (PID: {self._process.pid})"
                )

            except Exception as e:
                error = str(e)
                self._status['error'] = error
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Failed to start: {error}"

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
                return False, f"Stop error: {str(e)}"

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