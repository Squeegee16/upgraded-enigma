"""
P25 Survey Plugin Installer
=============================
Handles first-run installation of P25 Survey plugin
dependencies.

P25 Decoding Backend:
    OP25: https://github.com/boatbod/op25
        The primary P25 decoder. GNU Radio-based.
        Supports Phase 1, Phase 2, trunking.

    DSD / DSD+: https://github.com/szechyjs/dsd
        Alternative decoder for Phase 1.
        Simpler to install, less feature-complete.

Python Dependencies:
    numpy      - Signal processing
    scipy      - DSP and filtering
    requests   - HTTP API calls
    psutil     - Process management
    pyrtlsdr   - RTL-SDR interface (optional)

System Dependencies (must be in Dockerfile):
    op25        - OP25 P25 decoder (GNU Radio based)
    dsd         - Digital Speech Decoder (alternative)
    rtl-sdr     - RTL-SDR tools

Docker Notes:
    System decoders must be added to the Dockerfile.
    Runtime apt installs are blocked for non-root users.
    All Python packages should be in requirements.txt.
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
                print(f"[P25][INSTALL] Marker write error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[P25][INSTALL] Marker read error: {e}")
                return {}

class P25SurveyInstaller(BaseInstaller):
    """
    Manages P25 Survey plugin dependency installation.

    Checks for OP25 and DSD decoders and installs
    required Python packages.
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
        'pyrtlsdr',
        'sounddevice',
    ]

    # P25 decoder binaries in order of preference
    DECODER_BINARIES = [
        'op25',          # OP25 (GNU Radio based)
        'rx.py',         # OP25 receive script
        'dsd',           # Digital Speech Decoder
        'rtl_fm',        # RTL-SDR (demod only)
    ]

    def __init__(self):
        """Initialise P25 installer."""
        super().__init__()
        print(
            f"[P25Survey] Installer init | "
            f"Docker: {self.in_docker}"
        )

    def is_installed(self):
        """Check if plugin dependencies are installed."""
        return os.path.exists(self.INSTALL_MARKER)

    def find_decoder(self):
        """
        Find available P25 decoder.

        Searches for OP25, DSD, or rtl_fm binaries.

        Returns:
            tuple: (name, path) or (None, None)
        """
        # Check for OP25 rx.py script
        op25_paths = [
            '/usr/local/src/op25/op25/gr-op25-repeater'
            '/apps/rx.py',
            '/opt/op25/op25/gr-op25-repeater/apps/rx.py',
            os.path.expanduser('~/op25/op25/'
                                'gr-op25-repeater/'
                                'apps/rx.py'),
        ]
        for path in op25_paths:
            if os.path.exists(path):
                return 'op25_rx', path

        # Check PATH for decoders
        for decoder in self.DECODER_BINARIES:
            path = shutil.which(decoder)
            if path:
                return decoder, path

        return None, None

    def get_decoder_info(self):
        """
        Get information about available P25 decoders.

        Returns:
            dict: Decoder availability status
        """
        info = {}

        # Check OP25
        op25_name, op25_path = self.find_decoder()
        info['op25'] = {
            'available': (
                op25_name is not None and
                'op25' in (op25_name or '')
            ),
            'path': op25_path or '',
            'description': 'GNU Radio based P25 decoder',
        }

        # Check DSD
        dsd = shutil.which('dsd')
        info['dsd'] = {
            'available': dsd is not None,
            'path': dsd or '',
            'description': 'Digital Speech Decoder',
        }

        # Check rtl_fm
        rtl = shutil.which('rtl_fm')
        info['rtl_fm'] = {
            'available': rtl is not None,
            'path': rtl or '',
            'description': 'RTL-SDR FM demodulator',
        }

        # Check GNU Radio
        gnuradio = shutil.which('gnuradio-companion')
        info['gnuradio'] = {
            'available': gnuradio is not None,
            'path': gnuradio or '',
            'description': 'GNU Radio (required for OP25)',
        }

        return info

    def get_install_info(self):
        """Read installation marker data."""
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Install P25 Survey plugin dependencies.

        Returns:
            bool: True always — plugin loads regardless
        """
        if self.is_installed():
            print("[P25][INSTALL] ✓ Already installed")
            return True

        print("[P25][INSTALL] ==========================================")
        print("[P25][INSTALL] Installing P25 Survey dependencies")
        print("[P25][INSTALL] ==========================================")

        # Python packages
        available, failed = self.install_python_packages(
            self.REQUIRED_PACKAGES
        )

        for pkg in self.OPTIONAL_PACKAGES:
            self.pip_install(pkg)

        if failed and self.in_docker:
            print(
                f"[P25][INSTALL] Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        # Check for decoders
        decoder_name, decoder_path = self.find_decoder()
        if decoder_name:
            print(
                f"[P25][INSTALL] ✓ Decoder: "
                f"{decoder_name} at {decoder_path}"
            )
        else:
            print(
                "[P25][INSTALL] INFO: No P25 decoder found."
            )
            print(
                "[P25][INSTALL] For full decode, install OP25:"
            )
            print(
                "[P25][INSTALL]   https://github.com/"
                "boatbod/op25"
            )
            if self.in_docker:
                print(
                    "[P25][INSTALL] Add to Dockerfile: "
                    "apt-get install -y gr-op25-repeater"
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

        print("[P25][INSTALL] ✓ Installation complete")
        return True
