"""
DMR Plugin Installer
=====================
Handles first-run installation of DMR plugin
dependencies.

DMR Decoding Backend Options:
    1. DSD (Digital Speech Decoder)
       Open source DMR/P25/D-STAR decoder
       https://github.com/szechyjs/dsd
       Requires: libsndfile, libsamplerate, portaudio

    2. QRadioLink (preferred for TX+RX)
       https://github.com/qradiolink/qradiolink
       Full-featured DMR transceiver

    3. imbe_vocoder / mbe_server
       Python vocoder for audio decoding

    4. RTL-SDR + GNU Radio (demodulation only)
       No vocoding without AMBE hardware

Python Dependencies:
    pyrtlsdr   - RTL-SDR device interface
    numpy      - Signal processing
    scipy      - DSP filters
    sounddevice- Audio I/O for PTT mic and speaker
    requests   - HTTP API calls

Docker Notes:
    System packages (dsd, qradiolink) must be in
    the Dockerfile. Runtime apt installs are blocked
    for non-root users.
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from datetime import datetime

try:
    from plugins.implementations.base_installer import (
        BaseInstaller
    )
except ImportError:
    class BaseInstaller:
        """Minimal inline fallback."""

        def __init__(self):
            try:
                self.is_root = (os.getuid() == 0)
            except AttributeError:
                self.is_root = False
            self.sudo_available = (
                shutil.which('sudo') is not None
            )
            self._sudo = (
                [] if (
                    self.is_root or
                    not self.sudo_available
                ) else ['sudo']
            )
            self.in_docker = (
                os.environ.get(
                    'PLUGIN_SKIP_PIP_INSTALL', ''
                ).lower() == 'true' or
                os.path.exists('/.dockerenv')
            )

        def pip_install(self, package):
            if self.in_docker:
                return True
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '--quiet', package],
                    check=True,
                    capture_output=True,
                    timeout=120
                )
                return True
            except Exception:
                return False

        def install_python_packages(self, packages):
            failed = []
            for pkg in packages:
                if not self.pip_install(pkg):
                    failed.append(pkg)
            return len(packages) - len(failed), failed

        def write_marker(self, path, extra_data=None):
            data = {
                'installed': True,
                'timestamp': datetime.utcnow().isoformat(),
                'in_docker': self.in_docker,
            }
            if extra_data and isinstance(
                extra_data, dict
            ):
                data.update(extra_data)
            try:
                os.makedirs(
                    os.path.dirname(path),
                    exist_ok=True
                )
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[DMR] Marker error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class DMRInstaller(BaseInstaller):
    """
    Manages DMR plugin dependency installation.

    Installs Python packages and checks for system
    decoders (DSD, QRadioLink). System decoders must
    be installed in the Dockerfile for Docker deployments.
    """

    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__), '.installed'
    )

    REQUIRED_PACKAGES = [
        'numpy',
        'scipy',
        'requests',
        'psutil',
    ]

    OPTIONAL_PACKAGES = [
        'sounddevice',
        'pyrtlsdr',
    ]

    # System decoders in order of preference
    DECODER_BINARIES = [
        'dsd',           # Digital Speech Decoder
        'qradiolink',    # QRadioLink full transceiver
        'rtl_fm',        # RTL-SDR FM demodulator (basic)
    ]

    def __init__(self):
        """Initialise DMR installer."""
        super().__init__()
        print(
            f"[DMR] Installer init | "
            f"Docker: {self.in_docker}"
        )

    def is_installed(self):
        """Check if plugin is installed."""
        return os.path.exists(self.INSTALL_MARKER)

    def find_decoder(self):
        """
        Find available DMR decoder on the system.

        Returns:
            tuple: (name, path) or (None, None)
        """
        for decoder in self.DECODER_BINARIES:
            path = shutil.which(decoder)
            if path:
                return decoder, path
        return None, None

    def get_decoder_info(self):
        """
        Get information about available decoders.

        Returns:
            dict: Decoder availability status
        """
        info = {}
        for decoder in self.DECODER_BINARIES:
            path = shutil.which(decoder)
            info[decoder] = {
                'available': path is not None,
                'path': path,
            }
        return info

    def get_install_info(self):
        """Read installation marker."""
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Install DMR plugin dependencies.

        Returns:
            bool: True always — plugin loads regardless
        """
        if self.is_installed():
            print("[DMR] ✓ Already installed")
            return True

        print("[DMR] ==========================================")
        print("[DMR] Installing DMR plugin dependencies")
        print("[DMR] ==========================================")

        # Python packages
        available, failed = self.install_python_packages(
            self.REQUIRED_PACKAGES
        )

        for pkg in self.OPTIONAL_PACKAGES:
            self.pip_install(pkg)

        if failed and self.in_docker:
            print(
                f"[DMR] Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        # Check for system decoders
        decoder_name, decoder_path = self.find_decoder()
        if decoder_name:
            print(
                f"[DMR] ✓ Decoder found: "
                f"{decoder_name} at {decoder_path}"
            )
        else:
            print(
                "[DMR] INFO: No system decoder found. "
                "Install dsd or qradiolink for full "
                "DMR decode capability."
            )
            if self.in_docker:
                print(
                    "[DMR] Add to Dockerfile: "
                    "apt-get install -y dsd"
                )

        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': 'pip',
                'platform': platform.platform(),
                'decoder': decoder_name,
                'decoder_path': decoder_path,
            }
        )

        print("[DMR] ✓ Installation complete")
        return True
