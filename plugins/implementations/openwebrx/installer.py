"""
OpenWebRX Dependency Installer
================================
Handles installation of OpenWebRX and its required dependencies
on first run.

OpenWebRX can be installed via:
    - Docker image (recommended)
    - Debian/Ubuntu package repository
    - PyPI package

This installer handles:
    - System package dependencies
    - OpenWebRX installation via package manager or Docker
    - Configuration directory setup
    - Required Python packages

Dependencies:
    - OpenWebRX (main application)
    - docker or system packages
    - requests (Python HTTP library)
    - psutil (process management)
    - websockets (WebSocket client)

Reference: https://github.com/jketterl/openwebrx/wiki/Installation-guide
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from pathlib import Path


class OpenWebRXInstaller:
    """
    Manages installation and verification of OpenWebRX dependencies.

    Supports multiple installation methods:
    1. Docker (recommended - most reliable)
    2. Debian/Ubuntu package repository
    3. Direct pip installation

    The installer automatically detects the best method
    based on the system configuration.
    """

    # Installation state tracking file
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # OpenWebRX Docker image
    DOCKER_IMAGE = 'jketterl/openwebrx:latest'

    # OpenWebRX Debian repository
    DEBIAN_REPO = 'https://repo.openwebrx.de/debian/'

    # Required Python packages for plugin communication
    REQUIRED_PYTHON_PACKAGES = [
        'requests',
        'psutil',
        'websockets',
        'aiohttp',
    ]

    # OpenWebRX default ports
    DEFAULT_HTTP_PORT = 8073
    DEFAULT_WS_PORT = 8073

    def __init__(self):
        """
        Initialize the installer.
        Sets up paths and detects system capabilities.
        """
        self.plugin_dir = os.path.dirname(__file__)
        self.install_method = None

        # Detect available installation methods
        self._detect_install_method()

    def _detect_install_method(self):
        """
        Detect the best available installation method.

        Priority:
        1. Docker (if available)
        2. apt-get (Debian/Ubuntu)
        3. pip (fallback)
        """
        if shutil.which('docker'):
            self.install_method = 'docker'
            print("[OpenWebRX] Installation method: Docker")
        elif shutil.which('apt-get'):
            self.install_method = 'apt'
            print("[OpenWebRX] Installation method: apt-get")
        else:
            self.install_method = 'pip'
            print("[OpenWebRX] Installation method: pip")

    def is_installed(self):
        """
        Check if OpenWebRX has been previously installed.

        Verifies both the marker file and actual installation.

        Returns:
            bool: True if installation is complete and functional
        """
        # Check marker file
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Verify actual installation based on method
        if self.install_method == 'docker':
            return self._check_docker_image()
        elif self.install_method == 'apt':
            return shutil.which('openwebrx') is not None
        else:
            # Check pip installation
            try:
                import openwebrx
                return True
            except ImportError:
                return False

    def _check_docker_image(self):
        """
        Check if OpenWebRX Docker image is available.

        Returns:
            bool: True if image exists locally
        """
        try:
            result = subprocess.run(
                ['docker', 'images', '-q', self.DOCKER_IMAGE],
                capture_output=True,
                text=True,
                timeout=10
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages installed successfully
        """
        print("[OpenWebRX] Installing required Python packages...")

        failed = []
        for package in self.REQUIRED_PYTHON_PACKAGES:
            try:
                print(f"[OpenWebRX] Installing {package}...")
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[OpenWebRX] ✓ {package} installed")
            except subprocess.CalledProcessError as e:
                print(f"[OpenWebRX] WARNING: Failed to install {package}: {e}")
                failed.append(package)

        if failed:
            print(f"[OpenWebRX] WARNING: Failed packages: {failed}")
            return False

        return True

    def install_via_docker(self):
        """
        Pull OpenWebRX Docker image.

        Returns:
            bool: True if image pulled successfully
        """
        print(f"[OpenWebRX] Pulling Docker image: {self.DOCKER_IMAGE}")

        try:
            # Pull the Docker image
            result = subprocess.run(
                ['docker', 'pull', self.DOCKER_IMAGE],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes for image pull
            )

            if result.returncode == 0:
                print(f"[OpenWebRX] ✓ Docker image pulled: {self.DOCKER_IMAGE}")
                return True
            else:
                print(f"[OpenWebRX] ERROR: Docker pull failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("[OpenWebRX] ERROR: Docker pull timed out")
            return False
        except Exception as e:
            print(f"[OpenWebRX] ERROR: Docker pull error: {e}")
            return False

    def install_via_apt(self):
        """
        Install OpenWebRX via apt-get.

        Detects Docker environment and adjusts sudo usage.
        In Docker containers running as root, sudo is not
        needed or available.

        Returns:
            bool: True if installation successful
        """
        print("[OpenWebRX] Installing via apt-get...")

        # Detect if we are running as root (Docker)
        # In Docker with non-root user, sudo may not exist
        is_root = (os.getuid() == 0)
        sudo_available = shutil.which('sudo') is not None

        # Build prefix: use sudo only if available and needed
        if is_root:
            sudo_prefix = []
            print("[OpenWebRX] Running as root, no sudo needed")
        elif sudo_available:
            sudo_prefix = ['sudo']
        else:
            print(
                "[OpenWebRX] WARNING: sudo not available. "
                "Trying without sudo..."
            )
            sudo_prefix = []

        try:
            # Update package list
            subprocess.run(
                sudo_prefix + ['apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            # Install OpenWebRX
            subprocess.run(
                sudo_prefix + [
                    'apt-get', 'install', '-y', 'openwebrx'
                ],
                check=True,
                capture_output=True
            )

            print("[OpenWebRX] ✓ Installed via apt-get")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[OpenWebRX] apt-get failed: {e}")
            return self._install_via_flatpak()
        except FileNotFoundError as e:
            print(f"[OpenWebRX] Command not found: {e}")
            return self._install_via_flatpak()
        except Exception as e:
            print(f"[OpenWebRX] Installation error: {e}")
            return False
    def install_via_pip(self):
        """
        Install OpenWebRX via pip as a fallback method.

        Returns:
            bool: True if installation was successful
        """
        print("[OpenWebRX] Installing via pip...")

        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install',
                 '--quiet', 'openwebrx'],
                check=True,
                capture_output=True
            )
            print("[OpenWebRX] ✓ OpenWebRX installed via pip")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[OpenWebRX] ERROR: pip installation failed: {e}")
            return False

    def write_install_marker(self, method):
        """
        Write installation marker file with installation details.

        Args:
            method: Installation method used
        """
        marker_data = {
            'installed': True,
            'method': method,
            'platform': platform.platform(),
            'python_version': sys.version,
            'docker_image': self.DOCKER_IMAGE if method == 'docker' else None,
            'install_date': str(Path(self.INSTALL_MARKER).stat().st_mtime
                                if os.path.exists(self.INSTALL_MARKER)
                                else '')
        }

        try:
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print(f"[OpenWebRX] ✓ Installation marker written")
        except Exception as e:
            print(f"[OpenWebRX] WARNING: Could not write marker: {e}")

    def get_install_info(self):
        """
        Read installation marker information.

        Returns:
            dict: Installation details or empty dict
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return {}

        try:
            with open(self.INSTALL_MARKER, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def run(self):
        """
        Execute the full installation process.

        Handles first-run detection, installs Python packages,
        and installs OpenWebRX via the best available method.

        Returns:
            bool: True if installation was successful or already complete
        """
        # Check if already installed
        if self.is_installed():
            print("[OpenWebRX] ✓ Already installed, skipping")
            return True

        print("[OpenWebRX] ========================================")
        print("[OpenWebRX] Starting first-run installation")
        print("[OpenWebRX] ========================================")

        # Step 1: Install Python dependencies
        print("\n[OpenWebRX] Step 1: Installing Python packages...")
        if not self.install_python_packages():
            print("[OpenWebRX] WARNING: Some Python packages failed")
            # Continue anyway - non-fatal

        # Step 2: Install OpenWebRX
        print(f"\n[OpenWebRX] Step 2: Installing OpenWebRX via {self.install_method}...")
        success = False

        if self.install_method == 'docker':
            success = self.install_via_docker()
        elif self.install_method == 'apt':
            success = self.install_via_apt()
        else:
            success = self.install_via_pip()

        if not success:
            print("[OpenWebRX] ERROR: OpenWebRX installation failed")
            return False

        # Step 3: Write marker
        self.write_install_marker(self.install_method)

        print("\n[OpenWebRX] ========================================")
        print("[OpenWebRX] ✓ Installation complete!")
        print("[OpenWebRX] ========================================\n")

        return True
