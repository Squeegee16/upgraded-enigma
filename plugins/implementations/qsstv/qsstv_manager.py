"""
QSSTV Manager
==============
Manages the QSSTV process lifecycle and operations.

QSSTV is a GUI application that:
    - Decodes SSTV audio from sound card
    - Encodes and transmits SSTV images
    - Saves received images to disk
    - Supports multiple SSTV modes

Process Management:
    QSSTV is launched with DISPLAY set for GUI access.
    Communication happens via:
    - File monitoring (received images)
    - Process signals for TX control
    - Configuration file manipulation

Configuration:
    QSSTV stores config in:
    ~/.config/qsstv/qsstv.ini
    ~/.config/qsstv/rx/  (received images)
    ~/.config/qsstv/tx/  (transmit image queue)

Reference:
    https://github.com/ON4QZ/QSSTV
    https://users.telenet.be/on4qz/qsstv/
"""

import os
import json
import shutil
import configparser
import subprocess
import threading
import time
from datetime import datetime

from plugins.implementations.qsstv.image_monitor import QSStvImageMonitor


class QSStvManager:
    """
    Manages QSSTV process and image operations.

    Coordinates process lifecycle, configuration management,
    image monitoring, and provides a unified interface for
    the Flask plugin.
    """

    # Standard SSTV modes organized by family
    SSTV_MODES = {
        'Martin': [
            'Martin M1', 'Martin M2', 'Martin M3', 'Martin M4'
        ],
        'Scottie': [
            'Scottie S1', 'Scottie S2', 'Scottie S3',
            'Scottie DX'
        ],
        'Robot': [
            'Robot 8 BW', 'Robot 12 Color',
            'Robot 24 Color', 'Robot 36 Color',
            'Robot 72 Color'
        ],
        'Wraase': [
            'Wraase SC-2 120', 'Wraase SC-2 180'
        ],
        'PD': [
            'PD-50', 'PD-90', 'PD-120', 'PD-160',
            'PD-180', 'PD-240', 'PD-290'
        ],
        'Pasokon': ['P3', 'P5', 'P7'],
        'FAX': ['FAX480'],
    }

    def __init__(self, config_dir, binary_path=None):
        """
        Initialize QSSTV manager.

        Args:
            config_dir: Plugin data directory
            binary_path: Path to QSSTV binary
        """
        self.config_dir = config_dir
        self.binary_path = (
            binary_path or
            shutil.which('qsstv') or
            '/usr/bin/qsstv'
        )

        # QSSTV configuration paths
        self.qsstv_config_dir = os.path.expanduser(
            '~/.config/qsstv'
        )
        self.qsstv_rx_dir = os.path.join(
            self.qsstv_config_dir, 'rx'
        )
        self.qsstv_tx_dir = os.path.join(
            self.qsstv_config_dir, 'tx'
        )

        # Plugin gallery directory
        self.gallery_dir = os.path.join(config_dir, 'gallery')

        # Ensure directories exist
        for d in [config_dir, self.gallery_dir,
                  self.qsstv_rx_dir, self.qsstv_tx_dir]:
            os.makedirs(d, exist_ok=True)

        # Process management
        self._process = None
        self._process_lock = threading.Lock()

        # Image monitor
        self._image_monitor = None

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # New image callbacks
        self._image_callbacks = []

        # Status
        self._status = {
            'process_running': False,
            'pid': None,
            'receiving': False,
            'transmitting': False,
            'current_mode': None,
            'image_count': 0,
            'last_image': None,
            'version': None,
            'error': None,
            'last_check': None
        }

        # Load configuration
        self.config = self._load_config()

    def _load_config(self):
        """
        Load QSSTV plugin configuration.

        Returns:
            dict: Configuration with defaults applied
        """
        config_file = os.path.join(
            self.config_dir, 'qsstv_plugin_config.json'
        )

        defaults = {
            # Display settings
            'display': ':0',

            # SSTV defaults
            'default_mode': 'Martin M1',
            'default_frequency': 14230000,  # 14.230 MHz (20m SSTV)

            # Station info
            'callsign': '',
            'locator': '',

            # TX settings
            'tx_image_dir': self.qsstv_tx_dir,

            # Gallery settings
            'gallery_enabled': True,
            'max_gallery_images': 100,

            # Plugin behavior
            'auto_start': False,
            'auto_monitor': True,
            'log_received_images': True,

            # SSTV frequency presets
            'freq_presets': {
                '14.230 MHz (20m)': 14230000,
                '7.171 MHz (40m)': 7171000,
                '21.340 MHz (15m)': 21340000,
                '28.680 MHz (10m)': 28680000,
                '144.500 MHz (2m)': 144500000,
            }
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[QSSTV] Config load error: {e}")

        return defaults

    def save_config(self, config_data):
        """
        Save plugin configuration to file.

        Args:
            config_data: Configuration dictionary

        Returns:
            bool: True if saved successfully
        """
        config_file = os.path.join(
            self.config_dir, 'qsstv_plugin_config.json'
        )

        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print("[QSSTV] ✓ Config saved")
            return True
        except Exception as e:
            print(f"[QSSTV] Config save error: {e}")
            return False

    def _add_log(self, message, level='info'):
        """
        Add entry to log buffer.

        Args:
            message: Log message text
            level: Severity level (info, warning, error)
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
            list: Log entries, newest first
        """
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    def register_image_callback(self, callback):
        """
        Register callback for new received images.

        Args:
            callback: Function(image_data) to call
        """
        self._image_callbacks.append(callback)

        # Also register with monitor if running
        if self._image_monitor:
            self._image_monitor.register_new_image_callback(
                callback
            )

    def start_monitoring(self):
        """
        Start image monitoring system.

        Initializes and starts the image monitor to
        watch for new SSTV images from QSSTV.

        Returns:
            tuple: (success, message)
        """
        if self._image_monitor and \
                self._image_monitor._running:
            return False, "Monitor already running"

        try:
            self._image_monitor = QSStvImageMonitor(
                rx_dir=self.qsstv_rx_dir,
                gallery_dir=self.gallery_dir
            )

            # Register all pending callbacks
            for callback in self._image_callbacks:
                self._image_monitor.register_new_image_callback(
                    callback
                )

            # Register internal log callback
            self._image_monitor.register_new_image_callback(
                self._on_new_image
            )

            if self._image_monitor.start():
                image_count = self._image_monitor.get_image_count()
                self._status['image_count'] = image_count
                self._add_log(
                    f"Image monitoring started. "
                    f"{image_count} existing images."
                )
                return True, "Image monitoring started"
            else:
                return False, "Failed to start monitoring"

        except Exception as e:
            error = str(e)
            self._add_log(f"Monitor start error: {error}", 'error')
            return False, error

    def stop_monitoring(self):
        """
        Stop image monitoring.

        Returns:
            tuple: (success, message)
        """
        if not self._image_monitor:
            return False, "Monitor not running"

        try:
            self._image_monitor.stop()
            self._image_monitor = None
            self._add_log("Image monitoring stopped")
            return True, "Monitoring stopped"
        except Exception as e:
            return False, str(e)

    def _on_new_image(self, image_data):
        """
        Internal callback for new SSTV images.

        Updates status and logs reception event.

        Args:
            image_data: Image metadata dictionary
        """
        self._status['last_image'] = image_data.get('timestamp')
        self._status['image_count'] = (
            self._image_monitor.get_image_count()
            if self._image_monitor else 0
        )
        self._add_log(
            f"New SSTV image received: "
            f"{image_data.get('filename', 'unknown')} "
            f"[{image_data.get('mode', '?')}]"
        )

    def start_qsstv(self):
        """
        Launch QSSTV process.

        Starts QSSTV with the configured X display.
        QSSTV is a Qt5 GUI application that requires
        a display connection.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            # Check if already running
            if self._process and self._process.poll() is None:
                return False, "QSSTV is already running"

            # Check if binary available
            if not shutil.which('qsstv'):
                return False, (
                    "QSSTV binary not found. "
                    "Please install QSSTV: "
                    "https://github.com/ON4QZ/QSSTV"
                )

            try:
                # Set up environment
                env = os.environ.copy()
                display = self.config.get('display', ':0')
                env['DISPLAY'] = display

                self._add_log(
                    f"Launching QSSTV on display {display}..."
                )

                # Launch QSSTV
                self._process = subprocess.Popen(
                    ['qsstv'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env
                )

                self._status['process_running'] = True
                self._status['pid'] = self._process.pid
                self._status['error'] = None

                self._add_log(
                    f"✓ QSSTV launched (PID: {self._process.pid})"
                )

                # Start process monitor
                self._start_process_monitor()

                return True, (
                    f"QSSTV launched (PID: {self._process.pid})"
                )

            except Exception as e:
                error = str(e)
                self._status['error'] = error
                self._add_log(f"ERROR: {error}", 'error')
                return False, f"Failed to start: {error}"

    def stop_qsstv(self):
        """
        Stop QSSTV process gracefully.

        Returns:
            tuple: (success, message)
        """
        with self._process_lock:
            if not self._process:
                return False, "QSSTV not running"

            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait()

                self._process = None
                self._status['process_running'] = False
                self._status['pid'] = None
                self._add_log("✓ QSSTV stopped")
                return True, "QSSTV stopped"

            except Exception as e:
                return False, f"Stop error: {str(e)}"

    def _start_process_monitor(self):
        """
        Monitor QSSTV process output in background.

        Reads stdout from QSSTV and adds to log buffer.
        Detects process termination.
        """
        def monitor():
            if not self._process or not self._process.stdout:
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
            except Exception:
                pass

            self._status['process_running'] = False
            self._status['pid'] = None
            self._add_log("QSSTV process ended", 'warning')

        thread = threading.Thread(
            target=monitor,
            daemon=True,
            name='qsstv-process-monitor'
        )
        thread.start()

    def get_status(self):
        """
        Get comprehensive QSSTV status.

        Returns:
            dict: Current status information
        """
        self._status['last_check'] = datetime.utcnow().isoformat()

        # Check process
        if self._process:
            if self._process.poll() is not None:
                self._status['process_running'] = False
                self._status['pid'] = None

        # Update image count
        if self._image_monitor:
            self._status['image_count'] = (
                self._image_monitor.get_image_count()
            )

        return dict(self._status)

    def prepare_tx_image(self, image_path, mode=None):
        """
        Prepare an image for SSTV transmission.

        Copies and optionally resizes the image for the
        selected SSTV mode, placing it in QSSTV's TX directory.

        Args:
            image_path: Path to source image
            mode: SSTV mode (determines image dimensions)

        Returns:
            tuple: (success, message, dest_path)
        """
        if not os.path.exists(image_path):
            return False, "Image file not found", None

        try:
            # SSTV mode image dimensions
            mode_dimensions = {
                'Martin M1': (320, 256),
                'Martin M2': (320, 256),
                'Scottie S1': (320, 256),
                'Scottie S2': (320, 256),
                'Robot 36': (320, 240),
                'Robot 72': (320, 240),
                'PD-120': (640, 496),
                'PD-180': (640, 496),
                'PD-240': (640, 496),
                'PD-290': (800, 616),
            }

            # Prepare destination path
            filename = os.path.basename(image_path)
            dest_path = os.path.join(
                self.qsstv_tx_dir, filename
            )

            if PILLOW_AVAILABLE and mode:
                # Resize to appropriate dimensions
                target_size = mode_dimensions.get(mode, (320, 256))

                with PILImage.open(image_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Resize maintaining aspect ratio with crop
                    img = self._resize_and_crop(img, target_size)
                    img.save(dest_path, 'PNG')
            else:
                # Just copy the image
                shutil.copy2(image_path, dest_path)

            self._add_log(
                f"TX image prepared: {filename} ({mode or 'default'})"
            )
            return True, "Image prepared for TX", dest_path

        except Exception as e:
            error = str(e)
            self._add_log(f"TX prep error: {error}", 'error')
            return False, error, None

    @staticmethod
    def _resize_and_crop(image, target_size):
        """
        Resize and crop image to target dimensions.

        Maintains aspect ratio by resizing to fit, then
        centering and cropping to exact dimensions.

        Args:
            image: PIL Image object
            target_size: (width, height) tuple

        Returns:
            PIL Image: Resized and cropped image
        """
        from PIL import Image as PILImage

        target_w, target_h = target_size
        orig_w, orig_h = image.size

        # Calculate resize ratio to fit target
        ratio = max(target_w / orig_w, target_h / orig_h)
        new_w = int(orig_w * ratio)
        new_h = int(orig_h * ratio)

        # Resize
        resized = image.resize(
            (new_w, new_h),
            PILImage.Resampling.LANCZOS
        )

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        right = left + target_w
        bottom = top + target_h

        return resized.crop((left, top, right, bottom))

    def get_images(self, limit=50, offset=0):
        """
        Get gallery images.

        Args:
            limit: Maximum images to return
            offset: Pagination offset

        Returns:
            list: Image metadata dictionaries
        """
        if not self._image_monitor:
            return []
        return self._image_monitor.get_images(limit, offset)

    def get_image_count(self):
        """Get total gallery image count."""
        if not self._image_monitor:
            return 0
        return self._image_monitor.get_image_count()

    def update_image(self, image_id, callsign=None, notes=None):
        """
        Update image metadata.

        Args:
            image_id: Image identifier
            callsign: Optional callsign
            notes: Optional notes

        Returns:
            bool: True if updated
        """
        if not self._image_monitor:
            return False
        return self._image_monitor.update_image_metadata(
            image_id, callsign, notes
        )

    def delete_image(self, image_id):
        """
        Delete an image from gallery.

        Args:
            image_id: Image identifier

        Returns:
            bool: True if deleted
        """
        if not self._image_monitor:
            return False
        return self._image_monitor.delete_image(image_id)

    def get_flat_modes(self):
        """
        Get flat list of all SSTV mode names.

        Returns:
            list: All mode name strings
        """
        modes = []
        for family, family_modes in self.SSTV_MODES.items():
            modes.extend(family_modes)
        return modes

    def get_frequency_presets(self):
        """
        Get SSTV frequency presets.

        Returns:
            dict: Name -> frequency Hz mapping
        """
        return self.config.get('freq_presets', {})