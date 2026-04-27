"""
Base Plugin Installer
======================
Shared utility class for all plugin installers.

Provides:
    - sudo detection for Docker vs host environments
    - pip install with correct venv Python
    - Common system package installation
    - Installation marker management

All plugin installers should use these helpers
instead of hardcoding sudo or Python paths.
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path


class BaseInstaller:
    """
    Shared installer utilities for all plugins.

    Handles environment detection (Docker, root, venv)
    and provides safe wrappers around pip and apt-get.
    """

    def __init__(self):
        """Detect runtime environment on init."""
        # Are we running as root (common in Docker)?
        self.is_root = (os.getuid() == 0)

        # Is sudo available?
        self.sudo_available = shutil.which('sudo') is not None

        # Python executable (prefer venv if active)
        self.python = sys.executable

        # Build sudo prefix for system commands
        if self.is_root:
            # Root user — no sudo needed
            self.sudo = []
        elif self.sudo_available:
            self.sudo = ['sudo']
        else:
            # No sudo — try without (may fail for system installs)
            self.sudo = []

    def pip_install(self, package, quiet=True):
        """
        Install a Python package using pip.

        Uses the currently active Python interpreter
        to ensure packages go into the correct venv.

        Args:
            package: Package name to install
            quiet: Suppress pip output if True

        Returns:
            bool: True if installed successfully
        """
        cmd = [self.python, '-m', 'pip', 'install']
        if quiet:
            cmd.append('--quiet')
        cmd.append(package)

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True
            )
            print(f"[Installer] ✓ pip: {package}")
            return True
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else ''
            print(
                f"[Installer] WARNING: pip install "
                f"{package} failed: {stderr[:100]}"
            )
            return False

    def apt_install(self, *packages):
        """
        Install system packages using apt-get.

        Handles root vs non-root environments.

        Args:
            *packages: Package names to install

        Returns:
            bool: True if installed successfully
        """
        if not shutil.which('apt-get'):
            print("[Installer] apt-get not available")
            return False

        try:
            # Update first
            subprocess.run(
                self.sudo + ['apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            # Install packages
            subprocess.run(
                self.sudo + [
                    'apt-get', 'install', '-y'
                ] + list(packages),
                check=True,
                capture_output=True
            )

            print(
                f"[Installer] ✓ apt: {', '.join(packages)}"
            )
            return True

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else ''
            print(
                f"[Installer] apt-get failed: {stderr[:200]}"
            )
            return False
        except FileNotFoundError as e:
            print(f"[Installer] Command not found: {e}")
            return False

    def install_python_packages(self, packages):
        """
        Install a list of Python packages.

        Args:
            packages: List of package name strings

        Returns:
            tuple: (success_count, failed_list)
        """
        failed = []
        for package in packages:
            if not self.pip_install(package):
                failed.append(package)

        return len(packages) - len(failed), failed

    def write_marker(self, marker_path, data=None):
        """
        Write installation marker file.

        Args:
            marker_path: Full path to marker file
            data: Optional dict to store as JSON
        """
        import platform

        marker_data = {
            'installed': True,
            'platform': platform.platform(),
            'python': sys.version,
            'timestamp': __import__(
                'datetime'
            ).datetime.utcnow().isoformat(),
        }

        if data:
            marker_data.update(data)

        try:
            os.makedirs(
                os.path.dirname(marker_path),
                exist_ok=True
            )
            with open(marker_path, 'w') as f:
                json.dump(marker_data, f, indent=2)
        except Exception as e:
            print(f"[Installer] Marker write error: {e}")

    def read_marker(self, marker_path):
        """
        Read installation marker file.

        Args:
            marker_path: Full path to marker file

        Returns:
            dict: Marker data or empty dict
        """
        if not os.path.exists(marker_path):
            return {}
        try:
            with open(marker_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
