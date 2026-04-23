"""
WSJT-X Installer
=================
Handles first-run installation of WSJT-X and dependencies.

WSJT-X Installation Methods:
    1. apt-get (Debian/Ubuntu) - Recommended
       Installs wsjtx package from official repos
    2. dnf/yum (RedHat/Fedora/CentOS)
    3. Flatpak (Universal Linux)
       flatpak install wsjtx
    4. AppImage (Direct download from WSJT-X)
       Downloaded from physics.princeton.edu

Python Dependencies:
    - requests: HTTP client
    - psutil: Process management

UDP Communication:
    WSJT-X uses Python struct and socket modules for
    UDP communication - no extra packages required.

Note:
    WSJT-X requires a sound card and radio interface.
    For testing, it can run in demo mode without hardware.

Source: https://github.com/WSJTX/wsjtx
Download: https://physics.princeton.edu/pulsar/k1jt/wsjtx.html
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import urllib.request
from pathlib import Path


class WSJTXInstaller:
    """
    Manages WSJT-X installation and verification.

    Supports multiple installation methods and tracks
    installation state via a JSON marker file to prevent
    repeated installation on subsequent runs.
    """

    # Installation marker file
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # WSJT-X binary name
    WSJTX_BINARY = 'wsjtx'

    # WSJT-X download base URL
    WSJTX_DOWNLOAD_BASE = (
        'https://physics.princeton.edu/pulsar/k1jt/'
    )

    # Required Python packages for the plugin
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    # Package names per package manager
    PACKAGES = {
        'apt-get': ['wsjtx'],
        'dnf': ['wsjtx'],
        'yum': ['wsjtx'],
        'pacman': ['wsjtx'],
        'zypper': ['wsjtx'],
    }

    def __init__(self):
        """
        Initialize installer with system detection.

        Detects available package managers and the current
        system architecture for download selection.
        """
        self.plugin_dir = os.path.dirname(__file__)
        self.package_manager = self._detect_package_manager()
        self.arch = platform.machine()
        self.wsjtx_binary_path = shutil.which(self.WSJTX_BINARY)

        print(
            f"[WSJTX] Package manager: "
            f"{self.package_manager or 'not found'}"
        )
        print(f"[WSJTX] Architecture: {self.arch}")

    def _detect_package_manager(self):
        """
        Detect available system package manager.

        Returns:
            str: Package manager name or None
        """
        for manager in ['apt-get', 'dnf', 'yum', 'pacman', 'zypper']:
            if shutil.which(manager):
                return manager
        return None

    def is_installed(self):
        """
        Check if WSJT-X is installed and marker exists.

        Returns:
            bool: True if WSJT-X is available
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Check binary availability
        return shutil.which(self.WSJTX_BINARY) is not None

    def is_running(self):
        """
        Check if WSJT-X process is currently running.

        Returns:
            bool: True if WSJT-X process is active
        """
        try:
            result = subprocess.run(
                ['pgrep', '-x', self.WSJTX_BINARY],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def install_python_packages(self):
        """
        Install required Python packages via pip.

        Returns:
            bool: True if all packages installed
        """
        print("[WSJTX] Installing Python packages...")
        failed = []

        for package in self.REQUIRED_PACKAGES:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[WSJTX] ✓ {package}")
            except subprocess.CalledProcessError as e:
                print(f"[WSJTX] WARNING: {package} failed: {e}")
                failed.append(package)

        return len(failed) == 0

    def install_via_apt(self):
        """
        Install WSJT-X via apt-get.

        On some Debian/Ubuntu systems the wsjtx package
        may be in the 'hamradio' section or require
        additional repositories.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via apt-get...")

        try:
            # Update package list
            subprocess.run(
                ['sudo', 'apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            # Attempt direct installation
            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y', 'wsjtx'],
                check=True,
                capture_output=True
            )

            print("[WSJTX] ✓ Installed via apt-get")
            return True

        except subprocess.CalledProcessError:
            print("[WSJTX] apt install failed, trying alternatives...")
            return self._install_via_flatpak()

    def install_via_dnf(self):
        """
        Install WSJT-X via dnf package manager.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via dnf...")

        try:
            # Enable ham radio repo if needed
            subprocess.run(
                ['sudo', 'dnf', 'install', '-y', 'wsjtx'],
                check=True,
                capture_output=True
            )
            print("[WSJTX] ✓ Installed via dnf")
            return True
        except subprocess.CalledProcessError:
            print("[WSJTX] dnf install failed, trying Flatpak...")
            return self._install_via_flatpak()

    def install_via_pacman(self):
        """
        Install WSJT-X via pacman (Arch Linux).

        Tries AUR via yay if direct pacman fails.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via pacman...")

        try:
            subprocess.run(
                ['sudo', 'pacman', '-S', '--noconfirm', 'wsjtx'],
                check=True,
                capture_output=True
            )
            print("[WSJTX] ✓ Installed via pacman")
            return True
        except subprocess.CalledProcessError:
            # Try AUR via yay
            if shutil.which('yay'):
                try:
                    subprocess.run(
                        ['yay', '-S', '--noconfirm', 'wsjtx'],
                        check=True,
                        capture_output=True
                    )
                    print("[WSJTX] ✓ Installed via yay (AUR)")
                    return True
                except subprocess.CalledProcessError:
                    pass

            return self._install_via_flatpak()

    def _install_via_flatpak(self):
        """
        Install WSJT-X via Flatpak.

        Flatpak provides a universal Linux installation
        method that works across distributions.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Trying Flatpak installation...")

        # Check if flatpak is available
        if not shutil.which('flatpak'):
            print("[WSJTX] Flatpak not available")
            return self._install_appimage()

        try:
            # Add Flathub if not already added
            subprocess.run(
                ['flatpak', 'remote-add', '--if-not-exists',
                 'flathub',
                 'https://flathub.org/repo/flathub.flatpakrepo'],
                check=True,
                capture_output=True
            )

            # Install WSJT-X from Flathub
            subprocess.run(
                ['flatpak', 'install', '-y', 'flathub',
                 'org.physics.wsjtx'],
                check=True,
                capture_output=True,
                timeout=300
            )

            # Create wrapper script
            wrapper_path = os.path.expanduser('~/.local/bin/wsjtx')
            os.makedirs(os.path.dirname(wrapper_path), exist_ok=True)

            wrapper_content = (
                '#!/bin/bash\n'
                'exec flatpak run org.physics.wsjtx "$@"\n'
            )

            with open(wrapper_path, 'w') as f:
                f.write(wrapper_content)

            os.chmod(wrapper_path, 0o755)

            print("[WSJTX] ✓ Installed via Flatpak")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[WSJTX] Flatpak failed: {e}")
            return self._install_appimage()

    def _install_appimage(self):
        """
        Download and install WSJT-X AppImage.

        Downloads the AppImage from the official WSJT-X
        distribution site and sets it up as a runnable
        application with a wrapper script.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Downloading WSJT-X AppImage...")

        try:
            # Determine architecture for download
            arch = 'x86_64' if self.arch == 'x86_64' else 'aarch64'

            # AppImage URL pattern
            # Check actual URL from official site
            appimage_url = (
                f"{self.WSJTX_DOWNLOAD_BASE}"
                f"wsjtx_2.7.0_Linux_{arch}.AppImage"
            )

            # Download directory
            install_dir = os.path.expanduser('~/.local/share/wsjtx')
            os.makedirs(install_dir, exist_ok=True)

            appimage_path = os.path.join(
                install_dir, 'wsjtx.AppImage'
            )

            print(f"[WSJTX] Downloading from {appimage_url}...")
            urllib.request.urlretrieve(appimage_url, appimage_path)

            # Make executable
            os.chmod(appimage_path, 0o755)

            # Create wrapper script in PATH
            wrapper_dir = os.path.expanduser('~/.local/bin')
            os.makedirs(wrapper_dir, exist_ok=True)

            wrapper_path = os.path.join(wrapper_dir, 'wsjtx')
            wrapper_content = (
                f'#!/bin/bash\n'
                f'exec "{appimage_path}" "$@"\n'
            )

            with open(wrapper_path, 'w') as f:
                f.write(wrapper_content)

            os.chmod(wrapper_path, 0o755)

            print(
                f"[WSJTX] ✓ AppImage installed: {appimage_path}"
            )
            return True

        except Exception as e:
            print(f"[WSJTX] AppImage install failed: {e}")
            print("[WSJTX] Please install WSJT-X manually:")
            print("[WSJTX] https://physics.princeton.edu/pulsar/k1jt/wsjtx.html")
            return False

    def get_version(self):
        """
        Get installed WSJT-X version.

        Returns:
            str: Version string or None
        """
        binary = shutil.which(self.WSJTX_BINARY)
        if not binary:
            return None

        try:
            result = subprocess.run(
                [binary, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def write_install_marker(self, method, version=None):
        """
        Write installation marker with metadata.

        Args:
            method: Installation method used
            version: WSJT-X version string
        """
        marker_data = {
            'installed': True,
            'method': method,
            'version': version,
            'platform': platform.platform(),
            'arch': self.arch,
            'binary_path': shutil.which(self.WSJTX_BINARY)
        }

        try:
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print("[WSJTX] ✓ Installation marker written")
        except Exception as e:
            print(f"[WSJTX] WARNING: Marker write failed: {e}")

    def get_install_info(self):
        """
        Read installation marker data.

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
        Execute the complete installation process.

        Returns:
            bool: True if installation successful
        """
        # Already installed
        if self.is_installed():
            print("[WSJTX] ✓ Already installed")
            return True

        # Check if already in PATH
        if shutil.which(self.WSJTX_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[WSJTX] ✓ Found in PATH")
            return True

        print("[WSJTX] ==========================================")
        print("[WSJTX] Starting first-run installation")
        print("[WSJTX] ==========================================")

        # Step 1: Python packages
        print("\n[WSJTX] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: WSJT-X
        print("\n[WSJTX] Step 2: Installing WSJT-X...")
        success = False

        if self.package_manager == 'apt-get':
            success = self.install_via_apt()
        elif self.package_manager in ('dnf', 'yum'):
            success = self.install_via_dnf()
        elif self.package_manager == 'pacman':
            success = self.install_via_pacman()
        else:
            success = self._install_via_flatpak()

        if not success:
            print("[WSJTX] ERROR: Installation failed")
            return False

        # Write marker
        version = self.get_version()
        self.write_install_marker(
            self.package_manager or 'flatpak',
            version
        )

        print("\n[WSJTX] ==========================================")
        print("[WSJTX] ✓ Installation complete!")
        if version:
            print(f"[WSJTX]   Version: {version}")
        print("[WSJTX] ==========================================\n")

        return True