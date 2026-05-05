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
                print(f"[FLdigi] Config load error: {e}")

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
            print(f"[FLdigi] Config save error: {e}")
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

    def get_logs(self, limit=100
