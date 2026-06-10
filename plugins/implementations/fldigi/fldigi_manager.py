"""
FLdigi Process Manager
=======================
Manages the FLdigi process lifecycle and XML-RPC
communication.

FLdigi is a GUI application requiring:
    - X11 display (provided by Xvfb in Docker)
    - Audio device (provided by PulseAudio null sink)
    - XML-RPC enabled in FLdigi settings

XML-RPC API reference:
    http://www.w1hkj.com/FldigiHelp/xmlrpc-control.html
"""

import os
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime

from plugins.implementations.fldigi.xmlrpc_client import (
    FldigiXMLRPC
)


class FldigiManager:
    """
    Manages FLdigi process and XML-RPC communication.

    Handles:
        - Virtual display (Xvfb) setup
        - Virtual audio (PulseAudio) setup
        - Process lifecycle (start / stop)
        - XML-RPC connection and queries
        - Contact detection from FLdigi log panel
        - Status monitoring
    """

    def __init__(self, config_dir,
                 binary_path=None,
                 xmlrpc_host='localhost',
                 xmlrpc_port=7362):
        """
        Initialise FLdigi manager.

        Args:
            config_dir: Plugin configuration directory
            binary_path: Path to fldigi binary (auto-detect)
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

        # Dedicated FLdigi config directory
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

        # Log buffer (ring buffer)
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Pending contacts detected from FLdigi log panel
        self._pending_contacts = []
        self._contacts_lock = threading.Lock()

        # Monitor thread control
        self._rx_monitor_active = False

        # Status dictionary
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

        # Load plugin configuration
        self.config = self._load_config()

    # ----------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------

    def _load_config(self):
        """
        Load FLdigi plugin configuration from JSON file.

        Returns:
            dict: Configuration with defaults applied
        """
        config_file = os.path.join(
            self.config_dir, 'fldigi_config.json'
        )
        defaults = {
            'xmlrpc_host': 'localhost',
            'xmlrpc_port': 7362,
            'launch_mode': 'connect',
            'display': '',
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
                print(f"[FLdigi] [init] Config load error: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration.

        Args:
            config_data: Dictionary of config values

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
            return True
        except Exception as e:
            print(f"[FLdigi] [init]  Config save error: {e}")
            return False

    # ----------------------------------------------------------
    # Logging
    # ----------------------------------------------------------

    def _add_log(self, message, level='info'):
        """
        Add an entry to the in-memory log buffer.

        Args:
            message: Log message text
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
        Get recent log entries, newest first.

        Args:
            limit: Maximum entries to return

        Returns:
            list: Log entry dicts
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    # ----------------------------------------------------------
    # Display (Xvfb) management
    # ----------------------------------------------------------
    def _get_display(self):
        """
        Determine X11 display for FLdigi.

        Priority:
            1. Configured display value
            2. DISPLAY environment variable
            3. Xvfb on :99 if already running
            4. Start Xvfb on :99
            5. Fall back to :0

        Returns:
            str: Display string (e.g. ':99')
        """
        import os

        # 1. Explicit config
        configured = self.config.get('display', '').strip()
        if configured:
            return configured

        # 2. Environment variable
        env_display = os.environ.get('DISPLAY', '').strip()
        if env_display:
            self._add_log(
                f"Using DISPLAY={env_display}"
            )
            return env_display

        # 3. Check if Xvfb already running on :99
        xvfb_display = ':99'
        if self._is_xvfb_running(xvfb_display):
            os.environ['DISPLAY'] = xvfb_display
            self._add_log(
                f"Using existing Xvfb: {xvfb_display}"
            )
            return xvfb_display

        # 4. Start Xvfb
        if shutil.which('Xvfb'):
            if self._start_xvfb(xvfb_display):
                return xvfb_display

        # 5. Fall back
        self._add_log(
            "No display found, trying :0", 'warning'
        )
        return ':0'

    def _is_xvfb_running(self, display):
        """
        Check if Xvfb is running on the given display.

        Args:
            display: Display string e.g. ':99'

        Returns:
            bool: True if Xvfb is active
        """
        import os
        num = display.replace(':', '')

        # Check socket file
        socket_path = f'/tmp/.X11-unix/X{num}'
        if os.path.exists(socket_path):
            return True

        # Check lock file
        lock_path = f'/tmp/.X{num}-lock'
        if os.path.exists(lock_path):
            try:
                with open(lock_path, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return True
            except (ValueError, OSError):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
        return False

    def _start_xvfb(self, display=':99'):
        """
        Start a virtual framebuffer for FLdigi GUI.

        Args:
            display: Display number to use

        Returns:
            bool: True if Xvfb started
        """
        import os
        import time

        if not shutil.which('Xvfb'):
            self._add_log(
                "Xvfb not installed. "
                "Add xvfb to Dockerfile.",
                'warning'
            )
            return False

        # Clean up stale files
        num = display.replace(':', '')
        for path in [
            f'/tmp/.X{num}-lock',
            f'/tmp/.X11-unix/X{num}'
        ]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        self._add_log(f"Starting Xvfb on {display}...")

        try:
            self._xvfb_process = subprocess.Popen(
                [
                    'Xvfb', display,
                    '-screen', '0', '1024x768x24',
                    '-nolisten', 'tcp',
                    '-ac'
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )

            for _ in range(10):
                time.sleep(0.5)
                if self._xvfb_process.poll() is not None:
                    stderr = ''
                    try:
                        stderr = (
                            self._xvfb_process
                            .stderr.read(300)
                        )
                    except Exception:
                        pass
                    self._add_log(
                        f"Xvfb exited: {stderr}",
                        'error'
                    )
                    return False

                if self._is_xvfb_running(display):
                    os.environ['DISPLAY'] = display
                    self._add_log(
                        f"✓ Xvfb started on {display}"
                    )
                    return True

            self._add_log(
                "Xvfb did not start in time",
                'warning'
            )
            return False

        except Exception as e:
            self._add_log(
                f"Xvfb start error: {e}", 'error'
            )
            return False

    def _is_xvfb_running(self, display):
        """
        Check if Xvfb is running on the given display.

        Args:
            display: Display string (e.g. ':99')

        Returns:
            bool: True if Xvfb process is active
        """
        display_num = display.replace(':', '')

        # Check socket file
        socket = f'/tmp/.X11-unix/X{display_num}'
        if os.path.exists(socket):
            return True

        # Check lock file
        lock = f'/tmp/.X{display_num}-lock'
        if os.path.exists(lock):
            try:
                with open(lock, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # Check if alive
                return True
            except (ValueError, OSError):
                try:
                    os.remove(lock)
                except Exception:
                    pass

        return False

    def _start_xvfb(self, display=':99'):
        """
        Start a virtual framebuffer for FLdigi GUI.

        Args:
            display: Display number to use

        Returns:
            bool: True if Xvfb started
        """
        import os
        import time

        if not shutil.which('Xvfb'):
            self._add_log(
                "Xvfb not installed. "
                "Add xvfb to Dockerfile.",
                'warning'
            )
            return False

        # Clean up stale files
        num = display.replace(':', '')
        for path in [
            f'/tmp/.X{num}-lock',
            f'/tmp/.X11-unix/X{num}'
        ]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        self._add_log(f"Starting Xvfb on {display}...")

        try:
            self._xvfb_process = subprocess.Popen(
                [
                    'Xvfb', display,
                    '-screen', '0', '1024x768x24',
                    '-nolisten', 'tcp',
                    '-ac'
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )

            for _ in range(10):
                time.sleep(0.5)
                if self._xvfb_process.poll() is not None:
                    stderr = ''
                    try:
                        stderr = (
                            self._xvfb_process
                            .stderr.read(300)
                        )
                    except Exception:
                        pass
                    self._add_log(
                        f"Xvfb exited: {stderr}",
                        'error'
                    )
                    return False

                if self._is_xvfb_running(display):
                    os.environ['DISPLAY'] = display
                    self._add_log(
                        f"✓ Xvfb started on {display}"
                    )
                    return True

            self._add_log(
                "Xvfb did not start in time",
                'warning'
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
            except Exception:
                pass
            finally:
                self._xvfb_process = None

    # ----------------------------------------------------------
    # Audio environment setup
    # ----------------------------------------------------------
    def _setup_audio_environment(self):
        """
        Configure virtual audio for FLdigi in Docker.

        The ALSA errors in FLdigi output are caused by
        ALSA trying to open physical hardware cards that
        don't exist. The fix is:
            1. Ensure PulseAudio is running with null sink
            2. Write ~/.asoundrc routing ALSA -> PulseAudio
            3. Set environment variables so FLdigi uses
               the PulseAudio ALSA plugin

        Returns:
            dict: Environment variables for FLdigi process
        """
        env = os.environ.copy()

        # -------------------------------------------------------
        # Step 1: Ensure PulseAudio is running
        # -------------------------------------------------------
        pa_running = False

        if shutil.which('pactl'):
            try:
                result = subprocess.run(
                    ['pactl', 'info'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                pa_running = (result.returncode == 0)
            except Exception:
                pass

        if not pa_running and shutil.which('pulseaudio'):
            self._add_log(
                "Starting PulseAudio with null sink..."
            )
            try:
                subprocess.run(
                    [
                        'pulseaudio',
                        '--start',
                        '--exit-idle-time=-1',
                        '--log-level=error'
                    ],
                    capture_output=True,
                    timeout=10
                )
                time.sleep(2)

                # Verify it started
                result = subprocess.run(
                    ['pactl', 'info'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                pa_running = (result.returncode == 0)

                if pa_running:
                    self._add_log("✓ PulseAudio started")
                else:
                    self._add_log(
                        "PulseAudio start failed",
                        'warning'
                    )
            except Exception as e:
                self._add_log(
                    f"PulseAudio error: {e}", 'warning'
                )

        # -------------------------------------------------------
        # Step 2: Load null sink if PulseAudio is running
        # -------------------------------------------------------
        if pa_running and shutil.which('pactl'):
            for module_cmd in [
                [
                    'pactl', 'load-module',
                    'module-null-sink',
                    'sink_name=fldigi_out',
                    'sink_properties='
                    'device.description=FLdigi_Output'
                ],
                [
                    'pactl', 'load-module',
                    'module-null-source',
                    'source_name=fldigi_in',
                    'source_properties='
                    'device.description=FLdigi_Input'
                ],
            ]:
                subprocess.run(
                    module_cmd,
                    capture_output=True,
                    timeout=5
                )

            # Set defaults
            subprocess.run(
                ['pactl', 'set-default-sink', 'fldigi_out'],
                capture_output=True, timeout=5
            )
            subprocess.run(
                ['pactl', 'set-default-source', 'fldigi_in'],
                capture_output=True, timeout=5
            )

        # -------------------------------------------------------
        # Step 3: Write .asoundrc routing ALSA -> PulseAudio
        # This is what stops the "cannot find card '0'" spam
        # -------------------------------------------------------
        asoundrc = os.path.expanduser('~/.asoundrc')

        if pa_running:
            alsa_config = (
                '# ALSA -> PulseAudio bridge\n'
                '# Generated by FLdigi plugin\n'
                'pcm.!default {\n'
                '    type pulse\n'
                '}\n'
                'ctl.!default {\n'
                '    type pulse\n'
                '}\n'
                'pcm.pulse { type pulse }\n'
                'ctl.pulse { type pulse }\n'
                'pcm.null { type null }\n'
            )
        else:
            # PulseAudio not available — use null device
            # to prevent FLdigi from crashing on audio init
            alsa_config = (
                '# ALSA null device (no PulseAudio)\n'
                '# Generated by FLdigi plugin\n'
                'pcm.!default { type null }\n'
                'ctl.!default { type null }\n'
                'pcm.null { type null }\n'
            )

        try:
            with open(asoundrc, 'w') as f:
                f.write(alsa_config)
            self._add_log(
                f"✓ ~/.asoundrc written "
                f"({'PulseAudio' if pa_running else 'null'})"
            )
        except Exception as e:
            self._add_log(
                f"~/.asoundrc write error: {e}",
                'warning'
            )

        # -------------------------------------------------------
        # Step 4: Set environment variables
        # -------------------------------------------------------

        # Tell PulseAudio clients to connect to default server
        if pa_running:
            env['PULSE_SERVER'] = 'unix:/run/user/1000/pulse/native'

        # Suppress ALSA error messages in FLdigi output
        # These are cosmetic only — FLdigi still works
        env['ALSA_CARD'] = '0'
        env['PULSE_LATENCY_MSEC'] = '30'

        # Force FLdigi to use PulseAudio audio backend
        # by setting the PortAudio device hint
        env['AUDIODEV'] = 'pulse'

        self._add_log(
            f"Audio environment ready "
            f"(PulseAudio: {'✓' if pa_running else '✗ using null'})"
        )

        return env

    # ----------------------------------------------------------
    # FLdigi process management
    # ----------------------------------------------------------

    def _build_fldigi_command(self, binary, display):
        """
        Build the FLdigi launch command.

        Args:
            binary: Full path to fldigi executable
            display: X11 display string

        Returns:
            list: Command and arguments
        """
        cmd = [binary]

        # XML-RPC server settings
        cmd.extend([
            '--xmlrpc-server-address',
            self.config.get('xmlrpc_host', 'localhost'),
            '--xmlrpc-server-port',
            str(self.config.get('xmlrpc_port', 7362)),
        ])

        # Dedicated config directory
        cmd.extend(['--config-dir', self.fldigi_home])

        return cmd
        
    def connect_to_existing(self):
        """
        Connect to an already-running FLdigi instance.

        Attempts to connect to the XML-RPC server.
        If connection is refused, provides clear guidance
        on how to start FLdigi.

        Returns:
            tuple: (success: bool, message: str)
        """
        host = self.config.get('xmlrpc_host', 'localhost')
        port = self.config.get('xmlrpc_port', 7362)

        self._add_log(
            f"Attempting XML-RPC connection to "
            f"{host}:{port}..."
        )

        # Check if FLdigi binary exists before trying
        binary = shutil.which('fldigi')
        if not binary:
            msg = (
                "FLdigi binary not found. "
                "Add fldigi to Dockerfile and rebuild: "
                "docker compose build --no-cache"
            )
            self._add_log(msg, 'error')
            return False, msg

        # Attempt XML-RPC connection
        if self.rpc.connect():
            version = self.rpc.get_version()
            self._status['xmlrpc_connected'] = True
            self._status['version'] = version
            self._update_status_from_rpc()
            self._start_monitor()
            self._add_log(
                f"✓ Connected to FLdigi {version}"
            )
            return True, f"Connected to FLdigi {version}"

        # Connection refused — FLdigi is not running
        msg = (
            "Cannot connect to FLdigi "
            f"({host}:{port}). "
            "FLdigi is not running. "
            "Click 'Start FLdigi' to launch it."
        )
        self._add_log(msg, 'warning')
        self._add_log(
            "To start manually inside the container: "
            "DISPLAY=:99 fldigi "
            "--xmlrpc-server-address localhost "
            f"--xmlrpc-server-port {port} &",
            'info'
        )
        return False, msg
        
    def start_fldigi(self):
        """
        Launch FLdigi with Xvfb virtual display and
        PulseAudio virtual audio.

        Complete startup sequence:
            1. Verify FLdigi binary exists
            2. Ensure Xvfb display is running
            3. Ensure PulseAudio null sink is available
            4. Launch FLdigi process
            5. Wait up to 30s for XML-RPC to respond
            6. Start log monitor on success

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:

            # Already running
            if self._process and \
                    self._process.poll() is None:
                return False, "FLdigi process already running"

            # Check binary
            binary = shutil.which('fldigi')
            if not binary:
                msg = (
                    "FLdigi binary not found. "
                    "Add fldigi to Dockerfile and rebuild."
                )
                self._add_log(msg, 'error')
                return False, msg

            try:
                # Step 1: Get or create display
                display = self._get_display()
                self._status['display'] = display
                self._add_log(f"Using display: {display}")

                # Step 2: Set up audio environment
                env = self._setup_audio_environment()
                env['DISPLAY'] = display

                # Step 3: Build command
                cmd = self._build_fldigi_command(
                    binary, display
                )
                self._add_log(
                    f"Launching: {' '.join(cmd)}"
                )

                # Step 4: Launch FLdigi
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
                    f"✓ FLdigi launched "
                    f"(PID: {self._process.pid})"
                )

                # Step 5: Monitor output
                self._start_output_monitor()

                # Step 6: Wait for XML-RPC
                host = self.config.get(
                    'xmlrpc_host', 'localhost'
                )
                port = self.config.get('xmlrpc_port', 7362)
                timeout = self.config.get(
                    'connect_timeout', 45
                )

                self._add_log(
                    f"Waiting for XML-RPC on "
                    f"localhost:{self.config.get('xmlrpc_port', 7362)} "
                    f"(up to {timeout}s — audio init may be slow)..."
                )

                connected = False
                for attempt in range(timeout // 2):
                    time.sleep(2)

                    # Check process still alive
                    if self._process.poll() is not None:
                        code = self._process.poll()
                        msg = (
                            f"FLdigi exited with code "
                            f"{code}. "
                            "Check display (Xvfb) and "
                            "audio (PulseAudio) are running."
                        )
                        self._add_log(msg, 'error')
                        self._status['process_running'] = (
                            False
                        )
                        return False, msg

                    if self.rpc.connect():
                        connected = True
                        version = self.rpc.get_version()
                        self._status[
                            'xmlrpc_connected'
                        ] = True
                        self._status['version'] = version
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
                    # FLdigi started but XML-RPC not ready
                    # This is not necessarily a failure —
                    # user may need to enable XML-RPC in
                    # FLdigi Configure menu
                    self._add_log(
                        "FLdigi started but XML-RPC is "
                        "not responding. "
                        "In FLdigi: Configure → "
                        "XML-RPC server → enable → "
                        f"port {port}",
                        'warning'
                    )
                    return (
                        True,
                        f"FLdigi started (PID "
                        f"{self._process.pid}) but "
                        f"XML-RPC not yet connected. "
                        f"Enable XML-RPC in FLdigi: "
                        f"Configure → XML-RPC → "
                        f"port {port}"
                    )

                return (
                    True,
                    f"FLdigi started and connected "
                    f"(PID: {self._process.pid})"
                )

            except Exception as e:
                msg = f"Failed to start FLdigi: {e}"
                self._add_log(msg, 'error')
                import traceback
                traceback.print_exc()
                return False, msg

    def stop_fldigi(self, save_options=True):
        """
        Stop FLdigi gracefully.

        Requests shutdown via XML-RPC first, then
        terminates the process if still running.

        Args:
            save_options: Ask FLdigi to save its config

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            # Graceful XML-RPC shutdown
            if self.rpc.is_connected():
                try:
                    self.rpc.terminate(save_options)
                    time.sleep(1)
                except Exception:
                    pass
                self.rpc.disconnect()

            self._status['xmlrpc_connected'] = False
            self._rx_monitor_active = False

            # Kill our managed process
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

            self._add_log("[FLdigi] ✓ FLdigi stopped")
            return True, "[FLdigi] stopped"

    # ----------------------------------------------------------
    # Process monitoring
    # ----------------------------------------------------------

    def _start_output_monitor(self):
        """
        Monitor FLdigi stdout/stderr in a background thread.

        Reads process output and stores in log buffer.
        Detects and logs early process termination.
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
                    stripped = line.strip()
                    if stripped:
                        self._add_log(stripped)
            except Exception as e:
                self._add_log(
                    f"[FLdigi] [init] Output monitor error: {e}", 'warning'
                )
            finally:
                code = (
                    self._process.poll()
                    if self._process else None
                )
                self._status['process_running'] = False
                self._status['pid'] = None

                if code is not None and code != 0:
                    self._add_log(
                        f"[FLdigi] [init] o/p monitor terminated "
                        f"(exit code: {code})",
                        'warning'
                    )
                else:
                    self._add_log(
                        "[FLdigi] [init] o/p monitor terminated"
                    )

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='fldigi-output-monitor'
        )
        thread.start()

    def _start_monitor(self):
        """
        Start background XML-RPC status monitor.

        Polls FLdigi status and detects new log entries
        at the configured interval.
        """
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
                        f"[FLdigi] [init] Monitor error: {e}", 'error'
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
        Check FLdigi log panel for new contacts.

        Reads callsign from the log panel and adds
        to pending contacts list if not already present.
        """
        try:
            callsign = self.rpc.get_log_callsign()
            if callsign and callsign.strip():
                entry = self.rpc.get_full_log_entry()
                if entry and entry.get('callsign'):
                    with self._contacts_lock:
                        existing = [
                            c for c in
                            self._pending_contacts
                            if c.get('callsign') ==
                            entry['callsign']
                        ]
                        if not existing:
                            self._pending_contacts.append(
                                entry
                            )
                            self._add_log(
                                f"Contact detected: "
                                f"{entry['callsign']}"
                            )
        except Exception:
            pass  # Log panel may be empty

    # ----------------------------------------------------------
    # Status
    # ----------------------------------------------------------

    def _update_status_from_rpc(self):
        """Update status dict from live XML-RPC queries."""
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
        """
        Get comprehensive FLdigi status.

        Checks process state, XML-RPC connectivity,
        and updates live values from FLdigi.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = (
            datetime.utcnow().isoformat()
        )

        # Check process state
        if self._process:
            if self._process.poll() is not None:
                self._status['process_running'] = False
                self._status['pid'] = None

        # Check XML-RPC connection
        if self._status.get('xmlrpc_connected'):
            if not self.rpc.is_connected():
                self._status['xmlrpc_connected'] = False
                self._add_log(
                    "XML-RPC connection lost", 'warning'
                )
            else:
                self._update_status_from_rpc()

        return dict(self._status)

    # ----------------------------------------------------------
    # Operations
    # ----------------------------------------------------------

    def get_pending_contacts(self):
        """
        Get and clear the pending contacts list.

        Returns:
            list: List of contact entry dicts
        """
        with self._contacts_lock:
            contacts = list(self._pending_contacts)
            self._pending_contacts.clear()
            return contacts

    def send_text(self, text, transmit=True):
        """
        Add text to FLdigi TX buffer.

        Args:
            text: Text to transmit
            transmit: If True, switch to TX mode

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"
        try:
            self.rpc.add_tx_text(text + '\n')
            if transmit:
                self.rpc.set_tx()
                self._add_log(f"TX: {text[:50]}")
            return True, "Text queued"
        except Exception as e:
            return False, f"TX error: {e}"

    def set_mode(self, mode_name):
        """
        Set FLdigi operating mode by name.

        Args:
            mode_name: Mode name string (e.g. 'BPSK31')

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"
        try:
            self.rpc.set_modem_by_name(mode_name)
            self._status['mode'] = mode_name
            self._add_log(f"Mode: {mode_name}")
            return True, f"Mode set to {mode_name}"
        except Exception as e:
            return False, f"Mode error: {e}"

    def set_frequency(self, freq_hz):
        """
        Set radio frequency.

        Args:
            freq_hz: Frequency in Hz (integer)

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.rpc.is_connected():
            return False, "FLdigi not connected"
        try:
            self.rpc.set_frequency(freq_hz)
            self._status['frequency'] = freq_hz
            freq_mhz = freq_hz / 1_000_000
            return True, f"Frequency: {freq_mhz:.3f} MHz"
        except Exception as e:
            return False, f"Frequency error: {e}"

    def get_available_modes(self):
        """
        Get list of available FLdigi mode names.

        Queries XML-RPC if connected, otherwise returns
        a hardcoded fallback list.

        Returns:
            list: Sorted mode name strings
        """
        if self.rpc.is_connected():
            try:
                modes = self.rpc.get_modem_names()
                if modes:
                    return sorted(list(modes))
            except Exception:
                pass

        # Hardcoded fallback
        return sorted([
            'BPSK31', 'BPSK63', 'BPSK125', 'BPSK250',
            'BPSK500', 'BPSK1000',
            'QPSK31', 'QPSK63', 'QPSK125', 'QPSK250',
            'RTTY', 'RTTY-45', 'RTTY-50', 'RTTY-75',
            'MFSK-8', 'MFSK-16', 'MFSK-22', 'MFSK-32',
            'MFSK-64', 'MFSK-128',
            'OLIVIA-4/250', 'OLIVIA-8/250',
            'OLIVIA-8/500', 'OLIVIA-16/500',
            'OLIVIA-32/1000', 'OLIVIA-64/2000',
            'CW', 'WSPR',
            'MT63-500', 'MT63-1000', 'MT63-2000',
            'THOR-8', 'THOR-16', 'THOR-22',
            'DOMINO-11', 'DOMINO-22',
            'CONTESTIA-4/250', 'CONTESTIA-8/500',
        ])

    def get_rx_text(self):
        """
        Get the current RX text buffer content.

        Returns:
            str: Received text or empty string
        """
        if not self.rpc.is_connected():
            return ''
        try:
            return self.rpc.get_rx_text_full() or ''
        except Exception:
            return ''

    def abort_tx(self):
        """
        Abort the current transmission and switch to RX.

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.rpc.is_connected():
            return False, "Not connected"
        try:
            self.rpc.abort()
            self.rpc.set_rx()
            self._status['trx_status'] = 'rx'
            self._add_log("TX aborted")
            return True, "TX aborted"
        except Exception as e:
            return False, f"TX Abort error: {e}"

    def _build_fldigi_command(self, binary, display):
        """Build FLdigi command with correct settings."""
        cmd = [binary]

        # XML-RPC server
        cmd.extend([
            '--xmlrpc-server-address',
            self.config.get('xmlrpc_host', 'localhost'),
            '--xmlrpc-server-port',
            str(self.config.get('xmlrpc_port', 7362)),
        ])

        # Config directory
        cmd.extend(['--config-dir', self.fldigi_home])

        return cmd

    def _build_env(self, display):
        """
        Build environment for FLdigi/Qt apps.
    
        Args:
            display: X11 display string
    
        Returns:
            dict: Environment variables
        """
        env = os.environ.copy()
        env['DISPLAY'] = display
    
        # Force xcb platform — prevents :0 fallback
        env['QT_QPA_PLATFORM'] = 'xcb'
        env['QT_ACCESSIBILITY'] = '0'
    
        # Find and set Qt plugin path
        qt_plugin = self._find_qt_plugin_path()
        if qt_plugin:
            env['QT_PLUGIN_PATH'] = qt_plugin
    
        return env
