"""
Winlink Manager
================
Manages the Pat Winlink client process and operations.

Pat is a cross-platform Winlink client that supports:
    - Multiple connection modes (Telnet, AX.25, VARA, ARDOP)
    - HTTP API for programmatic control
    - Message store and forward

Pat HTTP API:
    Pat exposes an HTTP API on localhost (default port 8080)
    This plugin uses the API for:
    - Status monitoring
    - Connection management
    - Message sending/receiving

Reference:
    https://github.com/la5nta/pat/wiki/HTTP-API
    https://getpat.io/
"""

import os
import json
import shutil
import threading
import subprocess
import time
from datetime import datetime

# Handle optional imports
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

from plugins.implementations.winlink.message_parser import (
    WinlinkMessageParser
)


class WinlinkManager:
    """
    Manages Pat Winlink client operations.

    Handles:
    - Pat process lifecycle (start/stop)
    - HTTP API communication
    - Message management via WinlinkMessageParser
    - Connection monitoring
    - Configuration management
    """

    # Pat HTTP API base URL (default port)
    PAT_API_PORT = 8080
    PAT_API_BASE = f'http://localhost:{PAT_API_PORT}'

    # Pat API endpoints
    API_STATUS = '/api/status'
    API_CONNECT = '/api/connect'
    API_DISCONNECT = '/api/disconnect'
    API_MAILBOX = '/api/mailbox'
    API_VERSION = '/api/version'

    def __init__(self, config_dir, binary_path=None):
        """
        Initialize Winlink manager.

        Args:
            config_dir: Plugin data directory
            binary_path: Path to Pat binary
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('pat') or
            os.path.expanduser('~/.local/bin/pat')
        )

        # Process management
        self._process = None
        self._process_lock = threading.Lock()
        self._monitor_thread = None

        # Log buffer (ring buffer)
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Status
        self._status = {
            'running': False,
            'connected': False,
            'callsign': None,
            'mode': None,
            'gateway': None,
            'pid': None,
            'api_available': False,
            'last_check': None,
            'error': None,
            'version': None
        }

        # Load configuration
        self.config = self._load_config()

        # Initialize message parser
        self.message_parser = None
        self._init_message_parser()

        # Create config directory
        os.makedirs(config_dir, exist_ok=True)

    def _init_message_parser(self):
        """
        Initialize the message parser with the Pat mailbox directory.

        Pat stores messages in ~/.local/share/pat/mailbox/<callsign>/
        """
        callsign = self.config.get('callsign', '')
        if callsign:
            mailbox_dir = os.path.expanduser(
                f'~/.local/share/pat/mailbox/{callsign.upper()}/'
            )
        else:
            # Use a default path until callsign is configured
            mailbox_dir = os.path.expanduser(
                '~/.local/share/pat/mailbox/DEFAULT/'
            )

        os.makedirs(mailbox_dir, exist_ok=True)
        self.message_parser = WinlinkMessageParser(mailbox_dir)

    def _load_config(self):
        """
        Load Winlink plugin configuration.

        Returns:
            dict: Configuration with defaults
        """
        config_file = os.path.join(
            self.config_dir, 'winlink_config.json'
        )

        defaults = {
            # Identity
            'callsign': '',
            'password': '',
            'locator': '',  # Maidenhead grid

            # Connection settings
            'connection_mode': 'telnet',
            'telnet_host': 'server.winlink.org',
            'telnet_port': 8772,
            'ax25_port': 'wl2k',
            'vara_host': 'localhost',
            'vara_port': 8300,

            # Pat settings
            'pat_api_port': 8080,
            'pat_http_addr': '0.0.0.0:8080',
            'send_heartbeat': True,

            # Plugin settings
            'auto_start': False,
            'auto_connect': False,
            'log_messages': True,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[Winlink] Warning: Config load error: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration.

        Args:
            config_data: Configuration dictionary to save

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(
            self.config_dir, 'winlink_config.json'
        )

        try:
            self.config.update(config_data)

            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            # Reinitialize message parser if callsign changed
            self._init_message_parser()

            print("[Winlink] ✓ Configuration saved")
            return True

        except Exception as e:
            print(f"[Winlink] ERROR: Config save failed: {e}")
            return False

    def generate_pat_config(self):
        """
        Generate Pat client configuration file.

        Creates ~/.config/pat/config.json with plugin settings.
        Pat reads this file on startup.

        Returns:
            bool: True if generated successfully
        """
        pat_config_dir = os.path.expanduser('~/.config/pat')
        os.makedirs(pat_config_dir, exist_ok=True)

        callsign = self.config.get('callsign', '').upper()
        if not callsign:
            print("[Winlink] WARNING: No callsign configured")
            return False

        pat_config = {
            "mycall": callsign,
            "secure_login_password": self.config.get('password', ''),
            "locator": self.config.get('locator', ''),
            "http_addr": self.config.get(
                'pat_http_addr', '0.0.0.0:8080'
            ),
            "send_heartbeat": self.config.get('send_heartbeat', True),
            "hamlib_rigs": {},
            "connect_aliases": {
                "telnet": (
                    f"telnet:///{self.config.get('telnet_host', 'server.winlink.org')}"
                    f":{self.config.get('telnet_port', 8772)}"
                ),
            },
            "ax25": {
                "port": self.config.get('ax25_port', 'wl2k'),
                "rig": ""
            },
            "vara": {
                "host": self.config.get('vara_host', 'localhost'),
                "port": self.config.get('vara_port', 8300)
            },
            "version": "0.14.0"
        }

        config_path = os.path.join(pat_config_dir, 'config.json')

        try:
            with open(config_path, 'w') as f:
                json.dump(pat_config, f, indent=2)
            print(f"[Winlink] ✓ Pat config generated: {config_path}")
            return True
        except Exception as e:
            print(f"[Winlink] ERROR: Config generation failed: {e}")
            return False

    def _add_log(self, message, level='info'):
        """
        Add entry to in-memory log buffer.

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

            # Maintain ring buffer size
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """
        Get recent log entries.

        Args:
            limit: Maximum entries to return

        Returns:
            list: Log entries, newest first
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def is_binary_available(self):
        """
        Check if Pat binary is available and executable.

        Returns:
            bool: True if Pat is available
        """
        if not self.binary_path:
            return False
        return (
            os.path.exists(self.binary_path) and
            os.access(self.binary_path, os.X_OK)
        )

    def start(self):
        """
        Start the Pat Winlink client HTTP server.

        Pat runs as an HTTP server providing API access
        and a web interface for management.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            # Check already running
            if self._process and self._process.poll() is None:
                return False, "Pat is already running"

            # Validate binary
            if not self.is_binary_available():
                return False, (
                    f"Pat binary not found at {self.binary_path}. "
                    "Please install Pat: https://getpat.io/"
                )

            # Validate callsign
            if not self.config.get('callsign'):
                return False, "Callsign is required. Please configure settings."

            try:
                # Generate Pat config file
                self.generate_pat_config()

                # Build Pat command to start HTTP server
                # Pat 'http' command starts the web interface and API
                cmd = [
                    self.binary_path,
                    'http',
                    '--addr', self.config.get(
                        'pat_http_addr', '0.0.0.0:8080'
                    )
                ]

                self._add_log(
                    f"Starting Pat for {self.config.get('callsign')}..."
                )
                self._add_log(f"Command: {' '.join(cmd)}")

                # Start process
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # Give Pat a moment to start
                time.sleep(2)

                # Check if process started
                if self._process.poll() is not None:
                    return False, "Pat failed to start"

                # Update status
                self._status['running'] = True
                self._status['pid'] = self._process.pid
                self._status['callsign'] = self.config.get('callsign')
                self._status['error'] = None

                # Get version
                self._status['version'] = self._get_pat_version()

                # Start log and status monitoring
                self._start_monitor()

                self._add_log(
                    f"✓ Pat started (PID: {self._process.pid})"
                )

                return True, f"Pat started (PID: {self._process.pid})"

            except Exception as e:
                error = str(e)
                self._status['error'] = error
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Failed to start Pat: {error}"

    def stop(self):
        """
        Stop the Pat client gracefully.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if not self._process or self._process.poll() is not None:
                # Try to find and kill orphan process
                self._kill_pat_process()
                self._status['running'] = False
                return False, "Pat is not running"

            try:
                self._add_log("Stopping Pat...")
                self._process.terminate()

                # Wait for graceful shutdown
                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._add_log("Force killing Pat...", 'warning')
                    self._process.kill()
                    self._process.wait()

                self._process = None
                self._status['running'] = False
                self._status['connected'] = False
                self._status['pid'] = None
                self._status['api_available'] = False

                self._add_log("✓ Pat stopped")
                return True, "Pat stopped successfully"

            except Exception as e:
                error = str(e)
                self._add_log(f"ERROR stopping: {error}", 'error')
                return False, f"Error stopping Pat: {error}"

    def _kill_pat_process(self):
        """
        Kill any running Pat processes by name.
        Used to clean up orphaned processes.
        """
        if not PSUTIL_AVAILABLE:
            return

        try:
            for proc in psutil.process_iter(['name', 'cmdline']):
                if proc.info['name'] == 'pat':
                    proc.terminate()
                    self._add_log(
                        f"Terminated orphan Pat process: {proc.pid}",
                        'warning'
                    )
        except Exception:
            pass

    def connect(self, mode=None, target=None):
        """
        Connect to a Winlink gateway.

        Uses Pat API to initiate a connection to a Winlink
        CMS or gateway for message exchange.

        Args:
            mode: Connection mode override (telnet, ax25, vara)
            target: Gateway callsign or address override

        Returns:
            tuple: (success, message)
        """
        if not self._status['running']:
            return False, "Pat is not running. Start Pat first."

        if not self._status.get('api_available'):
            return False, "Pat API not available yet"

        if not REQUESTS_AVAILABLE:
            return False, "requests package not available"

        try:
            # Use configured mode or override
            connect_mode = mode or self.config.get(
                'connection_mode', 'telnet'
            )

            self._add_log(
                f"Connecting via {connect_mode}..."
            )

            # Build connection URL for Pat API
            if connect_mode == 'telnet':
                host = self.config.get('telnet_host', 'server.winlink.org')
                port = self.config.get('telnet_port', 8772)
                connect_url = f"telnet:///{host}:{port}"
            elif connect_mode == 'ax25':
                ax25_port = self.config.get('ax25_port', 'wl2k')
                gateway = target or 'W2CXM'
                connect_url = f"ax25://{ax25_port}/{gateway}"
            else:
                connect_url = f"telnet:///server.winlink.org:8772"

            # Post to Pat connect API
            response = requests.post(
                f"{self.PAT_API_BASE}{self.API_CONNECT}",
                json={'url': connect_url},
                timeout=30
            )

            if response.status_code == 200:
                self._status['connected'] = True
                self._status['mode'] = connect_mode
                self._add_log(
                    f"✓ Connected via {connect_mode}"
                )
                return True, f"Connected via {connect_mode}"
            else:
                error = response.text
                self._add_log(f"Connection failed: {error}", 'warning')
                return False, f"Connection failed: {error}"

        except Exception as e:
            error = str(e)
            self._add_log(f"Connection error: {error}", 'error')
            return False, f"Connection error: {error}"

    def disconnect(self):
        """
        Disconnect from the current Winlink gateway.

        Returns:
            tuple: (success, message)
        """
        if not REQUESTS_AVAILABLE:
            return False, "requests not available"

        try:
            response = requests.post(
                f"{self.PAT_API_BASE}{self.API_DISCONNECT}",
                timeout=10
            )

            self._status['connected'] = False
            self._status['gateway'] = None
            self._add_log("Disconnected from gateway")
            return True, "Disconnected"

        except Exception as e:
            self._status['connected'] = False
            return False, f"Disconnect error: {str(e)}"

    def get_status(self):
        """
        Get current Winlink/Pat status.

        Queries Pat API for live status when running.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check if process is still alive
        if self._process:
            if self._process.poll() is not None:
                self._status['running'] = False
                self._status['connected'] = False
                self._status['api_available'] = False
                self._add_log(
                    "Pat process terminated unexpectedly", 'warning'
                )

        # Query API if running
        if self._status['running'] and REQUESTS_AVAILABLE:
            api_status = self._query_api(self.API_STATUS)
            if api_status:
                self._status['api_available'] = True
                # Extract status fields from Pat API response
                self._status['connected'] = api_status.get(
                    'connected', False
                )
                if api_status.get('active_connection'):
                    conn = api_status['active_connection']
                    self._status['gateway'] = conn.get('target_call')
                    self._status['mode'] = conn.get('transport')
            else:
                self._status['api_available'] = False

        return dict(self._status)

    def _query_api(self, endpoint):
        """
        Query the Pat HTTP API.

        Args:
            endpoint: API endpoint path

        Returns:
            dict: Response data or None on error
        """
        if not REQUESTS_AVAILABLE:
            return None

        try:
            response = requests.get(
                f"{self.PAT_API_BASE}{endpoint}",
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

    def _get_pat_version(self):
        """
        Get Pat version from API or binary.

        Returns:
            str: Version string or None
        """
        # Try API first (if running)
        api_version = self._query_api(self.API_VERSION)
        if api_version:
            return api_version.get('version', 'unknown')

        # Try binary directly
        try:
            result = subprocess.run(
                [self.binary_path, '--version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    def _start_monitor(self):
        """
        Start background monitoring thread.

        Monitors Pat process output and API availability.
        Reads stdout from Pat and stores in log buffer.
        """
        def monitor():
            """Background monitoring function."""
            # Monitor process stdout
            if self._process and self._process.stdout:
                try:
                    for line in iter(
                        self._process.stdout.readline, ''
                    ):
                        if not line:
                            break
                        line = line.strip()
                        if line:
                            self._add_log(line)
                            self._parse_status_from_log(line)
                except Exception as e:
                    self._add_log(
                        f"Monitor error: {e}", 'error'
                    )

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='winlink-monitor'
        )
        thread.start()
        self._monitor_thread = thread

    def _parse_status_from_log(self, line):
        """
        Parse status information from Pat log output.

        Args:
            line: Log line from Pat process
        """
        line_lower = line.lower()

        if 'listening on' in line_lower:
            self._status['api_available'] = True
            self._add_log("Pat API ready")

        elif 'connected to' in line_lower:
            self._status['connected'] = True
            # Try to extract gateway callsign
            import re
            match = re.search(r'connected to (\S+)', line_lower)
            if match:
                self._status['gateway'] = match.group(1).upper()

        elif 'disconnected' in line_lower:
            self._status['connected'] = False
            self._status['gateway'] = None

        elif 'error' in line_lower:
            self._status['error'] = line

    def get_inbox(self):
        """
        Get inbox messages.

        Returns:
            list: Inbox messages
        """
        if not self.message_parser:
            return []
        return self.message_parser.get_inbox()

    def get_outbox(self):
        """
        Get outbox messages.

        Returns:
            list: Queued outgoing messages
        """
        if not self.message_parser:
            return []
        return self.message_parser.get_outbox()

    def get_sent(self):
        """
        Get sent messages.

        Returns:
            list: Sent messages
        """
        if not self.message_parser:
            return []
        return self.message_parser.get_sent()

    def send_message(self, to_address, subject, body):
        """
        Queue a message for sending via Winlink.

        Creates a message file in the Pat outbox.
        Message is sent on next gateway connection.

        Args:
            to_address: Recipient callsign or email
            subject: Message subject
            body: Message body text

        Returns:
            tuple: (success, message or error)
        """
        if not self.message_parser:
            return False, "Message parser not initialized"

        callsign = self.config.get('callsign', '').upper()
        if not callsign:
            return False, "Callsign not configured"

        # Get outbox directory
        outbox_dir = os.path.expanduser(
            f'~/.local/share/pat/mailbox/{callsign}/out/'
        )

        success, result = self.message_parser.create_message_file(
            outbox_dir=outbox_dir,
            from_callsign=callsign,
            to_address=to_address,
            subject=subject,
            body=body
        )

        if success:
            self._add_log(
                f"Message queued for {to_address}: {subject}"
            )
            return True, f"Message queued: {os.path.basename(result)}"
        else:
            self._add_log(
                f"Failed to queue message: {result}", 'error'
            )
            return False, f"Failed to queue: {result}"

    def get_message_counts(self):
        """
        Get message counts for all folders.

        Returns:
            dict: Count per folder
        """
        if not self.message_parser:
            return {'in': 0, 'out': 0, 'sent': 0, 'archive': 0}
        return self.message_parser.get_message_count()