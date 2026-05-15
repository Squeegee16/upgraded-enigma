"""
OpenWebRX Plugin Installer
============================
Handles first-run dependency checks for the
OpenWebRX plugin.

OpenWebRX itself runs as a Docker sidecar container
(jketterl/openwebrx:stable) defined in docker-compose.yml.
This installer only manages Python package dependencies
for the plugin's API communication layer.

Python Dependencies:
    requests    - HTTP API communication
    websockets  - WebSocket connection for real-time data
    psutil      - Process monitoring

Docker Notes:
    All packages must be in requirements.txt.
    Runtime pip installs are skipped in Docker.
    OpenWebRX binary is NOT installed here — it runs
    as a separate container.
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
        """Minimal inline fallback for BaseInstaller."""

        def __init__(self):
            try:
                self.is_root = (os.getuid() == 0)
            except AttributeError:
                self.is_root = False

            self.sudo_available = (
                shutil.which('sudo') is not None
            )
            self._sudo = (
                []
                if (
                    self.is_root or
                    not self.sudo_available
                )
                else ['sudo']
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
                    os.path.dirname(path), exist_ok=True
                )
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(
                    f"[OpenWebRX] Marker error: {e}"
                )

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class OpenWebRXInstaller(BaseInstaller):
    """
    Manages OpenWebRX plugin Python dependencies.

    Note: OpenWebRX itself is a Docker sidecar container.
    This installer only manages Python packages needed
    for the plugin to communicate with OpenWebRX via HTTP
    and WebSocket.
    """

    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__), '.installed'
    )

    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    OPTIONAL_PACKAGES = [
        'websockets',
        'aiohttp',
    ]

    def __init__(self):
        """Initialise installer."""
        super().__init__()
        print(
            f"[OpenWebRX] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root}"
        )

    def is_installed(self):
        """Check if plugin dependencies are installed."""
        return os.path.exists(self.INSTALL_MARKER)

    def get_install_info(self):
        """Read installation marker data."""
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Install plugin Python dependencies.

        OpenWebRX container availability is checked
        separately in the manager. This method only
        handles Python package installation.

        Returns:
            bool: True always — plugin loads regardless
        """
        if self.is_installed():
            print("[OpenWebRX] ✓ Already installed")
            return True

        print("[OpenWebRX] ==========================================")
        print("[OpenWebRX] Installing plugin dependencies")
        print("[OpenWebRX] ==========================================")

        # Install Python packages
        available, failed = self.install_python_packages(
            self.REQUIRED_PACKAGES
        )

        for pkg in self.OPTIONAL_PACKAGES:
            self.pip_install(pkg)

        if failed and self.in_docker:
            print(
                f"[OpenWebRX] Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': 'pip',
                'platform': platform.platform(),
                'note': (
                    'OpenWebRX runs as Docker sidecar — '
                    'see docker-compose.yml openwebrx service'
                )
            }
        )

        print("[OpenWebRX] ✓ Plugin dependencies installed")
        return True
