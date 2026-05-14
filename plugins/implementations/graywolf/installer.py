"""
GrayWolf Dependency Installer
==============================
Handles installation of GrayWolf and its required dependencies
on first run. Checks for Go runtime, GrayWolf binary, and
required Python packages.

Dependencies managed:
    - Go runtime (for building GrayWolf)
    - GrayWolf binary (built from source)
    - requests (Python HTTP library)
    - psutil (Process management)
"""

import os
import sys
import subprocess
import shutil
import platform
import json
from pathlib import Path


class GrayWolfInstaller:
    """
    Manages installation and verification of GrayWolf dependencies.

    This class handles:
    - Checking if GrayWolf is already installed
    - Installing Go runtime if required
    - Cloning and building GrayWolf from source
    - Installing required Python packages
    - Tracking installation state via a marker file
    """

    # Installation state file - tracks whether install has been completed
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # GrayWolf binary name
    GRAYWOLF_BINARY = 'graywolf'

    # Default install directory for GrayWolf binary
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # GrayWolf GitHub repository
    GRAYWOLF_REPO = 'https://github.com/chrissnell/graywolf'

    # Required Python packages for this plugin
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    def __init__(self):
        """Initialize the installer with path configuration."""
        self.plugin_dir = os.path.dirname(__file__)
        self.graywolf_binary_path = shutil.which(self.GRAYWOLF_BINARY) or \
            os.path.join(self.INSTALL_DIR, self.GRAYWOLF_BINARY)

    def is_installed(self):
        """
        Check if GrayWolf has been previously installed.

        Returns:
            bool: True if installation marker exists and binary is found
        """
        marker_exists = os.path.exists(self.INSTALL_MARKER)
        binary_exists = os.path.exists(self.graywolf_binary_path) or \
            shutil.which(self.GRAYWOLF_BINARY) is not None

        return marker_exists and binary_exists

    def check_go_installed(self):
        """
        Check if Go runtime is installed.

        Returns:
            bool: True if Go is available in PATH
        """
        return shutil.which('go') is not None

    def install_go(self):
        """
        Install Go runtime using system package manager.

        Returns:
            bool: True if installation was successful
        """
        print("[GrayWolf] Installing Go runtime...")

        try:
            # Detect Linux distribution package manager
            if shutil.which('apt-get'):
                # Debian/Ubuntu
                subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y', 'golang-go'],
                    check=True,
                    capture_output=True
                )
            elif shutil.which('yum'):
                # RedHat/CentOS
                subprocess.run(
                    ['sudo', 'yum', 'install', '-y', 'golang'],
                    check=True,
                    capture_output=True
                )
            elif shutil.which('dnf'):
                # Fedora
                subprocess.run(
                    ['sudo', 'dnf', 'install', '-y', 'golang'],
                    check=True,
                    capture_output=True
                )
            else:
                print("[GrayWolf] ERROR: Could not detect package manager")
                print("[GrayWolf] Please install Go manually: https://golang.org/dl/")
                return False

            print("[GrayWolf] ✓ Go runtime installed")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[GrayWolf] ERROR: Failed to install Go: {e}")
            return False

    def install_python_packages(self):
        """
        Install required Python packages using pip.

        Returns:
            bool: True if all packages installed successfully
        """
        print("[GrayWolf] Installing required Python packages...")

        try:
            for package in self.REQUIRED_PACKAGES:
                print(f"[GrayWolf] Installing {package}...")
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', package],
                    check=True,
                    capture_output=True
                )
                print(f"[GrayWolf] ✓ {package} installed")

            return True

        except subprocess.CalledProcessError as e:
            print(f"[GrayWolf] ERROR: Failed to install Python packages: {e}")
            return False

    def clone_and_build_graywolf(self):
        """
        Clone GrayWolf from GitHub and build the binary.

        Returns:
            bool: True if build was successful
        """
        print("[GrayWolf] Cloning and building GrayWolf...")

        # Create temporary build directory
        build_dir = os.path.join(self.plugin_dir, '_build')
        os.makedirs(build_dir, exist_ok=True)

        try:
            # Clone repository
            print("[GrayWolf] Cloning repository...")
            subprocess.run(
                ['git', 'clone', self.GRAYWOLF_REPO, build_dir],
                check=True,
                capture_output=True
            )

            # Build GrayWolf binary using Go
            print("[GrayWolf] Building binary...")
            subprocess.run(
                ['go', 'build', '-o', self.GRAYWOLF_BINARY],
                check=True,
                capture_output=True,
                cwd=build_dir
            )

            # Create install directory if needed
            os.makedirs(self.INSTALL_DIR, exist_ok=True)

            # Copy binary to install directory
            built_binary = os.path.join(build_dir, self.GRAYWOLF_BINARY)
            shutil.copy2(built_binary, self.graywolf_binary_path)
            os.chmod(self.graywolf_binary_path, 0o755)

            print(f"[GrayWolf] ✓ Binary installed to {self.graywolf_binary_path}")

            return True

        except subprocess.CalledProcessError as e:
            print(f"[GrayWolf] ERROR: Build failed: {e}")
            return False
        except Exception as e:
            print(f"[GrayWolf] ERROR: Installation failed: {e}")
            return False
        finally:
            # Clean up build directory
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

    def write_install_marker(self):
        """
        Write installation marker file to track completed installation.
        Stores installation details as JSON.
        """
        marker_data = {
            'installed': True,
            'binary_path': self.graywolf_binary_path,
            'install_date': str(Path(self.INSTALL_MARKER).stat().st_mtime
                                if os.path.exists(self.INSTALL_MARKER) else ''),
            'platform': platform.platform(),
            'python_version': sys.version
        }

        with open(self.INSTALL_MARKER, 'w') as f:
            json.dump(marker_data, f, indent=2)

        print(f"[GrayWolf] ✓ Installation marker written")

    def run(self):
        """
        Execute the full installation process.

        Checks for existing installation, installs dependencies
        as needed, and writes the installation marker on success.

        Returns:
            bool: True if installation was successful or already complete
        """
        # Check if already installed
        if self.is_installed():
            print("[GrayWolf] ✓ Already installed, skipping")
            return True

        print("[GrayWolf] ================================")
        print("[GrayWolf] Starting first-run installation")
        print("[GrayWolf] ================================")

        # Step 1: Install Python packages
        if not self.install_python_packages():
            print("[GrayWolf] ERROR: Python package installation failed")
            return False

        # Step 2: Check for git
        if not shutil.which('git'):
            print("[GrayWolf] ERROR: git is required but not found")
            print("[GrayWolf] Please install git and try again")
            return False

        # Step 3: Check/install Go runtime
        if not self.check_go_installed():
            print("[GrayWolf] Go runtime not found, attempting installation...")
            if not self.install_go():
                print("[GrayWolf] ERROR: Could not install Go runtime")
                print("[GrayWolf] Please install Go manually: https://golang.org/dl/")
                return False

        # Step 4: Build GrayWolf
        if not self.graywolf_binary_path or \
                not os.path.exists(self.graywolf_binary_path):
            if not self.clone_and_build_graywolf():
                print("[GrayWolf] ERROR: GrayWolf build failed")
                return False

        # Step 5: Write installation marker
        self.write_install_marker()

        print("[GrayWolf] ================================")
        print("[GrayWolf] ✓ Installation complete!")
        print("[GrayWolf] ================================")

        return True