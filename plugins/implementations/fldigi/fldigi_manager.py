"""
FLdigi Process Manager
=======================
Manages the FLdigi process lifecycle and communication.

FLdigi can be:
    - Started as a new process by this plugin
    - Connected to an existing running instance
    - Controlled via XML-RPC API

When started by this plugin, FLdigi is launched in
headless mode with XML-RPC enabled. For full GUI
access, FLdigi can also be launched with display.

Key operations:
    - Process start/stop with XML-RPC
    - Mode/modem management
    - TX/RX control
    - Log entry monitoring
    - Signal/spot monitoring

Reference:
    http://www.w1hkj.com/FldigiHelp/xmlrpc-control.html
    https://github.com/w1hkj/fldigi/
"""

import os
import json
import shutil
import threading
import subprocess
import time
from datetime import datetime

from plugins.implementations.fldigi.xmlrpc_client import FldigiXMLRPC


class FldigiManager:
    """
    Manages FLdigi instance and provides unified API.

    Handles process lifecycle, XML-RPC communication,
    log monitoring, and contact detection for logbook
    integration.
    """

    # Common digital modes organized by category
    MODES_PSK = [
        'BPSK31', 'BPSK63', 'BPSK125', 'BPSK250',
        'BPSK500', 'BPSK1000',
        'QPSK31', 'QPSK63', 'QPSK125', 'QPSK250',
        'QPSK500',
    ]

    MODES_RTTY = [
        'RTTY', 'RTTY-45', 'RTTY-50', 'RTTY-75',
        'RTTY-100',
    ]

    MODES_MFSK = [
        'MFSK-8', 'MFSK-16', 'MFSK-22', 'MFSK-31',
        'MFSK-32', 'MFSK-64', 'MFSK-128',
    ]

    MODES_OLIVIA = [
        'OLIVIA-4/250', 'OLIVIA-8/250', 'OLIVIA-8/500',
        'OLIVIA-16/500', 'OLIVIA-32/1000',
        'OLIVIA-64/2000',
    ]

    MODES_OTHER = [
        'CW', 'WSPR', 'JS8', 'THOR-8', 'THOR-16',
        'THOR-22', 'MT63-500', 'MT63-1000', 'MT63-2000',
        'DOMINO-11', 'DOMINO-22', 'CONTESTIA-4/250',
        'CONTESTIA-8/500', 'CONTESTIA-16/1000',
    ]

    def __init__(self, config_dir, binary_path=None,
                 xmlrpc_host='localhost', xmlrpc_port=7362):
        """
        Initialize FLdigi manager.

        Args:
            config_dir: Plugin configuration directory
            binary_path: Path to FLdigi binary (auto-detect if None)
            xmlrpc_host: FLdigi XML-RPC host
            xmlrpc_port: FLdigi XML-RPC port
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('fldigi') or
            '/usr/bin/fldigi'
        )
        self.xmlrpc_host = xmlrpc_host
        self.xmlrpc_port = xmlrpc_port

        # Process management
        self._process = None
        self._process_lock = threading.Lock()

        # XML-RPC client
        self.rpc = FldigiXMLRPC(xmlrpc_host, xmlrpc_port)

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Detected contacts (pending logbook entries)
        self._pending_contacts = []
        self._contacts_lock = threading.Lock()

        # RX text monitoring
        self._last_rx_text = ''
        self._rx_monitor_active = False

        # Status
        self._status = {
            'process_running': False,
            'xmlrpc_connected': False,
            'mode': None,
            'frequency': None,
            'trx_status': 'rx',
            'carrier': 1500,
            'version': None,
            'pid': None,
            'last_check': None,
            'error': None,
        }

        # Load configuration
        self.config = self._load_config()

        # Create config directory
        os.makedirs(config_dir, exist_ok=True)

    def _load_config(self):
        """
        Load FLdigi plugin configuration.

        Returns:
            dict: Configuration with defaults
        """
        config_file = os.path.join(
            self.config_dir, 'fldigi_config.json'
        )

        defaults = {
            # FLdigi connection settings
            'xmlrpc_host': 'localhost',
            'xmlrpc_port': 7362,

            # FLdigi launch settings
            'launch_mode': 'gui',    # 'gui' or 'headless'
            'display': ':0',          # X display for GUI mode
            'audio_device': 'pulse',  # Audio device

            # Default mode
            'default_mode': 'BPSK31',
            'default_frequency': 14070000,  # 14.070 MHz

            # Waterfall settings
            'wf_low': 50,
            'wf_high': 3000,

            # Callsign/station info
            'callsign': '',
            'locator': '',
            'asl': 0,

            # Plugin settings
            'auto_start': False,
            'auto_connect': True,     # Connect to existing instance
            'log_rx_contacts': True,  # Auto-log detected contacts
            'monitor_interval': 5,   # Seconds between status checks
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[FLdigi] Config load error: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration.

        Args:
            config_data: Configuration dictionary

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(
            self.config_dir, 'fldigi_config.json'
        )

        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print("[FLdigi] ✓ Config saved")
            return True
        except Exception as e:
            print(f"[FLdigi] Config save error: {e}")
            return False

    def _add_log(self, message, level='info'):
        """
        Add entry to in-memory log buffer.

        Args:
            message: Log message text
            level: Severity level (info, warning, error)
        """
        with self._log_lock:
            self._logs.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': str(message)
            })

            # Maintain ring buffer
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """
        Get recent log entries.

        Args:
            limit: Maximum entries to return

        Returns:
            list: Log entries newest first
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def start_fldigi(self):
        """
        Launch FLdigi process with XML-RPC enabled.

        Starts FLdigi with the XML-RPC server enabled
        so this plugin can communicate with it.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            # Check if already running as a process we started
            if self._process and self._process.poll() is None:
                return False, "FLdigi process already running"

            # Check if binary is available
            if not self.binary_path or \
                    not shutil.which('fldigi'):
                return False, (
                    "FLdigi binary not found. "
                    "Please install FLdigi."
                )

            try:
                # Build FLdigi command
                cmd = self._build_fldigi_command()

                self._add_log(
                    f"Launching FLdigi: {' '.join(cmd)}"
                )

                # Launch FLdigi
                env = os.environ.copy()

                # Set display for GUI mode
                if self.config.get('launch_mode') == 'gui':
                    display = self.config.get('display', ':0')
                    env['DISPLAY'] = display

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
                    f"✓ FLdigi started (PID: {self._process.pid})"
                )

                # Wait for FLdigi to initialize and start XML-RPC
                self._add_log("Waiting for FLdigi to initialize...")
                connected = False

                for attempt in range(15):
                    time.sleep(2)
                    if self.rpc.connect():
                        connected = True
                        break
                    self._add_log(
                        f"Connection attempt {attempt + 1}/15..."
                    )

                if connected:
                    self._status['xmlrpc_connected'] = True
                    version = self.rpc.get_version()
                    self._status['version'] = version
                    self._add_log(
                        f"✓ XML-RPC connected: FLdigi {version}"
                    )

                    # Start monitoring
                    self._start_monitor()

                    return True, (
                        f"FLdigi started and connected "
                        f"(PID: {self._process.pid})"
                    )
                else:
                    self._add_log(
                        "WARNING: FLdigi started but XML-RPC "
                        "not responding", 'warning'
                    )
                    return True, (
                        "FLdigi started but XML-RPC not connected. "
                        "Check FLdigi XML-RPC settings."
                    )

            except Exception as e:
                error = str(e)
                self._status['error'] = error
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Failed to start FLdigi: {error}"

    def _build_fldigi_command(self):
        """
        Build FLdigi command line arguments.

        Configures XML-RPC server address and port,
        audio device, and other startup options.

        Returns:
            list: Command and arguments
        """
        cmd = ['fldigi']

        # XML-RPC server configuration
        # FLdigi must have XML-RPC enabled and listening
        cmd.extend([
            '--xmlrpc-server-address',
            self.config.get('xmlrpc_host', 'localhost'),
            '--xmlrpc-server-port',
            str(self.config.get('xmlrpc_port', 7362)),
        ])

        # Set config directory to avoid conflicts
        fldigi_config_dir = os.path.join(
            self.config_dir, 'fldigi_home'
        )
        os.makedirs(fldigi_config_dir, exist_ok=True)
        cmd.extend(['--config-dir', fldigi_config_dir])

        return cmd

    def connect_to_existing(self):
        """
        Connect to an already-running FLdigi instance.

        Useful when FLdigi is started separately by the user.

        Returns:
            tuple: (success, message)
        """
        self._add_log("Connecting to existing FLdigi instance...")

        if self.rpc.connect():
            self._status['xmlrpc_connected'] = True
            version = self.rpc.get_version()
            self._status['version'] = version

            # Update mode and frequency
            self._update_status_from_rpc()

            # Start monitoring
            self._start_monitor()

            self._add_log(
                f"✓ Connected to FLdigi {version}"
            )
            return True, f"Connected to FLdigi {version}"
        else:
            msg = (
                "Cannot connect to FLdigi. "
                "Ensure FLdigi is running with XML-RPC enabled "
                f"on port {self.xmlrpc_port}."
            )
            self._add_log(msg, 'warning')
            return False, msg

    def stop_fldigi(self, save_options=True):
        """
        Stop FLdigi gracefully.

        If we started the process, terminate it.
        If connecting to existing instance, just disconnect.

        Args:
            save_options: Request FLdigi saves its config

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            # Disconnect XML-RPC
            if self.rpc.is_connected():
                try:
                    self.rpc.terminate(save_options)
                    time.sleep(1)
                except Exception:
                    pass
                self.rpc.disconnect()

            self._status['xmlrpc_connected'] = False
            self._rx_monitor_active = False

            # Kill process if we started it
            if self._process:
                try:
                    if self._process.poll() is None:
                        self._process.terminate()
                        try:
                            self._process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self._process.kill()
                            self._process.wait()
                except Exception as e:
                    self._add_log(
                        f"Error stopping process: {e}", 'warning'
                    )
                finally:
                    self._process = None

            self._status['process_running'] = False
            self._status['pid'] = None
            self._add_log("✓ FLdigi stopped")

            return True, "FLdigi stopped"

    def _update_status_from_rpc(self):
        """
        Update status dictionary from XML-RPC queries.

        Reads current mode, frequency, and other status
        from the running FLdigi instance.
        """
        if not self.rpc.is_connected():
            return

        try:
            self._status['mode'] = self.rpc.get_modem_name()
            self._status['frequency'] = self.rpc.get_frequency()
            self._status['trx_status'] = self.rpc.get_trx_status()
            self._status['carrier'] = self.rpc.get_modem_carrier()
        except Exception as e:
            self._add_log(
                f"Status update error: {e}", 'warning'
            )

    def get_status(self):
        """
        Get comprehensive FLdigi status.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check if our process is still running
        if self._process:
            if self._process.poll() is not None:
                self._status['process_running'] = False
                self._status['pid'] = None
                self._add_log(
                    "FLdigi process terminated", 'warning'
                )

        # Check XML-RPC connection
        if self._status.get('xmlrpc_connected'):
            if not self.rpc.is_connected():
                self._status['xmlrpc_connected'] = False
                self._add_log(
                    "XML-RPC connection lost", 'warning'
                )
            else:
                # Update live data
                self._update_status_from_rpc()

        return dict(self._status)

    def _start_monitor(self):
        """
        Start background monitoring thread.

        Monitors FLdigi status, RX text, and log entries
        at the configured interval.
        """
        self._rx_monitor_active = True

        def monitor():
            """Background monitoring loop."""
            interval = self.config.get('monitor_interval', 5)

            while self._rx_monitor_active:
                try:
                    if self.rpc.is_connected():
                        # Check for new log entries
                        self._check_log_entry()

                        # Update status
                        self._update_status_from_rpc()

                except Exception as e:
                    self._add_log(
                        f"Monitor error: {e}", 'error'
                    )

                time.sleep(interval)

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='fldigi-monitor'
        )
        thread.start()

    def _check_log_entry(self):
        """
        Check if FLdigi has a complete log entry ready.

        Reads the log panel fields and adds to pending
        contacts list if a callsign is present.
        """
        try:
            callsign = self.rpc.get_log_callsign()

            if callsign and callsign.strip():
                log_entry = self.rpc.get_full_log_entry()

                if log_entry and log_entry.get('callsign'):
                    with self._contacts_lock:
                        # Check for duplicates
                        existing = [
                            c for c in self._pending_contacts
                            if c.get('callsign') ==
                            log_entry['callsign']
                        ]

                        if not existing:
                            self._pending_contacts.append(log_entry)
                            self._add_log(
                                f"Contact detected: "
                                f"{log_entry['callsign']} "
                                f"{log_entry.get('mode', '')}"
                            )

        except Exception as e:
            pass  # Silent - log panel may be empty

    def get_pending_contacts(self):
        """
        Get and clear pending contact entries.

        Returns:
            list: Pending contact dictionaries
        """
        with self._contacts_lock:
            contacts = list(self._pending_contacts)
            self._pending_contacts.clear()
            return contacts

    def send_text(self, text, transmit=True):
        """
        Send text via FLdigi.

        Adds text to TX buffer and optionally switches
        to transmit mode.

        Args:
            text: Text to transmit
            transmit: If True, switch to TX after adding text

        Returns:
            tuple: (success, message)
        """
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"

        try:
            # Add text to TX buffer
            self.rpc.add_tx_text(text + '\n')

            # Switch to transmit if requested
            if transmit:
                self.rpc.set_tx()
                self._add_log(f"TX: {text[:50]}...")

            return True, "Text queued for transmission"
        except Exception as e:
            return False, f"TX error: {str(e)}"

    def set_mode(self, mode_name):
        """
        Set FLdigi operating mode.

        Args:
            mode_name: Mode name string (e.g., 'BPSK31')

        Returns:
            tuple: (success, message)
        """
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"

        try:
            self.rpc.set_modem_by_name(mode_name)
            self._status['mode'] = mode_name
            self._add_log(f"Mode set: {mode_name}")
            return True, f"Mode set to {mode_name}"
        except Exception as e:
            return False, f"Mode error: {str(e)}"

    def set_frequency(self, freq_hz):
        """
        Set radio frequency.

        Args:
            freq_hz: Frequency in Hz

        Returns:
            tuple: (success, message)
        """
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"

        try:
            self.rpc.set_frequency(freq_hz)
            self._status['frequency'] = freq_hz
            freq_mhz = freq_hz / 1_000_000
            self._add_log(f"Frequency: {freq_mhz:.3f} MHz")
            return True, f"Frequency set to {freq_mhz:.3f} MHz"
        except Exception as e:
            return False, f"Frequency error: {str(e)}"

    def get_available_modes(self):
        """
        Get all available FLdigi modes.

        Returns both from XML-RPC (if connected) and
        the hardcoded list as fallback.

        Returns:
            list: Available mode name strings
        """
        if self.rpc.is_connected():
            rpc_modes = self.rpc.get_modem_names()
            if rpc_modes:
                return sorted(rpc_modes)

        # Return hardcoded list as fallback
        return sorted(
            self.MODES_PSK +
            self.MODES_RTTY +
            self.MODES_MFSK +
            self.MODES_OLIVIA +
            self.MODES_OTHER
        )

    def get_rx_text(self):
        """
        Get received text from FLdigi.

        Returns:
            str: Current RX buffer content
        """
        if not self.rpc.is_connected():
            return ''
        return self.rpc.get_rx_text_full()

    def abort_tx(self):
        """
        Abort current transmission.

        Returns:
            tuple: (success, message)
        """
        if not self.rpc.is_connected():
            return False, "Not connected"

        try:
            self.rpc.abort()
            self.rpc.set_rx()
            self._status['trx_status'] = 'rx'
            self._add_log("TX aborted")
            return True, "Transmission aborted"
        except Exception as e:
            return False, f"Abort error: {str(e)}"