"""
OpenWebRX Process Manager
==========================
Manages the OpenWebRX process lifecycle, configuration,
and communication.

OpenWebRX can run as:
    - Docker container (recommended)
    - System service (apt installation)
    - Direct Python process (pip installation)

Communication:
    - HTTP API for status and control
    - WebSocket for real-time data
    - Config file management

Reference: https://github.com/jketterl/openwebrx/wiki
"""

import os
import json
import time
import shutil
import threading
import subprocess
from datetime import datetime

# Handle optional imports gracefully
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class OpenWebRXManager:
    """
    Manages OpenWebRX instance lifecycle and configuration.

    Supports Docker, system service, and direct process modes.
    Provides unified interface regardless of installation method.
    """

    # OpenWebRX API endpoints
    API_STATUS = '/api/status'
    API_FEATURES = '/api/features'
    API_RECEIVERS = '/api/receivers'
    API_BANDS = '/api/bands'

    # Docker container name
    CONTAINER_NAME = 'hamradio_openwebrx'

    def __init__(self, config_dir, install_method='docker',
                 http_port=8073):
        """
        Initialize the OpenWebRX manager.

        Args:
            config_dir: Directory for OpenWebRX configuration
            install_method: How OpenWebRX was installed
                           ('docker', 'apt', 'pip')
            http_port: HTTP port for OpenWebRX web interface
        """
        self.config_dir = config_dir
        self.install_method = install_method
        self.http_port = http_port
        self.base_url = f'http://localhost:{http_port}'

        # Process/container reference
        self._process = None
        self._process_lock = threading.Lock()

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Status tracking
        self._status = {
            'running': False,
            'connected': False,
            'url': self.base_url,
            'port': http_port,
            'method': install_method,
            'users': 0,
            'receivers': [],
            'last_check': None,
            'error': None,
            'container_id': None
        }

        # Detected signals for logbook integration
        self._detected_signals = []
        self._signal_lock = threading.Lock()

        # Load configuration
        self.config = self._load_config()

        # Ensure directories exist
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(os.path.join(config_dir, 'openwebrx'), exist_ok=True)

    def _load_config(self):
        """
        Load OpenWebRX plugin configuration.

        Returns:
            dict: Configuration with defaults applied
        """
        config_file = os.path.join(self.config_dir, 'openwebrx_config.json')

        defaults = {
            # Server settings
            'http_port': 8073,
            'allow_anonymous': True,

            # SDR Device settings
            'sdr_type': 'rtlsdr',
            'sdr_device_index': 0,
            'center_frequency': 145000000,  # 145 MHz
            'sample_rate': 2048000,
            'gain': 30,
            'ppm': 0,

            # Profile settings
            'receiver_name': 'Ham Radio SDR',
            'receiver_location': '',
            'receiver_asl': 0,
            'receiver_admin': '',
            'receiver_gps': {'lat': 0.0, 'lon': 0.0},
            'photo_title': 'Ham Radio Station',

            # Bands to monitor
            'initial_frequency': 145000000,
            'initial_modulation': 'nfm',

            # Auto-start setting
            'auto_start': False,

            # Signal logging settings
            'log_signals': True,
            'min_signal_strength': -70,  # dBm threshold for logging
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[OpenWebRX] Warning: Could not load config: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration to file.

        Args:
            config_data: Dictionary of configuration values

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(self.config_dir, 'openwebrx_config.json')

        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print("[OpenWebRX] ✓ Configuration saved")
            return True
        except Exception as e:
            print(f"[OpenWebRX] ERROR: Could not save config: {e}")
            return False

    def generate_openwebrx_config(self):
        """
        Generate OpenWebRX configuration files.

        Creates the config_webrx.py and bands.json files
        required by OpenWebRX.

        Returns:
            bool: True if generated successfully
        """
        owrx_config_dir = os.path.join(self.config_dir, 'openwebrx')
        os.makedirs(owrx_config_dir, exist_ok=True)

        # Generate config_webrx.py
        config_content = f'''# OpenWebRX Configuration
# Generated by Ham Radio App Plugin
# Reference: https://github.com/jketterl/openwebrx/wiki/Configuration-guide

# ==============================================================
# Server Configuration
# ==============================================================
web_port = {self.config.get('http_port', 8073)}

# ==============================================================
# Receiver Information
# ==============================================================
receiver_name = "{self.config.get('receiver_name', 'Ham Radio SDR')}"
receiver_location = "{self.config.get('receiver_location', '')}"
receiver_asl = {self.config.get('receiver_asl', 0)}
receiver_admin = "{self.config.get('receiver_admin', '')}"
receiver_gps = {self.config.get('receiver_gps', {'lat': 0.0, 'lon': 0.0})}
photo_title = "{self.config.get('photo_title', 'Ham Radio Station')}"

# ==============================================================
# SDR Device Configuration
# ==============================================================
sdrs = {{
    "rtlsdr": {{
        "name": "RTL-SDR",
        "type": "{self.config.get('sdr_type', 'rtlsdr')}",
        "device_index": {self.config.get('sdr_device_index', 0)},
        "ppm": {self.config.get('ppm', 0)},
        "gain": {self.config.get('gain', 30)},
        "rf_gain": {self.config.get('gain', 30)},
        "profiles": {{
            "2m": {{
                "name": "2m Band",
                "center_freq": 145000000,
                "samp_rate": {self.config.get('sample_rate', 2048000)},
                "start_freq": {self.config.get('initial_frequency', 145000000)},
                "start_mod": "{self.config.get('initial_modulation', 'nfm')}",
            }},
            "airband": {{
                "name": "Airband",
                "center_freq": 118000000,
                "samp_rate": 2048000,
                "start_freq": 121500000,
                "start_mod": "am",
            }},
            "hf": {{
                "name": "HF 20m",
                "center_freq": 14100000,
                "samp_rate": 2048000,
                "start_freq": 14074000,
                "start_mod": "usb",
            }},
            "weather": {{
                "name": "NOAA Weather",
                "center_freq": 162500000,
                "samp_rate": 1024000,
                "start_freq": 162550000,
                "start_mod": "wfm",
            }},
        }},
    }},
}}
'''

        try:
            config_path = os.path.join(owrx_config_dir, 'config_webrx.py')
            with open(config_path, 'w') as f:
                f.write(config_content)
            print(f"[OpenWebRX] ✓ Config generated: {config_path}")
            return True
        except Exception as e:
            print(f"[OpenWebRX] ERROR: Config generation failed: {e}")
            return False

    def _add_log(self, message, level='info'):
        """
        Add entry to in-memory log buffer.

        Args:
            message: Log message
            level: Log level (info, warning, error)
        """
        with self._log_lock:
            self._logs.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message
            })

            # Trim buffer
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """
        Get recent log entries.

        Args:
            limit: Maximum entries to return

        Returns:
            list: Recent log entries newest first
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def start(self):
        """
        Start OpenWebRX using the appropriate method.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            # Check if already running
            if self._status['running']:
                return False, "OpenWebRX is already running"

            # Generate configuration
            self.generate_openwebrx_config()

            # Start based on installation method
            if self.install_method == 'docker':
                return self._start_docker()
            elif self.install_method == 'apt':
                return self._start_service()
            else:
                return self._start_process()

    def _start_docker(self):
        """
        Start OpenWebRX as a Docker container.

        Mounts the config directory and exposes the web port.

        Returns:
            tuple: (success, message)
        """
        owrx_config_dir = os.path.join(self.config_dir, 'openwebrx')

        try:
            self._add_log("Starting OpenWebRX Docker container...")

            # Build docker run command
            cmd = [
                'docker', 'run', '-d',
                '--name', self.CONTAINER_NAME,
                '--rm',  # Remove on stop
                '-p', f'{self.http_port}:{self.http_port}',
                '-v', f'{owrx_config_dir}:/etc/openwebrx',
                # Add RTL-SDR device if available
                '--device=/dev/bus/usb',
                # Set privileged for USB device access
                '--privileged',
                'jketterl/openwebrx:latest'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                container_id = result.stdout.strip()
                self._status['running'] = True
                self._status['container_id'] = container_id
                self._status['error'] = None

                self._add_log(
                    f"✓ Container started: {container_id[:12]}"
                )

                # Start monitoring thread
                self._start_monitor()

                return True, f"OpenWebRX started (container: {container_id[:12]})"
            else:
                # Check if container already exists
                if 'already in use' in result.stderr:
                    # Remove existing container and retry
                    subprocess.run(
                        ['docker', 'rm', '-f', self.CONTAINER_NAME],
                        capture_output=True
                    )
                    return self._start_docker()

                error = result.stderr.strip()
                self._status['error'] = error
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Docker start failed: {error}"

        except Exception as e:
            error = str(e)
            self._status['error'] = error
            self._add_log(f"ERROR: {error}", 'error')
            return False, f"Error starting container: {error}"

    def _start_service(self):
        """
        Start OpenWebRX as a system service.

        Returns:
            tuple: (success, message)
        """
        try:
            self._add_log("Starting OpenWebRX system service...")

            result = subprocess.run(
                ['sudo', 'systemctl', 'start', 'openwebrx'],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                self._status['running'] = True
                self._add_log("✓ Service started")
                self._start_monitor()
                return True, "OpenWebRX service started"
            else:
                error = result.stderr.strip()
                self._status['error'] = error
                return False, f"Service start failed: {error}"

        except Exception as e:
            return False, f"Error starting service: {str(e)}"

    def _start_process(self):
        """
        Start OpenWebRX as a direct process.

        Checks for binary availability before attempting
        to start. Returns a clear error if not found
        instead of raising FileNotFoundError.

        Returns:
            tuple: (success, message)
        """
        # Check for binary before attempting to start
        owrx_binary = (
            shutil.which('openwebrx') or
            shutil.which('/usr/bin/openwebrx') or
            shutil.which('/usr/local/bin/openwebrx')
        )

        if not owrx_binary:
            msg = (
                "OpenWebRX binary not found. "
                "It must be installed in the Docker image. "
                "Add to Dockerfile: "
                "RUN apt-get install -y openwebrx "
                "and rebuild with: "
                "docker compose build --no-cache"
            )
            self._add_log(msg, 'warning')
            return False, msg

        try:
            owrx_config_dir = os.path.join(
                self.config_dir, 'openwebrx'
            )

            self._add_log(
                f"Starting OpenWebRX: {owrx_binary}"
            )

            self._process = subprocess.Popen(
                [owrx_binary],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=owrx_config_dir
            )

            self._status['running'] = True
            self._status['pid'] = self._process.pid
            self._add_log(
                f"✓ Process started "
                f"(PID: {self._process.pid})"
            )
            self._start_monitor()

            return True, (
                f"OpenWebRX started "
                f"(PID: {self._process.pid})"
            )

        except FileNotFoundError:
            msg = (
                f"OpenWebRX not found at {owrx_binary}. "
                "Rebuild Docker image with OpenWebRX installed."
            )
            self._add_log(msg, 'error')
            return False, msg

        except Exception as e:
            msg = f"Error starting OpenWebRX: {str(e)}"
            self._add_log(msg, 'error')
            return False, msg

    def stop(self):
        """
        Stop OpenWebRX using the appropriate method.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if not self._status['running']:
                return False, "OpenWebRX is not running"

            if self.install_method == 'docker':
                return self._stop_docker()
            elif self.install_method == 'apt':
                return self._stop_service()
            else:
                return self._stop_process()

    def _stop_docker(self):
        """
        Stop and remove the OpenWebRX Docker container.

        Returns:
            tuple: (success, message)
        """
        try:
            self._add_log("Stopping OpenWebRX container...")

            result = subprocess.run(
                ['docker', 'stop', self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=30
            )

            self._status['running'] = False
            self._status['connected'] = False
            self._status['container_id'] = None

            self._add_log("✓ Container stopped")
            return True, "OpenWebRX container stopped"

        except Exception as e:
            return False, f"Error stopping container: {str(e)}"

    def _stop_service(self):
        """
        Stop OpenWebRX system service.

        Returns:
            tuple: (success, message)
        """
        try:
            subprocess.run(
                ['sudo', 'systemctl', 'stop', 'openwebrx'],
                capture_output=True,
                text=True,
                timeout=15
            )

            self._status['running'] = False
            self._status['connected'] = False
            self._add_log("✓ Service stopped")
            return True, "OpenWebRX service stopped"

        except Exception as e:
            return False, f"Error stopping service: {str(e)}"

    def _stop_process(self):
        """
        Stop the OpenWebRX direct process.

        Returns:
            tuple: (success, message)
        """
        try:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()

                self._process = None

            self._status['running'] = False
            self._status['connected'] = False
            self._add_log("✓ Process stopped")
            return True, "OpenWebRX process stopped"

        except Exception as e:
            return False, f"Error stopping process: {str(e)}"

    def get_status(self):
        """
        Get current OpenWebRX status.

        Queries the OpenWebRX API for detailed status
        when the service is running.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check if running via API ping
        if self._status['running']:
            api_status = self._query_api(self.API_STATUS)
            if api_status:
                self._status['connected'] = True
                self._status['users'] = api_status.get('users', 0)
            else:
                self._status['connected'] = False

            # Verify Docker container is still running
            if self.install_method == 'docker':
                if not self._check_container_running():
                    self._status['running'] = False
                    self._status['connected'] = False
                    self._add_log(
                        "Container stopped unexpectedly", 'warning'
                    )

        return dict(self._status)

    def _check_container_running(self):
        """
        Check if the OpenWebRX Docker container is running.

        Returns:
            bool: True if container is running
        """
        try:
            result = subprocess.run(
                ['docker', 'inspect', '-f', '{{.State.Running}}',
                 self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() == 'true'
        except Exception:
            return False

    def _query_api(self, endpoint):
        """
        Query the OpenWebRX HTTP API.

        Args:
            endpoint: API endpoint path

        Returns:
            dict: API response or None on error
        """
        if not REQUESTS_AVAILABLE:
            return None

        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

    def _start_monitor(self):
        """
        Start background monitoring thread.

        Periodically checks OpenWebRX status and
        monitors for detected signals.
        """
        def monitor():
            """Background monitoring function."""
            while self._status['running']:
                try:
                    # Update status
                    self.get_status()

                    # Check for signals if logging enabled
                    if self.config.get('log_signals', True):
                        self._check_for_signals()

                except Exception as e:
                    self._add_log(f"Monitor error: {e}", 'error')

                time.sleep(30)  # Check every 30 seconds

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='openwebrx-monitor'
        )
        thread.start()

    def _check_for_signals(self):
        """
        Query OpenWebRX for detected digital mode signals.

        Retrieves decoded signals from digital modes
        for potential logbook entries.
        """
        # Query for receiver data
        receiver_data = self._query_api(self.API_RECEIVERS)

        if not receiver_data:
            return

        # Look for decoded digital mode data
        with self._signal_lock:
            # Process any spots or decoded transmissions
            if isinstance(receiver_data, dict):
                spots = receiver_data.get('spots', [])
                for spot in spots:
                    # Build signal entry
                    signal = {
                        'callsign': spot.get('callsign', 'UNKNOWN'),
                        'frequency': spot.get('freq'),
                        'mode': spot.get('mode', 'DIGITAL'),
                        'snr': spot.get('snr'),
                        'timestamp': datetime.utcnow().isoformat()
                    }

                    # Add to detected signals
                    self._detected_signals.append(signal)

                    # Keep last 100 signals
                    if len(self._detected_signals) > 100:
                        self._detected_signals = self._detected_signals[-100:]

    def get_detected_signals(self, limit=50):
        """
        Get recently detected signals.

        Args:
            limit: Maximum signals to return

        Returns:
            list: Recently detected signals
        """
        with self._signal_lock:
            return list(reversed(self._detected_signals[-limit:]))

    def get_web_url(self):
        """
        Get the OpenWebRX web interface URL.

        Returns:
            str: Full URL to OpenWebRX interface
        """
        return f"http://localhost:{self.config.get('http_port', 8073)}"

    def is_available(self):
        """
        Check if OpenWebRX is accessible via HTTP.

        Returns:
            bool: True if web interface responds
        """
        if not REQUESTS_AVAILABLE:
            return False

        try:
            response = requests.get(
                self.base_url,
                timeout=3
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_band_plan(self):
        """
        Get the configured band plan from OpenWebRX.

        Returns:
            list: Band plan entries
        """
        return self._query_api(self.API_BANDS) or []
