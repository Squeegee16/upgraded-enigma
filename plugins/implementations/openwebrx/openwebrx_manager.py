"""
OpenWebRX Manager
==================
Manages communication with the OpenWebRX sidecar
container via HTTP API and optional WebSocket.

OpenWebRX HTTP API endpoints:
    GET  /api/status         - Server status
    GET  /api/features       - Available features
    GET  /api/receivers      - Configured SDR devices
    GET  /api/bands          - Band plan data
    POST /api/set_frequency  - Set receiver frequency
    POST /api/set_modulation - Set demodulation mode

OpenWebRX is accessed at:
    Docker: http://openwebrx:8073 (internal network)
    Host:   http://localhost:8073

Signal spots/decodes are available via:
    WebSocket ws://openwebrx:8073/ws/ (real-time)
    HTTP polling /api/status (fallback)

Reference:
    https://github.com/jketterl/openwebrx/wiki/HTTP-API
"""

import os
import json
import threading
import time
from datetime import datetime
from collections import deque

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class OpenWebRXManager:
    """
    Manages OpenWebRX container communication.

    Provides:
        - HTTP API queries for status and configuration
        - Receiver/profile management
        - Signal detection polling for logbook
        - Configuration persistence
        - Connection state management
    """

    # OpenWebRX API endpoints
    API_STATUS = '/api/status'
    API_FEATURES = '/api/features'
    API_RECEIVERS = '/api/receivers'
    API_BANDS = '/api/bands'
    API_VERSION = '/api/version'

    def __init__(self, config_dir, base_url=None):
        """
        Initialise the OpenWebRX manager.

        Args:
            config_dir: Plugin data directory
            base_url: OpenWebRX URL (auto-detect if None)
        """
        self.config_dir = config_dir
        os.makedirs(config_dir, exist_ok=True)

        # Determine OpenWebRX URL.
        # Priority: env var -> config -> docker default
        self.base_url = (
            base_url or
            os.environ.get(
                'OPENWEBRX_URL',
                'http://openwebrx:8073'
            )
        )

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Detected signal spots (from API polling)
        self._spots = deque(maxlen=500)
        self._spots_lock = threading.Lock()

        # Background polling thread
        self._poll_thread = None
        self._polling = False

        # Status cache
        self._status_cache = {}
        self._status_cache_time = 0
        self._status_cache_ttl = 10  # seconds

        # Load config
        self.config = self._load_config()

        # Update base_url from config if set
        config_url = self.config.get('openwebrx_url', '')
        if config_url:
            self.base_url = config_url

    # ----------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------

    def _load_config(self):
        """Load plugin configuration."""
        config_file = os.path.join(
            self.config_dir, 'openwebrx_config.json'
        )
        defaults = {
            'openwebrx_url': os.environ.get(
                'OPENWEBRX_URL', 'http://0.0.0.0:8073'
            ),
            'http_port': 8073,
            'log_ft8': True,
            'log_wspr': True,
            'log_aprs': True,
            'log_other': False,
            'min_snr_log': -20,
            'poll_interval': 15,
            'receiver_name': 'Ham SDR',
            'callsign': '',
            'locator': '',
            'admin_password': '',
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(
                    f"[OpenWebRX][init] Config load error: {e}"
                )

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration.

        Args:
            config_data: Configuration dict to save

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(
            self.config_dir, 'openwebrx_config.json'
        )
        try:
            self.config.update(config_data)

            # Update base_url if changed
            if 'openwebrx_url' in config_data:
                self.base_url = config_data['openwebrx_url']

            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            print("[OpenWebRX][init] ✓ Configuration saved")
            return True
        except Exception as e:
            print(f"[OpenWebRX][init] Config save error: {e}")
            return False

    # ----------------------------------------------------------
    # Logging
    # ----------------------------------------------------------

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

    # ----------------------------------------------------------
    # HTTP API communication
    # ----------------------------------------------------------

    def _get(self, endpoint, timeout=8):
        """
        Make a GET request to the OpenWebRX API.

        Args:
            endpoint: API path (e.g. '/api/status')
            timeout: Request timeout in seconds

        Returns:
            dict or None: Parsed JSON response
        """
        if not REQUESTS_AVAILABLE:
            return None

        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(
                url,
                timeout=timeout,
                headers={'Accept': 'application/json'}
            )
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception:
                    return {
                        'raw': response.text[:200]
                    }
            return None
        except Exception as e:
            print(
                f"[OpenWebRX][init] get msg format error: {e}"
            )
            return None

    def _post(self, endpoint, data=None, timeout=8):
        """
        Make a POST request to the OpenWebRX API.

        Args:
            endpoint: API path
            data: JSON data to send
            timeout: Request timeout

        Returns:
            dict or None: Parsed JSON response
        """
        if not REQUESTS_AVAILABLE:
            return None

        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.post(
                url,
                json=data or {},
                timeout=timeout
            )
            if response.status_code in (200, 204):
                try:
                    return response.json()
                except Exception:
                    return {'success': True}
            return None
        except Exception as e:
            print(
                f"[OpenWebRX][init] post msg format error: {e}"
            )
            return None

    # ----------------------------------------------------------
    # Status and availability
    # ----------------------------------------------------------

    def is_available(self):
        """
        Check if OpenWebRX is accessible via HTTP.

        Returns:
            bool: True if web interface responds
        """
        if not REQUESTS_AVAILABLE:
            return False

        now = time.time()

        # Use cache to avoid hammering the API
        if (now - self._status_cache_time <
                self._status_cache_ttl):
            return self._status_cache.get(
                'available', False
            )

        try:
            response = requests.get(
                self.base_url,
                timeout=3,
                allow_redirects=True
            )
            available = response.status_code in (
                200, 301, 302, 401
            )
            self._status_cache['available'] = available
            self._status_cache_time = now
            return available
        except Exception:
            self._status_cache['available'] = False
            self._status_cache_time = now
            return False

    def get_server_status(self):
        """
        Get OpenWebRX server status from API.

        Returns:
            dict: Status data or empty dict
        """
        data = self._get(self.API_STATUS)
        if data:
            self._add_log(
                "[OpenWebRX] Status retrieved successfully"
            )
        return data or {}

    def get_version(self):
        """
        Get OpenWebRX version string.

        Returns:
            str: Version or 'unknown'
        """
        data = self._get(self.API_VERSION, timeout=5)
        if data:
            return data.get('version', 'unknown')

        # Try parsing from main page
        if REQUESTS_AVAILABLE:
            try:
                resp = requests.get(
                    self.base_url, timeout=5
                )
                if 'openwebrx' in resp.text.lower():
                    import re
                    match = re.search(
                        r'v?(\d+\.\d+[\.\d]*)',
                        resp.text
                    )
                    if match:
                        return match.group(1)
            except Exception:
                pass
        return 'unknown'

    def get_receivers(self):
        """
        Get configured SDR receivers.

        Returns:
            dict: Receiver configuration or empty dict
        """
        return self._get(self.API_RECEIVERS) or {}

    def get_bands(self):
        """
        Get OpenWebRX band plan.

        Returns:
            list: Band data or empty list
        """
        data = self._get(self.API_BANDS)
        if isinstance(data, list):
            return data
        return []

    def get_full_status(self):
        """
        Get comprehensive status for display.

        Combines availability check, version, and
        server status into one dict for the plugin UI.

        Returns:
            dict: Complete status information
        """
        available = self.is_available()
        status = {
            'available': available,
            'url': self.base_url,
            'web_url': self._get_web_url(),
            'version': 'unknown',
            'users': 0,
            'receivers': [],
            'error': None,
            'last_check': datetime.utcnow().isoformat(),
            'polling': self._polling,
            'spots_count': len(self._spots),
        }

        if available:
            try:
                server_data = self.get_server_status()
                if server_data:
                    status['users'] = server_data.get(
                        'clients', 0
                    )

                version = self.get_version()
                if version != 'unknown':
                    status['version'] = version

                receivers = self.get_receivers()
                if receivers:
                    status['receivers'] = list(
                        receivers.keys()
                        if isinstance(receivers, dict)
                        else []
                    )
            except Exception as e:
                status['error'] = str(e)
        else:
            status['error'] = (
                f'[OpenWebRX][init] OpenWebRX not reachable at '
                f'{self.base_url}'
            )

        return status

    def _get_web_url(self):
        """
        Get the host-accessible URL for the web interface.

        Converts internal Docker network URL to
        localhost URL for browser access.

        Returns:
            str: Browser-accessible URL
        """
        port = self.config.get('http_port', 8073)

        # If URL uses internal Docker hostname, convert
        # to localhost for browser access
        url = self.base_url
        if 'openwebrx:' in url:
            return f'http://localhost:{port}'

        return url

    # ----------------------------------------------------------
    # Signal spot polling
    # ----------------------------------------------------------

    def start_polling(self):
        """
        Start background polling for signal spots.

        Polls the OpenWebRX API periodically to collect
        decoded digital mode signals for logbook logging.

        Returns:
            bool: True if started
        """
        if self._polling:
            return False

        self._polling = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name='openwebrx-poll'
        )
        self._poll_thread.start()
        self._add_log(
            "[OpenWebRX][init] Signal spot polling started"
        )
        return True

    def stop_polling(self):
        """Stop background polling."""
        self._polling = False
        self._add_log("Spot polling stopped")

    def _poll_loop(self):
        """
        Background polling loop.

        Queries OpenWebRX status periodically and
        collects any digital mode spots available
        through the API.
        """
        interval = self.config.get('poll_interval', 15)

        while self._polling:
            try:
                if self.is_available():
                    self._collect_spots()
            except Exception as e:
                self._add_log(
                    f"Poll error: {e}", 'error'
                )

            time.sleep(interval)

    def _collect_spots(self):
        """
        Collect decoded signal spots from OpenWebRX.

        OpenWebRX exposes decoded spots through its
        WebSocket and optionally via HTTP endpoints.
        This method uses the HTTP API polling approach.
        """
        # Query status for any spot data
        status = self.get_server_status()

        if not status:
            return

        # Extract any spot data from status
        # (OpenWebRX may expose spots differently
        # depending on version)
        spots = status.get('spots', [])
        clients = status.get('clients', [])

        if isinstance(clients, list):
            for client in clients:
                if isinstance(client, dict):
                    spot = self._extract_spot(client)
                    if spot:
                        with self._spots_lock:
                            self._spots.appendleft(spot)

    def _extract_spot(self, client_data):
        """
        Extract a spot from OpenWebRX client data.

        Args:
            client_data: Client/session data dict

        Returns:
            dict: Spot data or None
        """
        try:
            freq = client_data.get('frequency')
            mode = client_data.get('modulation', '')

            if not freq:
                return None

            return {
                'timestamp': (
                    datetime.utcnow().isoformat()
                ),
                'frequency': freq,
                'frequency_mhz': (
                    freq / 1_000_000
                    if freq > 1000
                    else freq
                ),
                'mode': mode,
                'callsign': client_data.get(
                    'callsign', ''
                ),
                'snr': client_data.get('snr'),
                'grid': client_data.get('grid', ''),
                'source': 'openwebrx_api',
            }
        except Exception as e:
            print(
                f"[OpenWebRX][init] spot extract error: {e}"
            )
            return None

    def get_spots(self, limit=100, mode_filter=None):
        """
        Get collected signal spots.

        Args:
            limit: Maximum spots to return
            mode_filter: Filter by mode string

        Returns:
            list: Spot data dicts
        """
        with self._spots_lock:
            spots = list(self._spots)

        if mode_filter:
            spots = [
                s for s in spots
                if s.get('mode', '').upper() ==
                mode_filter.upper()
            ]

        return spots[:limit]

    def add_manual_spot(self, spot_data):
        """
        Add a manually entered spot to the buffer.

        Args:
            spot_data: Spot dictionary
        """
        spot_data['timestamp'] = (
            datetime.utcnow().isoformat()
        )
        spot_data['source'] = 'manual'
        with self._spots_lock:
            self._spots.appendleft(spot_data)

    def clear_spots(self):
        """Clear all collected spots."""
        with self._spots_lock:
            self._spots.clear()
        self._add_log("Spots cleared")
