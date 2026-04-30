"""
GrayWolf Process Manager
=========================
Manages the GrayWolf process lifecycle and operations.

GrayWolf is a Winlink gateway client that:
    - Runs as an HTTP server (default: 127.0.0.1:8080)
    - Stores all configuration in a SQLite database
    - Is configured via its web UI, not CLI flags
    - Communicates via its HTTP API

GrayWolf CLI flags (from graywolf --help):
    -config string          SQLite config database path
    -http string            HTTP listen address
    -modem string           Path to graywolf-modem binary
    -history-db string      Position history database path
    -tile-cache-dir string  PMTiles cache directory
    -shutdown-timeout       Clean shutdown wait time
    -logbuffer-ramdisk      Force log buffer to ramdisk
    -flac string            Override audio with FLAC file
    -debug                  Enable debug logging

NOTE: Callsign, mode, port, and gateway are NOT CLI flags.
      They are configured in the SQLite database via the
      GrayWolf web UI at http://localhost:8080.

Reference: https://github.com/chrissnell/graywolf
"""

import os
import json
import shutil
import threading
import subprocess
import time
from datetime import datetime


class GrayWolfManager:
    """
    Manages GrayWolf process and Winlink communications.

    GrayWolf runs as a local HTTP server. Configuration
    (callsign, password, gateway, mode) is stored in a
    SQLite database and managed through the web interface.

    This manager:
        - Starts/stops the GrayWolf process
        - Passes correct CLI flags (config path, http addr)
        - Monitors process output
        - Provides status to the plugin UI
        - Links to the GrayWolf web UI for configuration
    """

    # GrayWolf default HTTP port
    GRAYWOLF_HTTP_PORT = 8080

    # GrayWolf web UI URL
    GRAYWOLF_UI_URL = f'http://localhost:{GRAYWOLF_HTTP_PORT}'

    def __init__(self, config_dir, binary_path=None):
        """
        Initialize GrayWolf manager.

        Args:
            config_dir: Plugin data directory for storing
                        GrayWolf's SQLite config database
            binary_path: Path to GrayWolf binary
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('graywolf') or
            os.path.expanduser('~/.local/bin/graywolf')
        )

        # GrayWolf's SQLite config database path.
        # This is where GrayWolf stores all its settings
        # including callsign, password, and gateway config.
        self.graywolf_db_path = os.path.join(
            config_dir, 'graywolf.db'
        )

        # GrayWolf position history database
        self.graywolf_history_db_path = os.path.join(
            config_dir, 'graywolf-history.db'
        )

        # PMTiles cache directory
        self.graywolf_tiles_dir = os.path.join(
            config_dir, 'tiles'
        )

        # HTTP address GrayWolf listens on.
        # Bind to all interfaces so the plugin can reach it.
        self.http_addr = '0.0.0.0:8080'

        # Process management
        self._process = None
        self._process_lock = threading.Lock()
        self._monitor_thread = None

        # Log buffer (ring buffer)
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Status tracking
        self._status = {
            'running': False,
            'connected': False,
            'callsign': None,
            'gateway': None,
            'pid': None,
            'api_available': False,
            'last_check': None,
            'error': None,
            'ui_url': self.GRAYWOLF_UI_URL,
        }

        # Load plugin configuration
        self.config = self._load_config()

        # Ensure directories exist
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(self.graywolf_tiles_dir, exist_ok=True)

    def _load_config(self):
        """
        Load plugin configuration from JSON file.

        Note: This is the HAM RADIO APP plugin config,
        NOT the GrayWolf SQLite config. GrayWolf's own
        configuration lives in its SQLite database.

        Returns:
            dict: Plugin configuration with defaults
        """
        config_file = os.path.join(
            self.config_dir, 'graywolf_plugin_config.json'
        )

        defaults = {
            # Displayed in UI for reference only.
            # The actual callsign is set inside GrayWolf's
            # own web interface at http://localhost:8080
            'callsign': '',
            'locator': '',

            # GrayWolf process settings
            'http_addr': '0.0.0.0:8080',
            'http_port': 8080,
            'debug_mode': False,

            # Plugin behaviour
            'auto_start': False,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[GrayWolf] Config load error: {e}")

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
            self.config_dir, 'graywolf_plugin_config.json'
        )

        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            # Update HTTP address from config
            port = self.config.get('http_port', 8080)
            self.http_addr = f"0.0.0.0:{port}"

            print("[GrayWolf] ✓ Configuration saved")
            return True
        except Exception as e:
            print(f"[GrayWolf] Config save error: {e}")
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

    def is_binary_available(self):
        """
        Check if GrayWolf binary is present and executable.

        Returns:
            bool: True if binary can be executed
        """
        if not self.binary_path:
            return False
        return (
            os.path.isfile(self.binary_path) and
            os.access(self.binary_path, os.X_OK)
        )

    def _build_command(self):
        """
        Build the GrayWolf launch command.

        Includes -modem flag pointing to the installed
        graywolf-modem binary so GrayWolf can find it
        even if it is not in the same directory as
        the graywolf binary.

        Returns:
            list: Command and valid arguments
        """
        cmd = [self.binary_path]

        # SQLite config database
        cmd.extend(['-config', self.graywolf_db_path])

        # HTTP listen address
        http_addr = self.config.get(
            'http_addr', '0.0.0.0:8080'
        )
        cmd.extend(['-http', http_addr])

        # Explicit path to graywolf-modem binary.
        # GrayWolf searches PATH and the directory next
        # to graywolf, but being explicit avoids the
        # 'binary not found' error when both are in
        # ~/.local/bin.
        modem_binary = os.path.join(
            os.path.expanduser('~/.local/bin'),
            'graywolf-modem'
        )

        if os.path.isfile(modem_binary) and \
                os.access(modem_binary, os.X_OK):
            cmd.extend(['-modem', modem_binary])
            self._add_log(
                f"Using modem: {modem_binary}"
            )
        else:
            # Check PATH
            modem_in_path = shutil.which('graywolf-modem')
            if modem_in_path:
                cmd.extend(['-modem', modem_in_path])
                self._add_log(
                    f"Using modem from PATH: {modem_in_path}"
                )
            else:
                self._add_log(
                    "WARNING: graywolf-modem not found. "
                    "GrayWolf will fail to start.",
                    'warning'
                )

        # Position history database
        cmd.extend([
            '-history-db',
            self.graywolf_history_db_path
        ])

        # PMTiles cache directory
        cmd.extend([
            '-tile-cache-dir',
            self.graywolf_tiles_dir
        ])

        # Debug logging
        if self.config.get('debug_mode', False):
            cmd.append('-debug')

        return cmd
    def start(self, callsign=None, gateway=None,
              password=None):
        """
        Start the GrayWolf process.

        NOTE: The callsign, gateway, and password parameters
        are accepted for API compatibility but are NOT
        passed as command line flags. GrayWolf reads these
        from its SQLite config database. To configure
        GrayWolf, use its web interface at:
            http://localhost:8080

        Args:
            callsign: Ignored (configure via GrayWolf UI)
            gateway: Ignored (configure via GrayWolf UI)
            password: Ignored (configure via GrayWolf UI)

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            # Check already running
            if self._process and \
                    self._process.poll() is None:
                return False, "GrayWolf is already running"

            # Check binary
            if not self.is_binary_available():
                return False, (
                    f"GrayWolf binary not found at "
                    f"{self.binary_path}. "
                    "Please install GrayWolf."
                )

            try:
                # Build command with valid flags only
                cmd = self._build_command()

                self._add_log(
                    f"Starting GrayWolf..."
                )
                self._add_log(
                    f"Command: {' '.join(cmd)}"
                )
                self._add_log(
                    f"Config DB: {self.graywolf_db_path}"
                )
                self._add_log(
                    f"Web UI: "
                    f"http://localhost:"
                    f"{self.config.get('http_port', 8080)}"
                )

                # Launch GrayWolf process
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=self.config_dir
                )

                # Update status
                self._status['running'] = True
                self._status['pid'] = self._process.pid
                self._status['error'] = None
                self._status['callsign'] = (
                    self.config.get('callsign', 'See GrayWolf UI')
                )

                # Start log monitor thread
                self._start_log_monitor()

                self._add_log(
                    f"GrayWolf started (PID: "
                    f"{self._process.pid})"
                )
                self._add_log(
                    f"Configure at: "
                    f"http://localhost:"
                    f"{self.config.get('http_port', 8080)}"
                )

                return True, (
                    f"GrayWolf started "
                    f"(PID: {self._process.pid}). "
                    f"Configure via web UI at "
                    f"http://localhost:"
                    f"{self.config.get('http_port', 8080)}"
                )

            except FileNotFoundError:
                error = (
                    f"GrayWolf binary not executable: "
                    f"{self.binary_path}"
                )
                self._status['error'] = error
                self._add_log(error, 'error')
                return False, error

            except Exception as e:
                error = f"Failed to start GrayWolf: {str(e)}"
                self._status['error'] = error
                self._add_log(error, 'error')
                return False, error

    def stop(self):
        """
        Stop the GrayWolf process gracefully.

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            if not self._process or \
                    self._process.poll() is not None:
                self._status['running'] = False
                return False, "GrayWolf is not running"

            try:
                self._add_log("Stopping GrayWolf...")
                self._process.terminate()

                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._add_log(
                        "Force killing GrayWolf...",
                        'warning'
                    )
                    self._process.kill()
                    self._process.wait()

                self._process = None
                self._status['running'] = False
                self._status['connected'] = False
                self._status['pid'] = None
                self._status['api_available'] = False

                self._add_log("✓ GrayWolf stopped")
                return True, "GrayWolf stopped"

            except Exception as e:
                error = f"Error stopping GrayWolf: {str(e)}"
                self._add_log(error, 'error')
                return False, error

    def _start_log_monitor(self):
        """
        Start background thread to monitor process output.

        Reads stdout/stderr from GrayWolf and stores
        in the log buffer. Detects process termination.
        """
        def monitor():
            """Monitor thread function."""
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
                        self._parse_log_line(line)

            except Exception as e:
                self._add_log(
                    f"Log monitor error: {e}", 'error'
                )
            finally:
                # Process has ended
                if self._status['running']:
                    self._status['running'] = False
                    self._status['pid'] = None
                    self._status['api_available'] = False
                    self._add_log(
                        "GrayWolf process terminated "
                        "unexpectedly",
                        'warning'
                    )

        self._monitor_thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='graywolf-monitor'
        )
        self._monitor_thread.start()

    def _parse_log_line(self, line):
        """
        Parse GrayWolf log output for status information.

        Args:
            line: Log line from GrayWolf process
        """
        line_lower = line.lower()

        # Detect when HTTP server is ready
        if 'listening' in line_lower or \
                'starting' in line_lower or \
                ':8080' in line:
            self._status['api_available'] = True
            self._add_log(
                "GrayWolf web UI is ready at "
                f"http://localhost:"
                f"{self.config.get('http_port', 8080)}"
            )

        elif 'connected' in line_lower:
            self._status['connected'] = True

        elif 'disconnected' in line_lower or \
                'connection failed' in line_lower:
            self._status['connected'] = False

        elif 'error' in line_lower:
            self._status['error'] = line[:200]

    def get_status(self):
        """
        Get current GrayWolf status.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = (
            datetime.utcnow().isoformat()
        )

        # Check if process is still alive
        if self._process:
            if self._process.poll() is not None:
                self._status['running'] = False
                self._status['pid'] = None
                self._status['api_available'] = False
        else:
            self._status['running'] = False

        # Add web UI URL for the frontend
        port = self.config.get('http_port', 8080)
        self._status['ui_url'] = f"http://localhost:{port}"

        return dict(self._status)
        
    def get_messages(self):
        """
        Get messages from GrayWolf.

        GrayWolf manages its own messages internally via
        its SQLite database and web UI. This method returns
        an empty list as a compatibility stub so the plugin
        UI loads without error.

        Full message management is available through the
        GrayWolf web interface at http://localhost:8080.

        Returns:
            list: Empty list (messages managed by GrayWolf UI)
        """
        return []

    def get_inbox(self):
        """
        Get inbox messages.

        Stub method for API compatibility.
        Use the GrayWolf web UI for message management.

        Returns:
            list: Empty list
        """
        return []

    def get_outbox(self):
        """
        Get outbox messages.

        Stub method for API compatibility.
        Use the GrayWolf web UI for message management.

        Returns:
            list: Empty list
        """
        return []

    def get_sent(self):
        """
        Get sent messages.

        Stub method for API compatibility.
        Use the GrayWolf web UI for message management.

        Returns:
            list: Empty list
        """
        return []

    def get_message_counts(self):
        """
        Get message counts for all folders.

        Stub method for API compatibility.
        Use the GrayWolf web UI for message management.

        Returns:
            dict: Zero counts for all folders
        """
        return {
            'inbox': 0,
            'outbox': 0,
            'sent': 0,
        }

    def send_message(self, to_address, subject, body):
        """
        Send a Winlink message via GrayWolf.

        GrayWolf manages message sending through its own
        web UI and internal queue. This method logs the
        intent and directs the user to the GrayWolf UI.

        Args:
            to_address: Recipient callsign or email
            subject: Message subject line
            body: Message body text

        Returns:
            tuple: (success: bool, message: str)
        """
        self._add_log(
            f"Message compose requested for {to_address}. "
            f"Use GrayWolf web UI: "
            f"{self.get_web_ui_url()}"
        )
        return (
            False,
            f"Use the GrayWolf web UI to send messages: "
            f"{self.get_web_ui_url()}"
        )
    def get_web_ui_url(self):
        """
        Get the GrayWolf web interface URL.

        Returns:
            str: Full URL to GrayWolf web UI
        """
        port = self.config.get('http_port', 8080)
        return f"http://localhost:{port}"

    def log_contact(self, contact_data):
        """
        Log a contact to the central logbook.

        Args:
            contact_data: Dictionary with contact info

        Returns:
            bool: True if logged successfully
        """
        from models import db
        from models.logbook import ContactLog
        from flask_login import current_user

        try:
            contact = ContactLog(
                operator_id=current_user.id,
                contact_callsign=contact_data.get(
                    'callsign', ''
                ),
                mode=contact_data.get('mode', 'WINLINK'),
                band=contact_data.get('band'),
                frequency=contact_data.get('frequency'),
                grid=contact_data.get('grid'),
                signal_report_sent=contact_data.get(
                    'rst_sent'
                ),
                signal_report_rcvd=contact_data.get(
                    'rst_rcvd'
                ),
                notes=contact_data.get('notes', '')
            )

            db.session.add(contact)
            db.session.commit()
            return True

        except Exception as e:
            print(f"[GrayWolf] Log contact error: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return False
