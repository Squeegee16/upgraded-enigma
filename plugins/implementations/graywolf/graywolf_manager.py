"""
GrayWolf Process Manager
=========================
Manages the GrayWolf process lifecycle including starting,
stopping, monitoring, and communication with the Winlink
network.

GrayWolf communicates via:
- Command line arguments for configuration
- Log files for status monitoring
- Winlink API for message access

Reference: https://github.com/chrissnell/graywolf
"""

import os
import shutil
import subprocess
import threading
import time
import json
import re
from datetime import datetime
from pathlib import Path


class GrayWolfManager:
    """
    Manages GrayWolf process and Winlink communications.

    Handles process lifecycle, configuration management,
    log monitoring, and provides an interface for the
    Flask plugin to interact with GrayWolf.
    """

    def __init__(self, config_dir, binary_path=None):
        """
        Initialize the GrayWolf manager.

        Args:
            config_dir: Directory for GrayWolf configuration files
            binary_path: Path to GrayWolf binary (auto-detected if None)
        """
        self.config_dir = config_dir
        self.binary_path = binary_path or shutil.which('graywolf') or \
            os.path.expanduser('~/.local/bin/graywolf')

        # Process management
        self._process = None
        self._process_lock = threading.Lock()
        self._monitor_thread = None
        self._running = False

        # Log storage (in-memory ring buffer)
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Status tracking
        self._status = {
            'running': False,
            'connected': False,
            'callsign': None,
            'gateway': None,
            'last_check': None,
            'error': None,
            'pid': None
        }

        # Configuration
        self.config = self._load_config()

        # Create config directory
        os.makedirs(config_dir, exist_ok=True)

    def _load_config(self):
        """
        Load GrayWolf configuration from file.

        Returns:
            dict: Configuration dictionary with defaults
        """
        config_file = os.path.join(self.config_dir, 'graywolf_config.json')
        defaults = {
            'callsign': '',
            'password': '',
            'gateway': '',
            'port': 8772,
            'mode': 'telnet',  # telnet, ax25, vara
            'grid': '',
            'auto_start': False,
            'log_level': 'info'
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[GrayWolf] Warning: Could not load config: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save GrayWolf configuration to file.

        Args:
            config_data: Dictionary of configuration values

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(self.config_dir, 'graywolf_config.json')

        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[GrayWolf] ERROR: Could not save config: {e}")
            return False

    def _add_log(self, message, level='info'):
        """
        Add a message to the in-memory log buffer.

        Args:
            message: Log message string
            level: Log level (info, warning, error)
        """
        with self._log_lock:
            self._logs.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message
            })

            # Trim log buffer to max size
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """
        Get recent log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            list: Recent log entries
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def get_status(self):
        """
        Get current GrayWolf status.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check if process is still running
        if self._process:
            if self._process.poll() is not None:
                # Process has terminated
                self._status['running'] = False
                self._status['connected'] = False
                self._status['pid'] = None
                self._add_log("GrayWolf process terminated unexpectedly", 'warning')
            else:
                self._status['running'] = True
                self._status['pid'] = self._process.pid
        else:
            self._status['running'] = False
            self._status['pid'] = None

        return dict(self._status)

    def is_binary_available(self):
        """
        Check if GrayWolf binary is available.

        Returns:
            bool: True if binary exists and is executable
        """
        if not self.binary_path:
            return False
        return os.path.exists(self.binary_path) and \
            os.access(self.binary_path, os.X_OK)

    def start(self, callsign=None, gateway=None, password=None):
        """
        Start the GrayWolf process.

        Args:
            callsign: Override callsign for this session
            gateway: Override gateway for this session
            password: Override password for this session

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            # Check if already running
            if self._process and self._process.poll() is None:
                return False, "GrayWolf is already running"

            # Check binary
            if not self.is_binary_available():
                return False, f"GrayWolf binary not found at {self.binary_path}"

            # Use provided values or fall back to config
            cs = callsign or self.config.get('callsign')
            gw = gateway or self.config.get('gateway')
            pw = password or self.config.get('password')

            # Validate required fields
            if not cs:
                return False, "Callsign is required to start GrayWolf"

            try:
                # Build command arguments
                cmd = self._build_command(cs, gw, pw)

                self._add_log(f"Starting GrayWolf for {cs}...")
                self._add_log(f"Command: {' '.join(cmd)}")

                # Start process
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
                self._status['callsign'] = cs
                self._status['gateway'] = gw
                self._status['pid'] = self._process.pid
                self._status['error'] = None

                # Start log monitoring thread
                self._start_log_monitor()

                self._add_log(
                    f"GrayWolf started with PID {self._process.pid}",
                    'info'
                )
                return True, f"GrayWolf started (PID: {self._process.pid})"

            except Exception as e:
                error_msg = f"Failed to start GrayWolf: {str(e)}"
                self._status['error'] = error_msg
                self._add_log(error_msg, 'error')
                return False, error_msg

    def _build_command(self, callsign, gateway, password):
        """
        Build the GrayWolf command line.

        Args:
            callsign: Ham radio callsign
            gateway: Winlink gateway address
            password: Winlink account password

        Returns:
            list: Command and arguments
        """
        cmd = [self.binary_path]

        # Add callsign
        if callsign:
            cmd.extend(['-callsign', callsign.upper()])

        # Add gateway
        if gateway:
            cmd.extend(['-gateway', gateway])

        # Add password
        if password:
            cmd.extend(['-password', password])

        # Add mode
        mode = self.config.get('mode', 'telnet')
        cmd.extend(['-mode', mode])

        # Add port
        port = self.config.get('port', 8772)
        cmd.extend(['-port', str(port)])

        # Add grid square if available
        grid = self.config.get('grid', '')
        if grid:
            cmd.extend(['-grid', grid])

        return cmd

    def stop(self):
        """
        Stop the GrayWolf process gracefully.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if not self._process or self._process.poll() is not None:
                return False, "GrayWolf is not running"

            try:
                # Try graceful shutdown first
                self._add_log("Stopping GrayWolf...")
                self._process.terminate()

                # Wait up to 10 seconds for graceful exit
                try:
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't stop
                    self._add_log("Force killing GrayWolf...", 'warning')
                    self._process.kill()
                    self._process.wait()

                # Update status
                self._status['running'] = False
                self._status['connected'] = False
                self._status['pid'] = None
                self._process = None

                self._add_log("GrayWolf stopped successfully")
                return True, "GrayWolf stopped"

            except Exception as e:
                error_msg = f"Error stopping GrayWolf: {str(e)}"
                self._add_log(error_msg, 'error')
                return False, error_msg

    def _start_log_monitor(self):
        """
        Start background thread to monitor GrayWolf output.
        Reads stdout/stderr from the process and stores in log buffer.
        """
        self._running = True

        def monitor():
            """Monitor thread function."""
            if not self._process:
                return

            try:
                for line in iter(self._process.stdout.readline, ''):
                    if not line:
                        break

                    line = line.strip()
                    if line:
                        self._add_log(line)

                        # Parse status from log output
                        self._parse_log_line(line)

            except Exception as e:
                self._add_log(f"Log monitor error: {e}", 'error')
            finally:
                self._running = False

        self._monitor_thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='graywolf-monitor'
        )
        self._monitor_thread.start()

    def _parse_log_line(self, line):
        """
        Parse GrayWolf log output to extract status information.

        Args:
            line: Log line from GrayWolf process
        """
        line_lower = line.lower()

        # Check for connection status
        if 'connected' in line_lower:
            self._status['connected'] = True
            self._add_log("Connected to Winlink network", 'info')

        elif 'disconnected' in line_lower or 'connection failed' in line_lower:
            self._status['connected'] = False

        elif 'error' in line_lower:
            self._status['error'] = line

    def get_messages(self):
        """
        Get messages from GrayWolf inbox.

        Returns:
            list: List of message dictionaries
        """
        # GrayWolf stores messages in the working directory
        messages = []
        inbox_dir = os.path.join(self.config_dir, 'inbox')

        if not os.path.exists(inbox_dir):
            os.makedirs(inbox_dir, exist_ok=True)
            return messages

        try:
            for filename in os.listdir(inbox_dir):
                if filename.endswith('.msg'):
                    filepath = os.path.join(inbox_dir, filename)
                    msg = self._parse_message_file(filepath)
                    if msg:
                        messages.append(msg)

            return sorted(messages,
                          key=lambda x: x.get('timestamp', ''),
                          reverse=True)

        except Exception as e:
            print(f"[GrayWolf] Error reading messages: {e}")
            return []

    def _parse_message_file(self, filepath):
        """
        Parse a Winlink message file.

        Args:
            filepath: Path to message file

        Returns:
            dict: Parsed message data
        """
        try:
            with open(filepath, 'r', errors='ignore') as f:
                content = f.read()

            # Basic message parsing
            msg = {
                'id': os.path.basename(filepath),
                'timestamp': datetime.fromtimestamp(
                    os.path.getmtime(filepath)
                ).isoformat(),
                'from': '',
                'to': '',
                'subject': '',
                'body': '',
                'raw': content
            }

            # Parse headers
            lines = content.split('\n')
            in_body = False
            body_lines = []

            for line in lines:
                if line.strip() == '':
                    in_body = True
                    continue

                if in_body:
                    body_lines.append(line)
                else:
                    # Parse header fields
                    if line.startswith('From:'):
                        msg['from'] = line[5:].strip()
                    elif line.startswith('To:'):
                        msg['to'] = line[3:].strip()
                    elif line.startswith('Subject:'):
                        msg['subject'] = line[8:].strip()

            msg['body'] = '\n'.join(body_lines)
            return msg

        except Exception as e:
            print(f"[GrayWolf] Error parsing message {filepath}: {e}")
            return None

    def send_message(self, to_address, subject, body):
        """
        Queue a message for sending via Winlink.

        Args:
            to_address: Recipient Winlink address
            subject: Message subject
            body: Message body

        Returns:
            tuple: (success, message)
        """
        outbox_dir = os.path.join(self.config_dir, 'outbox')
        os.makedirs(outbox_dir, exist_ok=True)

        try:
            # Create message file
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"msg_{timestamp}.msg"
            filepath = os.path.join(outbox_dir, filename)

            # Format message in Winlink format
            callsign = self.config.get('callsign', 'UNKNOWN')
            message_content = (
                f"From: {callsign}@winlink.org\n"
                f"To: {to_address}\n"
                f"Subject: {subject}\n"
                f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                f"\n"
                f"{body}\n"
            )

            with open(filepath, 'w') as f:
                f.write(message_content)

            self._add_log(f"Message queued for {to_address}: {subject}")
            return True, f"Message queued successfully: {filename}"

        except Exception as e:
            error_msg = f"Failed to queue message: {str(e)}"
            self._add_log(error_msg, 'error')
            return False, error_msg