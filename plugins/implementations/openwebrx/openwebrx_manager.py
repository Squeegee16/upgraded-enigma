"""
OpenWebRX Manager - Updated for sidecar Docker deployment.

OpenWebRX runs as a separate container (openwebrx service)
accessible via http://openwebrx:8073 within the Docker
network, or http://localhost:8073 from the host.

The OPENWEBRX_URL environment variable controls the URL.
"""

import os
import json
import shutil
import threading
import subprocess
import time
from datetime import datetime

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
    Manages OpenWebRX communication and configuration.

    In Docker deployment, OpenWebRX runs as a sidecar
    container. This manager communicates with it via
    HTTP rather than launching a local process.
    """

    # API endpoints
    API_STATUS = '/api/status'
    API_FEATURES = '/api/features'
    API_RECEIVERS = '/api/receivers'

    # Container name for Docker management
    CONTAINER_NAME = 'hamradio_openwebrx'

    def __init__(self, config_dir, install_method='sidecar',
                 http_port=8073):
        """
        Initialise OpenWebRX manager.

        Args:
            config_dir: Plugin configuration directory
            install_method: How OpenWebRX is deployed
            http_port: OpenWebRX HTTP port
        """
        self.config_dir = config_dir
        self.install_method = install_method
        self.http_port = http_port

        # Determine OpenWebRX base URL
        # Use OPENWEBRX_URL env var if set (Docker network)
        # otherwise fall back to localhost
        self.base_url = os.environ.get(
            'OPENWEBRX_URL',
            f'http://localhost:{http_port}'
        )

        print(
            f"[OpenWebRX] Manager URL: {self.base_url}"
        )

        # Process handle (only used in direct-process mode)
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

        # Detected signals
        self._detected_signals = []
        self._signal_lock = threading.Lock()

        # Load config
        self.config = self._load_config()
        os.makedirs(config_dir, exist_ok=True)

    def _load_config(self):
        """Load plugin configuration with defaults."""
        config_file = os.path.join(
            self.config_dir, 'openwebrx_config.json'
        )

        defaults = {
            'http_port': self.http_port,
            'openwebrx_url': self.base_url,
            'allow_anonymous': True,
            'sdr_type': 'rtlsdr',
            'sdr_device_index': 0,
            'center_frequency': 145000000,
            'sample_rate': 2048000,
            'gain': 30,
            'ppm': 0,
            'receiver_name': 'Ham Radio SDR',
            'receiver_location': '',
            'receiver_asl': 0,
            'receiver_admin': '',
            'receiver_gps': {'lat': 0.0, 'lon': 0.0},
            'photo_title': 'Ham Radio Station',
            'initial_frequency': 145000000,
            'initial_modulation': 'nfm',
            'auto_start': False,
            'log_signals': True,
            'min_signal_strength': -70,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
                    # Update URL from config
                    self.base_url = defaults.get(
                        'openwebrx_url', self.base_url
                    )
            except Exception as e:
                print(
                    f"[OpenWebRX] Config load error: {e}"
                )

        return defaults

    def save_config(self, config_data):
        """Save plugin configuration."""
        config_file = os.path.join(
            self.config_dir, 'openwebrx_config.json'
        )
        try:
            self.config.update(config_data)
            # Update URL if changed
            if 'openwebrx_url' in config_data:
                self.base_url = config_data['openwebrx_url']
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[OpenWebRX] Config save error: {e}")
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

    def start(self):
        """
        Start OpenWebRX.

        In sidecar mode, checks if the container is
        already running and accessible. If not, attempts
        to start the Docker container.

        In direct process mode, launches the binary.

        Returns:
            tuple: (success, message)
        """
        # Check if already accessible
        if self.is_available():
            self._status['running'] = True
            self._status['connected'] = True
            self._add_log(
                "✓ OpenWebRX is already running and accessible"
            )
            return True, "OpenWebRX is running"

        # Sidecar / Docker mode
        if self.install_method in ('sidecar', 'docker'):
            return self._start_sidecar()

        # Direct process mode
        return self._start_direct_process()

    def _start_sidecar(self):
        """
        Start/restart the OpenWebRX Docker container.

        Uses docker commands to start the container
        defined in docker-compose.yml.

        Returns:
            tuple: (success, message)
        """
        if not shutil.which('docker'):
            msg = (
                "OpenWebRX runs as a Docker sidecar. "
                "It should start automatically with "
                "docker compose up. "
                f"Check container status: "
                f"docker compose ps"
            )
            self._add_log(msg, 'warning')
            return False, msg

        self._add_log(
            "Attempting to start OpenWebRX container..."
        )

        try:
            # Try docker compose start
            result = subprocess.run(
                ['docker', 'compose', 'start', 'openwebrx'],
                capture_output=True,
                text=True,
                timeout=15,
                cwd='/app'
            )

            if result.returncode == 0:
                self._add_log(
                    "✓ OpenWebRX container started"
                )
                # Wait for it to become available
                for i in range(10):
                    time.sleep(2)
                    if self.is_available():
                        self._status['running'] = True
                        self._status['connected'] = True
                        return True, "OpenWebRX started"

                return True, (
                    "OpenWebRX container started. "
                    "Waiting for service to be ready..."
                )

            # Try docker start directly
            result2 = subprocess.run(
                ['docker', 'start', self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result2.returncode == 0:
                self._add_log(
                    "✓ OpenWebRX container started"
                )
                return True, "OpenWebRX container started"

            # Container not found - it needs to be started
            # via docker compose from the project directory
            msg = (
                "OpenWebRX container not running. "
                "Run: docker compose up -d openwebrx"
            )
            self._add_log(msg, 'warning')
            return False, msg

        except Exception as e:
            msg = (
                f"OpenWebRX sidecar start error: {e}. "
                "Ensure docker compose is running."
            )
            self._add_log(msg, 'error')
            return False, msg

    def _start_direct_process(self):
        """
        Launch OpenWebRX as a direct process.

        Only used outside Docker. Checks for binary
        before attempting to start.

        Returns:
            tuple: (success, message)
        """
        # Locate binary
        owrx_binary = (
            shutil.which('openwebrx') or
            shutil.which('/usr/bin/openwebrx') or
            shutil.which('/usr/local/bin/openwebrx')
        )

        if not owrx_binary:
            msg = (
                "OpenWebRX binary not found. "
                "When using Docker, OpenWebRX runs as a "
                "sidecar container (openwebrx service). "
                "Ensure docker-compose.yml includes the "
                "openwebrx service and run: "
                "docker compose up -d"
            )
            self._add_log(msg, 'warning')
            return False, msg

        try:
            self.generate_openwebrx_config()
            self._add_log(
                f"Starting OpenWebRX: {owrx_binary}"
            )

            self._process = subprocess.Popen(
                [owrx_binary],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
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
                "OpenWebRX binary not executable. "
                "Use docker compose to deploy OpenWebRX."
            )
            self._add_log(msg, 'error')
            return False, msg
        except Exception as e:
            msg = f"OpenWebRX start error: {e}"
            self._add_log(msg, 'error')
            return False, msg

    def stop(self):
        """Stop OpenWebRX."""
        if self.install_method in ('sidecar', 'docker'):
            return self._stop_sidecar()

        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None
                self._status['running'] = False
                return True, "OpenWebRX stopped"
            except Exception as e:
                return False, str(e)

        return False, "OpenWebRX not running"

    def _stop_sidecar(self):
        """Stop the OpenWebRX Docker sidecar."""
        if not shutil.which('docker'):
            return False, "Docker not available"

        try:
            result = subprocess.run(
                ['docker', 'stop', self.CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                self._status['running'] = False
                self._status['connected'] = False
                return True, "OpenWebRX container stopped"

            return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)

    def get_status(self):
        """Get current OpenWebRX status."""
        self._status['last_check'] = (
            datetime.utcnow().isoformat()
        )

        # Probe HTTP API
        api_data = self._query_api(self.API_STATUS)
        if api_data:
            self._status['running'] = True
            self._status['connected'] = True
            self._status['users'] = api_data.get('users', 0)
            self._status['error'] = None
        else:
            # Not reachable - check if container exists
            self._status['connected'] = False
            if self.install_method in ('sidecar', 'docker'):
                self._status['running'] = (
                    self._check_container_exists()
                )
            elif self._process:
                self._status['running'] = (
                    self._process.poll() is None
                )
            else:
                self._status['running'] = False

        return dict(self._status)

    def _check_container_exists(self):
        """Check if the OpenWebRX container exists."""
        if not shutil.which('docker'):
            return False
        try:
            result = subprocess.run(
                [
                    'docker', 'inspect',
                    '-f', '{{.State.Running}}',
                    self.CONTAINER_NAME
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() == 'true'
        except Exception:
            return False

    def is_available(self):
        """
        Check if OpenWebRX HTTP interface is accessible.

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
            return response.status_code in (200, 301, 302)
        except Exception:
            return False

    def _query_api(self, endpoint):
        """Query OpenWebRX HTTP API."""
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

    def generate_openwebrx_config(self):
        """Generate OpenWebRX config_webrx.py file."""
        owrx_config_dir = os.path.join(
            self.config_dir, 'openwebrx'
        )
        os.makedirs(owrx_config_dir, exist_ok=True)

        config_content = f'''# OpenWebRX Configuration
# Generated by Ham Radio App Plugin

web_port = {self.config.get('http_port', 8073)}

receiver_name = "{self.config.get('receiver_name', 'Ham Radio SDR')}"
receiver_location = "{self.config.get('receiver_location', '')}"
receiver_asl = {self.config.get('receiver_asl', 0)}
receiver_admin = "{self.config.get('receiver_admin', '')}"
receiver_gps = {self.config.get('receiver_gps', {'lat': 0.0, 'lon': 0.0})}
photo_title = "{self.config.get('photo_title', 'Ham Radio Station')}"

sdrs = {{
    "rtlsdr": {{
        "name": "RTL-SDR",
        "type": "{self.config.get('sdr_type', 'rtlsdr')}",
        "device_index": {self.config.get('sdr_device_index', 0)},
        "ppm": {self.config.get('ppm', 0)},
        "gain": {self.config.get('gain', 30)},
        "profiles": {{
            "2m": {{
                "name": "2m Band",
                "center_freq": 145000000,
                "samp_rate": {self.config.get('sample_rate', 2048000)},
                "start_freq": {self.config.get('initial_frequency', 145000000)},
                "start_mod": "{self.config.get('initial_modulation', 'nfm')}",
            }},
            "hf": {{
                "name": "HF 20m",
                "center_freq": 14100000,
                "samp_rate": 2048000,
                "start_freq": 14074000,
                "start_mod": "usb",
            }},
        }},
    }},
}}
'''
        try:
            config_path = os.path.join(
                owrx_config_dir, 'config_webrx.py'
            )
            with open(config_path, 'w') as f:
                f.write(config_content)
            print(
                f"[OpenWebRX] ✓ Config generated: "
                f"{config_path}"
            )
            return True
        except Exception as e:
            print(
                f"[OpenWebRX] Config error: {e}"
            )
            return False

    def get_web_url(self):
        """Get the OpenWebRX web interface URL."""
        # Return the host-accessible URL
        return (
            f"http://localhost:"
            f"{self.config.get('http_port', 8073)}"
        )

    def get_detected_signals(self, limit=50):
        """Get recently detected signals."""
        with self._signal_lock:
            return list(
                reversed(self._detected_signals[-limit:])
            )

    def _start_monitor(self):
        """Start background status monitor."""
        def monitor():
            while (self._process and
                   self._process.poll() is None):
                try:
                    self.get_status()
                except Exception:
                    pass
                time.sleep(30)

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='openwebrx-monitor'
        )
        thread.start()
