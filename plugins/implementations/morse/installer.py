"""
Morse Plugin Installer
=======================
Installs Python dependencies for the Morse Code plugin.

Dependencies:
    numpy      - Signal processing for CW decode
    scipy      - DSP filters for tone detection
    sounddevice- Audio playback for sidetone
    pyrtlsdr   - RTL-SDR receiver interface (optional)

No system binaries are required. All processing is
done in Python using numpy/scipy DSP.

Docker Notes:
    All packages must be in requirements.txt.
    Runtime pip installs are skipped in Docker.
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
            if extra_data and isinstance(extra_data, dict):
                data.update(extra_data)
            try:
                os.makedirs(
                    os.path.dirname(path), exist_ok=True
                )
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Morse] Marker write error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class MorseInstaller(BaseInstaller):
    """
    Manages Morse plugin dependency installation.

    All dependencies are pure Python / pip packages.
    No system binary installation is required.
    """

    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__), '.installed'
    )

    REQUIRED_PACKAGES = [
        'numpy',
        'scipy',
    ]

    OPTIONAL_PACKAGES = [
        'sounddevice',   # Server-side audio playback
        'pyrtlsdr',      # RTL-SDR Python bindings
    ]

    def __init__(self):
        super().__init__()
        print(
            f"[Morse] Installer init | "
            f"Docker: {self.in_docker}"
        )

    def is_installed(self):
        return os.path.exists(self.INSTALL_MARKER)

    def install_python_packages_all(self):
        """Install required and optional packages."""
        print("[Morse] Installing Python packages...")

        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )

        for pkg in self.OPTIONAL_PACKAGES:
            self.pip_install(pkg)

        if failed and self.in_docker:
            print(
                f"[Morse] Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        return len(failed) == 0

    def get_install_info(self):
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Install Morse plugin dependencies.

        Returns:
            bool: True always — plugin works with
                  minimal deps (numpy/scipy in image)
        """
        if self.is_installed():
            print("[Morse] ✓ Already installed")
            return True

        print("[Morse] ==========================================")
        print("[Morse] Starting first-run installation")
        print("[Morse] ==========================================")

        self.install_python_packages_all()

        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': 'pip',
                'platform': platform.platform(),
            }
        )

        print("[Morse] ✓ Installation complete")
        return True
