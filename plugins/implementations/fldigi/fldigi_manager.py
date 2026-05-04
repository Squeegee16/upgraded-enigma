"""
FLdigi Process Manager
=======================
Manages the FLdigi process lifecycle and XML-RPC communication.

FLdigi is a GUI application requiring an X11 display.
In Docker environments a virtual framebuffer (Xvfb) is used
to provide a display without real graphics hardware.

Display Strategy:
    1. Check for existing DISPLAY environment variable
    2. Check if Xvfb is already running on :99
    3. Start Xvfb if not running and available
    4. Fall back to :0 if all else fails

XML-RPC API:
    FLdigi exposes XML-RPC on port 7362 (default).
    http://www.w1hkj.com/FldigiHelp/xmlrpc-control.html
"""

import os
import shutil
import subprocess
import threading
import time
import json
from datetime import datetime

from plugins.implementations.fldigi.xmlrpc_client import (
    FldigiXMLRPC
)


class FldigiManager:
    """
    Manages FLdigi process and XML-RPC communication.

    Handles display setup (Xvfb), process lifecycle,
    XML-RPC connection, and log monitoring.
    """

    def __init__(self, config_dir,
                 binary_path=None,
                 xmlrpc_host='localhost',
                 xmlrpc_port=7362):
        """
        Initialise FLdigi manager.

        Args:
            config_dir: Plugin configuration directory
            binary_path: Path to fldigi binary
            xmlrpc_host: XML-RPC server host
            xmlrpc_port: XML-RPC server port
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('fldigi') or
            '/usr/bin/fldigi'
        )
        self.xmlrpc_host = xmlrpc_host
        self.xmlrpc_port = xmlrpc_port

        # FLdigi config directory
        self.fldigi_home = os.path.join(
            config_dir, 'fldigi_home'
        )
        os.makedirs(self.fldigi_home, exist_ok=True)

        # Process management
        self._process = None
        self._xvfb_process = None
        self._process_lock = threading.Lock()

        # XML-RPC client
        self.rpc = FldigiXMLRPC(xmlrpc_host, xmlrpc_port)

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Pending contacts (detected from FLdigi log panel)
        self._pending_contacts = []
        self._contacts_lock = threading.Lock()

        # Monitor control
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
            'display': None,
            'last_check': None,
            'error': None,
        }

        # Load configuration
        self.config = self._load_config()

    def _load_config(self):
        """Load FLdigi plugin configuration."""
        config_file = os.path.join(
            self.config_dir, 'fldigi_config.json'
        )
        defaults = {
            'xmlrpc_host': 'localhost',
            'xmlrpc_port': 7362,
            'launch_mode': 'connect',
            'display': '',              # Auto-detect
            'default_mode': 'BPSK31',
            'default_frequency': 14070000,
            'callsign': '',
            'locator': '',
            'auto_start': False,
            'auto_connect': True,
            'log_rx_contacts': True,
            'monitor_interval': 5,
            'xvfb_display': ':99',
            'connect_timeout': 30,
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
        """Save plugin configuration."""
        config_file = os.path.join(
            self.config_dir, 'fldigi_config.json'
        )
        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[FLdigi] Config save error: {e}")
            return False

    def _add_log(self, message, level='info'):
        """Add entry to log buffer."""
        with self._log_lock:
            self._logs.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': str(message)
            })
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """Get recent log entries."""
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def _get_display(self):
        """
        Determine the X11 display to use for FLdigi.

        Priority:
            1. Configured display in plugin settings
            2. DISPLAY environment variable (if set)
            3. Xvfb display :99 (if running)
            4. Start Xvfb on :99 (if available)
            5. Fall back to :0

        Returns:
            str: Display string (e.g., ':99', ':0')
        """
        # 1. Explicit config override
        configured = self.config.get('display', '').strip()
        if configured:
            self._add_log(
                f"Using configured display: {configured}"
            )
            return configured

        # 2. Existing DISPLAY env var
        env_display = os.environ.get('DISPLAY', '').strip()
        if env_display:
            self._add_log(
                f"Using DISPLAY env: {env_display}"
            )
            return env_display

        # 3. Check if Xvfb is already running on :99
        xvfb_display = self.config.get(
            'xvfb_display', ':99'
        )
        if self._is_xvfb_running(xvfb_display):
            self._add_log(
                f"Using existing Xvfb: {xvfb_display}"
            )
            return xvfb_display

        # 4. Try to start Xvfb
        if shutil.which('Xvfb'):
            started = self._start_xvfb(xvfb_display)
            if started:
                return xvfb_display

        # 5. Last resort fallback
        self._add_log(
            "WARNING: No display found, trying :0",
            'warning'
        )
        return ':0'

    def _is_xvfb_running(self, display):
        """
        Check if Xvfb is running on the given display.

        Args:
            display: Display string (e.g., ':99')

        Returns:
            bool: True if Xvfb is running
        """
        # Check for lock file
        display_num = display.replace(':', '')
        lock_file = f'/tmp/.X{display_num}-lock'

        if os.path.exists(lock_file):
            # Verify the process is actually running
            try:
                with open(lock_file, 'r') as f:
                    pid_str = f.read().strip()
                pid = int(pid_str)
                # Check if process exists
                os.kill(pid, 0)
                return True
            except (ValueError, OSError):
                # Process not running, remove stale lock
                try:
                    os.remove(lock_file)
                except Exception:
                    pass

        return False

    def _start_xvfb(self, display=':99'):
        """
        Start a virtual framebuffer display.

        FLdigi requires a real or virtual X11 display.
        Xvfb (X Virtual FrameBuffer) provides a display
        without needing real graphics hardware, making
        it suitable for Docker containers.

        Args:
            display: Display number to use (e.g., ':99')

        Returns:
            bool: True if Xvfb started successfully
        """
        if not shutil.which('Xvfb'):
            self._add_log(
                "Xvfb not available. Install with: "
                "apt-get install xvfb",
                'warning'
            )
            return False

        # Remove stale lock file if present
        display_num = display.replace(':', '')
        lock_file = f'/tmp/.X{display_num}-lock'
        socket_file = f'/tmp/.X11-unix/X{display_num}'

        for stale in [lock_file, socket_file]:
            if os.path.exists(stale):
                try:
                    os.remove(stale)
                    self._add_log(
                        f"Removed stale file: {stale}"
                    )
                except Exception:
                    pass

        self._add_log(
            f"Starting Xvfb on display {display}..."
        )

        try:
            self._xvfb_process = subprocess.Popen(
                [
                    'Xvfb', display,
                    '-screen', '0', '1024x768x24',
                    '-nolisten', 'tcp',
                    '-ac'   # Disable access control
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for Xvfb to initialise
            for i in range(10):
                time.sleep(0.5)
                if self._xvfb_process.poll() is not None:
                    # Xvfb exited already
                    stderr = ''
                    try:
                        stderr = (
                            self._xvfb_process.stderr.read()
                        )
                    except Exception:
                        pass
                    self._add_log(
                        f"Xvfb exited: {stderr[:200]}",
                        'error'
                    )
                    return False

                if self._is_xvfb_running(display):
                    self._add_log(
                        f"✓ Xvfb running on {display} "
                        f"(PID: {self._xvfb_process.pid})"
                    )
                    # Set environment variable
                    os.environ['DISPLAY'] = display
                    return True

            self._add_log(
                "Xvfb did not start in time", 'warning'
            )
            return False

        except Exception as e:
            self._add_log(
                f"Xvfb start error: {e}", 'error'
            )
            return False

    def _stop_xvfb(self):
        """Stop the Xvfb process if we started it."""
        if self._xvfb_process:
            try:
                if self._xvfb_process.poll() is None:
                    self._xvfb_process.terminate()
                    self._xvfb_process.wait(timeout=5)
                self._add_log("Xvfb stopped")
            except Exception as e:
                self._add_log(
                    f"Xvfb stop error: {e}", 'warning'
                )
            finally:
                self._xvfb_process = None

    def start_fldigi(self):
        """
        Launch FLdigi with Xvfb display support.

        Steps:
            1. Determine display (or start Xvfb)
            2. Build FLdigi command with XML-RPC flags
            3. Launch FLdigi process
            4. Wait for XML-RPC to become available
            5. Start log monitoring

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            # Already running
            if self._process and \
                    self._process.poll() is None:
                return False, "FLdigi already running"

            # Check binary
            binary = shutil.which('fldigi')
            if not binary:
                return False, (
                    "FLdigi binary not found. "
                    "Add 'fldigi' to Dockerfile and rebuild: "
                    "docker compose build --no-cache"
                )

            try:
                # Get or create display
                display = self._get_display()
                self._status['display'] = display
                self._add_log(
                    f"Using display: {display}"
                )

                # Build FLdigi command
                cmd = self._build_fldigi_command(
                    binary, display
                )

                self._add_log(
                    f"Launching FLdigi: {' '.join(cmd)}"
                )

                # Build environment
                env = os.environ.copy()
                env['DISPLAY'] = display

                # Launch FLdigi
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    bufsize=1
                )

                self._status['process_running'] = True
                self._status['pid'] = self._process.pid
                self._add_log(
                    f"✓ FLdigi started "
                    f"(PID: {self._process.pid})"
                )

                # Start output monitor (detects early exit)
                self._start_output_monitor()

                # Wait for XML-RPC to become available
                connect_timeout = self.config.get(
                    'connect_timeout', 30
                )
                self._add_log(
                    f"Waiting for XML-RPC "
                    f"(timeout: {connect_timeout}s)..."
                )

                connected = False
                for attempt in range(connect_timeout // 2):
                    time.sleep(2)

                    # Check if process already died
                    if self._process.poll() is not None:
                        return False, (
                            "FLdigi exited immediately. "
                            "Check logs for details. "
                            "Ensure a display is available "
                            "(Xvfb is required in Docker)."
                        )

                    if self.rpc.connect():
                        connected = True
                        version = self.rpc.get_version()
                        self._status['version'] = version
                        self._status['xmlrpc_connected'] = (
                            True
                        )
                        self._add_log(
                            f"✓ XML-RPC connected: "
                            f"FLdigi {version}"
                        )
                        self._start_monitor()
                        break

                    self._add_log(
                        f"  Attempt {attempt + 1}: "
                        f"waiting for XML-RPC..."
                    )

                if not connected:
                    return (
                        True,
                        "FLdigi started but XML-RPC not "
                        "responding. Check FLdigi XML-RPC "
                        "settings (Configure → XML-RPC, "
                        "port 7362)."
                    )

                return (
                    True,
                    f"FLdigi started and connected "
                    f"(PID: {self._process.pid})"
                )

            except FileNotFoundError:
                msg = (
                    f"FLdigi binary not found at {binary}. "
                    "Rebuild Docker image."
                )
                self._add_log(msg, 'error')
                return False, msg

            except Exception as e:
                msg = f"Failed to start FLdigi: {str(e)}"
                self._add_log(msg, 'error')
                return False, msg

    def _build_fldigi_command(self, binary, display):
        """
        Build the FLdigi launch command.

        Args:
            binary: Path to fldigi executable
            display: X11 display string

        Returns:
            list: Command and arguments
        """
        cmd = [binary]

        # XML-RPC server configuration
        cmd.extend([
            '--xmlrpc-server-address',
            self.config.get('xmlrpc_host', 'localhost'),
            '--xmlrpc-server-port',
            str(self.config.get('xmlrpc_port', 7362)),
        ])

        # Dedicated config directory to avoid conflicts
        # with any system-level FLdigi installation
        cmd.extend(['--config-dir', self.fldigi_home])

        return cmd

    def _start_output_monitor(self):
        """
        Monitor FLdigi stdout in background thread.

        Reads FLdigi output and stores in log buffer.
        Detects early process termination and logs
        the reason for easier diagnosis.
        """
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
            except Exception as e:
                self._add_log(
                    f"Output monitor error: {e}", 'warning'
                )
            finally:
                # Process ended
                exit_code = self._process.poll()
                self._status['process_running'] = False
                self._status['pid'] = None

                if exit_code is not None and exit_code != 0:
                    self._add_log(
                        f"FLdigi process terminated "
                        f"(exit code: {exit_code}). "
                        f"Display was: "
                        f"{self._status.get('display', '?')}",
                        'warning'
                    )

                    # Provide diagnosis hints
                    if exit_code in (1, 127):
                        self._add_log(
                            "HINT: FLdigi may have failed "
                            "to open a display. "
                            "Ensure Xvfb is running: "
                            "apt-get install xvfb",
                            'warning'
                        )
                else:
                    self._add_log("FLdigi process terminated")

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='fldigi-output-monitor'
        )
        thread.start()

    def connect_to_existing(self):
        """
        Connect to an already-running FLdigi instance.

        Used when FLdigi is started separately, either:
        - Running on the host and accessible via network
        - Started manually inside the container
        - Running inside a container with DISPLAY forwarded

        Returns:
            tuple: (success: bool, message: str)
        """
        self._add_log(
            f"Attempting to connect to FLdigi XML-RPC at "
            f"{self.xmlrpc_host}:{self.xmlrpc_port}..."
        )

        if self.rpc.connect():
            version = self.rpc.get_version()
            self._status['xmlrpc_connected'] = True
            self._status['version'] = version
            self._update_status_from_rpc()
            self._start_monitor()

            self._add_log(
                f"✓ Connected to FLdigi {version}"
            )
            return (
                True,
                f"Connected to FLdigi {version}"
            )

        msg = (
            f"Cannot connect to FLdigi XML-RPC on "
            f"{self.xmlrpc_host}:{self.xmlrpc_port}. "
            "Start FLdigi with XML-RPC enabled "
            "(Configure → XML-RPC → port 7362)."
        )
        self._add_log(msg, 'warning')
        return False, msg

    def stop_fldigi(self, save_options=True):
        """
        Stop FLdigi gracefully.

        Args:
            save_options: Request FLdigi saves config

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            # Request graceful shutdown via XML-RPC
            if self.rpc.is_connected():
                try:
                    self.rpc.terminate(save_options)
                    time.sleep(1)
                except Exception:
                    pass
                self.rpc.disconnect()

            self._status['xmlrpc_connected'] = False
            self._rx_monitor_active = False

            # Kill our process if we started it
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
                        f"Stop error: {e}", 'warning'
                    )
                finally:
                    self._process = None

            self._status['process_running'] = False
            self._status['pid'] = None

            # Stop Xvfb if we started it
            self._stop_xvfb()

            self._add_log("✓ FLdigi stopped")
            return True, "FLdigi stopped"

    def _update_status_from_rpc(self):
        """Update status from live XML-RPC queries."""
        if not self.rpc.is_connected():
            return
        try:
            self._status['mode'] = (
                self.rpc.get_modem_name()
            )
            self._status['frequency'] = (
                self.rpc.get_frequency()
            )
            self._status['trx_status'] = (
                self.rpc.get_trx_status()
            )
            self._status['carrier'] = (
                self.rpc.get_modem_carrier()
            )
        except Exception:
            pass

    def get_status(self):
        """Get comprehensive FLdigi status."""
        self._status['last_check'] = (
            datetime.utcnow().isoformat()
        )

        if self._process:
            if self._process.poll() is not None:
                self._status['process_running'] = False
                self._status['pid'] = None

        if self._status.get('xmlrpc_connected'):
            if not self.rpc.is_connected():
                self._status['xmlrpc_connected'] = False
                self._add_log(
                    "XML-RPC connection lost", 'warning'
                )
            else:
                self._update_status_from_rpc()

        return dict(self._status)

    def _start_monitor(self):
        """Start background status monitor."""
        self._rx_monitor_active = True

        def monitor():
            interval = self.config.get(
                'monitor_interval', 5
            )
            while self._rx_monitor_active:
                try:
                    if self.rpc.is_connected():
                        self._check_log_entry()
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
        """Check for new contacts in FLdigi log panel."""
        try:
            callsign = self.rpc.get_log_callsign()
            if callsign and callsign.strip():
                log_entry = self.rpc.get_full_log_entry()
                if log_entry and log_entry.get('callsign'):
                    with self._contacts_lock:
                        existing = [
                            c for c in self._pending_contacts
                            if c.get('callsign') ==
                            log_entry['callsign']
                        ]
                        if not existing:
                            self._pending_contacts.append(
                                log_entry
                            )
                            self._add_log(
                                f"Contact: "
                                f"{log_entry['callsign']}"
                            )
        except Exception:
            pass

    def get_pending_contacts(self):
        """Get and clear pending contacts."""
        with self._contacts_lock:
            contacts = list(self._pending_contacts)
            self._pending_contacts.clear()
            return contacts

    def send_text(self, text, transmit=True):
        """Send text via FLdigi."""
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"
        try:
            self.rpc.add_tx_text(text + '\n')
            if transmit:
                self.rpc.set_tx()
                self._add_log(f"TX: {text[:50]}")
            return True, "Text queued"
        except Exception as e:
            return False, f"TX error: {str(e)}"

    def set_mode(self, mode_name):
        """Set FLdigi operating mode."""
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"
        try:
            self.rpc.set_modem_by_name(mode_name)
            self._status['mode'] = mode_name
            return True, f"Mode: {mode_name}"
        except Exception as e:
            return False, f"Mode error: {str(e)}"

    def set_frequency(self, freq_hz):
        """Set radio frequency."""
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"
        try:
            self.rpc.set_frequency(freq_hz)
            self._status['frequency'] = freq_hz
            return True, f"{freq_hz/1e6:.3f} MHz"
        except Exception as e:
            return False, f"Frequency error: {str(e)}"

    def get_available_modes(self):
        """Get available FLdigi modes."""
        if self.rpc.is_connected():
            modes = self.rpc.get_modem_names()
            if modes:
                return sorted(modes)

        # Fallback hardcoded list
        return sorted([
            'BPSK31', 'BPSK63', 'BPSK125', 'BPSK250',
            'QPSK31', 'QPSK63', 'QPSK125',
            'RTTY', 'RTTY-45', 'RTTY-75',
            'MFSK-8', 'MFSK-16', 'MFSK-22', 'MFSK-32',
            'OLIVIA-4/250', 'OLIVIA-8/500',
            'OLIVIA-16/500', 'OLIVIA-32/1000',
            'CW', 'WSPR', 'MT63-500', 'MT63-1000',
            'THOR-8', 'THOR-16', 'THOR-22',
            'DOMINO-11', 'DOMINO-22',
        ])

    def get_rx_text(self):
        """Get received text from FLdigi."""
        if not self.rpc.is_connected():
            return ''
        return self.rpc.get_rx_text_full() or ''

    def abort_tx(self):
        """Abort current transmission."""
        if not self.rpc.is_connected():
            return False, "Not connected"
        try:
            self.rpc.abort()
            self.rpc.set_rx()
            self._status['trx_status'] = 'rx'
            return True, "TX aborted"
        except Exception as e:
            return False, f"Abort error: {str(e)}"
