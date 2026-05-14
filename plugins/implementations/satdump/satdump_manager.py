"""
SatDump Process Manager
========================
Manages SatDump process lifecycle, configuration,
and coordinates between pipeline and data monitoring.

SatDump can run in two modes:
    1. GUI mode (satdump-ui): Full graphical interface
    2. CLI mode (satdump): Command-line pipeline execution

This manager handles both modes and provides:
    - Process start/stop/monitor
    - Pipeline execution management
    - Configuration file management
    - Product monitoring coordination
    - Status tracking

SatDump Configuration:
    ~/.config/satdump/settings.json  - Application settings
    ~/.config/satdump/pipelines/     - Custom pipelines

Reference:
    https://github.com/SatDump/SatDump
    https://docs.satdump.org/
"""

import os
import json
import shutil
import threading
import subprocess
import time
from datetime import datetime

from plugins.implementations.satdump.pipeline_manager import (
    PipelineManager
)
from plugins.implementations.satdump.data_monitor import (
    SatDumpDataMonitor
)


class SatDumpManager:
    """
    Manages SatDump operations and lifecycle.

    Coordinates processes, pipelines, data monitoring,
    and provides a unified interface for the plugin.
    """

    def __init__(self, config_dir, binary_path=None):
        """
        Initialize SatDump manager.

        Args:
            config_dir: Plugin data directory
            binary_path: Path to satdump binary
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('satdump') or
            '/usr/local/bin/satdump'
        )
        self.ui_binary_path = (
            shutil.which('satdump-ui') or
            '/usr/local/bin/satdump-ui'
        )

        # Default output directory
        self.output_dir = os.path.join(config_dir, 'output')
        os.makedirs(self.output_dir, exist_ok=True)

        # Gallery directory
        self.gallery_dir = os.path.join(config_dir, 'gallery')
        os.makedirs(self.gallery_dir, exist_ok=True)

        # Process management
        self._ui_process = None
        self._pipeline_processes = {}  # name -> subprocess
        self._process_lock = threading.Lock()

        # Managers
        self.pipeline_manager = PipelineManager(
            satdump_binary=self.binary_path
        )
        self._data_monitor = None

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 1000

        # Status
        self._status = {
            'ui_running': False,
            'monitoring': False,
            'active_pipelines': [],
            'product_count': 0,
            'version': None,
            'pid': None,
            'error': None,
            'last_check': None
        }

        # Load configuration
        self.config = self._load_config()
        os.makedirs(config_dir, exist_ok=True)

    def _load_config(self):
        """
        Load plugin configuration.

        Returns:
            dict: Configuration with defaults
        """
        config_file = os.path.join(
            self.config_dir, 'satdump_config.json'
        )

        defaults = {
            # SDR settings
            'sdr_source': 'rtlsdr',
            'sdr_device_id': '0',
            'sdr_gain': 30,
            'sdr_ppm': 0,
            'spyserver_host': 'localhost',
            'spyserver_port': 5555,

            # Output settings
            'output_dir': self.output_dir,

            # Display
            'display': ':0',

            # Station info
            'callsign': '',
            'locator': '',

            # Plugin behavior
            'auto_listen': True,
            'log_products': True,
            'auto_start': False,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
                    # Update output dir from config
                    self.output_dir = defaults.get(
                        'output_dir', self.output_dir
                    )
            except Exception as e:
                print(f"[SatDump] Config load error: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration.

        Args:
            config_data: Configuration dictionary

        Returns:
            bool: True if saved
        """
        config_file = os.path.join(
            self.config_dir, 'satdump_config.json'
        )

        try:
            self.config.update(config_data)

            # Update output directory
            if 'output_dir' in config_data:
                self.output_dir = config_data['output_dir']
                os.makedirs(self.output_dir, exist_ok=True)

            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            print("[SatDump] ✓ Config saved")
            return True
        except Exception as e:
            print(f"[SatDump] Config save error: {e}")
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

    def start_monitoring(self):
        """
        Start data product monitoring.

        Initializes the data monitor to watch for new
        satellite images and products from SatDump.

        Returns:
            tuple: (success, message)
        """
        if self._data_monitor and self._data_monitor._running:
            return False, "Monitoring already active"

        try:
            output_dir = self.config.get(
                'output_dir', self.output_dir
            )
            os.makedirs(output_dir, exist_ok=True)

            self._data_monitor = SatDumpDataMonitor(
                output_dir=output_dir,
                gallery_dir=self.gallery_dir
            )

            if self._data_monitor.start():
                self._status['monitoring'] = True
                count = self._data_monitor.get_product_count()
                self._add_log(
                    f"Data monitoring started. "
                    f"{count} existing products found."
                )
                return True, "Data monitoring started"
            else:
                return False, "Failed to start monitoring"

        except Exception as e:
            error = str(e)
            self._add_log(f"Monitor error: {error}", 'error')
            return False, error

    def stop_monitoring(self):
        """
        Stop data monitoring.

        Returns:
            tuple: (success, message)
        """
        if not self._data_monitor:
            return False, "Not monitoring"

        try:
            self._data_monitor.stop()
            self._data_monitor = None
            self._status['monitoring'] = False
            self._add_log("Data monitoring stopped")
            return True, "Monitoring stopped"
        except Exception as e:
            return False, str(e)

    def launch_ui(self):
        """
        Launch SatDump graphical interface.

        Starts satdump-ui for visual satellite reception
        and processing. Requires X display.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if self._ui_process and \
                    self._ui_process.poll() is None:
                return False, "SatDump UI already running"

            ui_binary = self.ui_binary_path or \
                shutil.which('satdump-ui') or \
                self.binary_path

            if not ui_binary:
                return False, (
                    "SatDump binary not found. "
                    "Please install SatDump."
                )

            try:
                env = os.environ.copy()
                env['DISPLAY'] = self.config.get(
                    'display', ':0'
                )

                self._add_log("Launching SatDump UI...")

                self._ui_process = subprocess.Popen(
                    [ui_binary],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env
                )

                self._status['ui_running'] = True
                self._status['pid'] = self._ui_process.pid
                self._add_log(
                    f"✓ SatDump UI launched "
                    f"(PID: {self._ui_process.pid})"
                )

                self._start_ui_monitor()

                return True, (
                    f"SatDump UI launched "
                    f"(PID: {self._ui_process.pid})"
                )

            except Exception as e:
                error = str(e)
                self._status['error'] = error
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Launch failed: {error}"

    def stop_ui(self):
        """
        Stop SatDump UI process.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if not self._ui_process:
                return False, "SatDump UI not running"

            try:
                if self._ui_process.poll() is None:
                    self._ui_process.terminate()
                    try:
                        self._ui_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._ui_process.kill()
                        self._ui_process.wait()

                self._ui_process = None
                self._status['ui_running'] = False
                self._status['pid'] = None
                self._add_log("✓ SatDump UI stopped")
                return True, "SatDump stopped"

            except Exception as e:
                return False, f"Stop error: {str(e)}"

    def start_pipeline(self, pipeline_name,
                       frequency_override=None,
                       sdr_override=None,
                       output_subdir=None,
                       extra_args_str=None):
        """
        Start a SatDump processing pipeline.

        Launches satdump CLI with the specified pipeline
        for live reception from an SDR device.

        Args:
            pipeline_name: Name of pipeline to run
            frequency_override: Frequency in MHz (optional)
            sdr_override: SDR source override
            output_subdir: Optional output subdirectory
            extra_args_str: Additional CLI arguments string

        Returns:
            tuple: (success, message)
        """
        # Check if pipeline already running
        if pipeline_name in self._pipeline_processes:
            proc = self._pipeline_processes[pipeline_name]
            if proc.poll() is None:
                return False, f"Pipeline {pipeline_name} already running"

        # Build output directory
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        out_dir_name = output_subdir or f"{timestamp}_{pipeline_name}"
        output_dir = os.path.join(
            self.config.get('output_dir', self.output_dir),
            out_dir_name
        )
        os.makedirs(output_dir, exist_ok=True)

        # Convert frequency
        freq_hz = None
        if frequency_override:
            freq_hz = frequency_override * 1e6

        # Parse extra args
        extra_args = []
        if extra_args_str:
            extra_args = extra_args_str.split()

        # Build command
        cmd = self.pipeline_manager.build_command(
            pipeline_name=pipeline_name,
            output_dir=output_dir,
            source_override=sdr_override or None,
            frequency_override=freq_hz,
            extra_args=extra_args if extra_args else None
        )

        if not cmd:
            return False, "Failed to build pipeline command"

        try:
            self._add_log(
                f"Starting pipeline: {pipeline_name}"
            )
            self._add_log(f"Command: {' '.join(cmd)}")
            self._add_log(f"Output: {output_dir}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            self._pipeline_processes[pipeline_name] = proc
            self._status['active_pipelines'].append(
                pipeline_name
            )

            # Monitor pipeline output
            self._monitor_pipeline(pipeline_name, proc)

            return True, (
                f"Pipeline '{pipeline_name}' started "
                f"(PID: {proc.pid})"
            )

        except Exception as e:
            error = str(e)
            self._add_log(
                f"Pipeline start error: {error}", 'error'
            )
            return False, error

    def stop_pipeline(self, pipeline_name):
        """
        Stop a running pipeline.

        Args:
            pipeline_name: Name of pipeline to stop

        Returns:
            tuple: (success, message)
        """
        proc = self._pipeline_processes.get(pipeline_name)
        if not proc:
            return False, f"Pipeline {pipeline_name} not running"

        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

            del self._pipeline_processes[pipeline_name]

            if pipeline_name in self._status['active_pipelines']:
                self._status['active_pipelines'].remove(
                    pipeline_name
                )

            self._add_log(f"Pipeline stopped: {pipeline_name}")
            return True, f"Pipeline {pipeline_name} stopped"

        except Exception as e:
            return False, f"Stop error: {str(e)}"

    def stop_all_pipelines(self):
        """Stop all running pipelines."""
        names = list(self._pipeline_processes.keys())
        for name in names:
            self.stop_pipeline(name)

    def _monitor_pipeline(self, name, proc):
        """
        Monitor pipeline process output.

        Reads stdout from pipeline process and adds to
        log buffer. Handles pass recording tracking.

        Args:
            name: Pipeline name
            proc: Subprocess instance
        """
        def monitor():
            if not proc.stdout:
                return

            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        self._add_log(f"[{name}] {line}")

            except Exception:
                pass

            # Pipeline ended
            if name in self._pipeline_processes:
                del self._pipeline_processes[name]

            if name in self._status['active_pipelines']:
                self._status['active_pipelines'].remove(name)

            self._add_log(
                f"Pipeline completed: {name}", 'info'
            )

            # Complete pass in monitor
            if self._data_monitor:
                self._data_monitor.complete_pass()

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name=f'satdump-pipeline-{name}'
        )
        thread.start()

    def _start_ui_monitor(self):
        """Monitor SatDump UI process output."""
        def monitor():
            if not self._ui_process or \
                    not self._ui_process.stdout:
                return

            try:
                for line in iter(
                    self._ui_process.stdout.readline, ''
                ):
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        self._add_log(line)
            except Exception:
                pass

            self._status['ui_running'] = False
            self._status['pid'] = None
            self._add_log("SatDump UI exited", 'warning')

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='satdump-ui-monitor'
        )
        thread.start()

    def get_status(self):
        """
        Get comprehensive status.

        Returns:
            dict: Current status
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check UI process
        if self._ui_process:
            if self._ui_process.poll() is not None:
                self._status['ui_running'] = False
                self._status['pid'] = None

        # Check pipeline processes
        active = [
            name for name, proc in
            self._pipeline_processes.items()
            if proc.poll() is None
        ]
        self._status['active_pipelines'] = active

        # Update product count
        if self._data_monitor:
            self._status['product_count'] = (
                self._data_monitor.get_product_count()
            )
            self._status['monitoring'] = (
                self._data_monitor._running
            )

        return dict(self._status)

    def get_products(self, limit=50, offset=0,
                     satellite_filter=None):
        """Get satellite products."""
        if not self._data_monitor:
            return []
        return self._data_monitor.get_products(
            limit, offset, satellite_filter
        )

    def get_product_count(self, satellite_filter=None):
        """Get total product count."""
        if not self._data_monitor:
            return 0
        return self._data_monitor.get_product_count(
            satellite_filter
        )

    def get_passes(self, limit=20):
        """Get satellite pass history."""
        if not self._data_monitor:
            return []
        return self._data_monitor.get_passes(limit)

    def delete_product(self, product_id):
        """Delete a product."""
        if not self._data_monitor:
            return False
        return self._data_monitor.delete_product(product_id)

    def get_active_pipelines(self):
        """
        Get currently running pipelines with details.

        Returns:
            list: Active pipeline information
        """
        active = []
        for name, proc in self._pipeline_processes.items():
            if proc.poll() is None:
                pipeline_info = (
                    self.pipeline_manager.get_pipeline(name)
                )
                active.append({
                    'name': name,
                    'pid': proc.pid,
                    'satellite': (
                        pipeline_info.get('satellite', '')
                        if pipeline_info else ''
                    ),
                    'frequency': (
                        pipeline_info.get('frequency', 0)
                        if pipeline_info else 0
                    ),
                })
        return active