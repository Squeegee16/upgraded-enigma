"""
QSSTV Installer
================
Handles first-run installation of QSSTV and dependencies.

QSSTV Installation Methods:
    1. apt-get (Debian/Ubuntu) - Primary
       Installs qsstv from official repositories
    2. Build from source (GitHub) - Fallback
       Clones and builds from https://github.com/ON4QZ/QSSTV

Python Dependencies:
    - requests: HTTP client for API calls
    - psutil: Process management
    - Pillow: Image processing for SSTV images
    - watchdog: File system monitoring for received images

System Dependencies (installed automatically):
    - Qt5 libraries (for QSSTV GUI)
    - ALSA/PulseAudio (for audio I/O)
    - hamlib (for radio control)
    - v4l-utils (for video capture)
    - cmake/build-essential (for source builds)

Source: https://github.com/ON4QZ/QSSTV
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from pathlib import Path


class QSStvInstaller:
    """
    Manages QSSTV installation and dependency verification.

    Detects system capabilities and installs QSSTV via the
    most appropriate method. Tracks installation state via
    a JSON marker file.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # QSSTV binary name
    QSSTV_BINARY = 'qsstv'

    # GitHub repository
    QSSTV_REPO = 'https://github.com/ON4QZ/QSSTV.git'

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
        'Pillow',
        'watchdog',
    ]

    # System dependencies for apt-get
    APT_DEPENDENCIES = [
        'qsstv',
        'libhamlib-utils',
        'libpulse-dev',
        'libasound2-dev',
    ]

    # Build dependencies for compiling from source
    BUILD_DEPS_APT = [
        'cmake',
        'build-essential',
        'qtbase5-dev',
        'qt5-qmake',
        'qtmultimedia5-dev',
        'libqt5multimedia5-plugins',
        'libqt5serialport5-dev',
        'libqt5sql5-sqlite',
        'libpulse-dev',
        'libasound2-dev',
        'libv4l-dev',
        'libhamlib-dev',
        'libfftw3-dev',
        'git',
    ]

    def __init__(self):
        """
        Initialize installer with system detection.
        """
        self.plugin_dir = os.path.dirname(__file__)
        self.package_manager = self._detect_package_manager()
        self.qsstv_binary_path = shutil.which(self.QSSTV_BINARY)

        print(
            f"[QSSTV] Package manager: "
            f"{self.package_manager or 'not found'}"
        )

    def _detect_package_manager(self):
        """
        Detect available system package manager.

        Returns:
            str: Package manager name or None
        """
        for manager in ['apt-get', 'dnf', 'yum', 'pacman']:
            if shutil.which(manager):
                return manager
        return None

    def is_installed(self):
        """
        Check if QSSTV is installed and marker exists.

        Returns:
            bool: True if QSSTV is available
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        return shutil.which(self.QSSTV_BINARY) is not None

    def is_running(self):
        """
        Check if QSSTV process is currently running.

        Returns:
            bool: True if QSSTV process is active
        """
        try:
            result = subprocess.run(
                ['pgrep', '-x', self.QSSTV_BINARY],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages installed
        """
        print("[QSSTV] Installing Python packages...")
        failed = []

        for package in self.REQUIRED_PACKAGES:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[QSSTV] ✓ {package}")
            except subprocess.CalledProcessError as e:
                print(f"[QSSTV] WARNING: {package} failed: {e}")
                failed.append(package)

        return len(failed) == 0

    def install_via_apt(self):
        """
        Install QSSTV and dependencies via apt-get.

        Installs QSSTV from official Debian/Ubuntu
        package repositories along with required
        system libraries.

        Returns:
            bool: True if installation successful
        """
        print("[QSSTV] Installing via apt-get...")

        try:
            # Update package list
            print("[QSSTV] Updating package list...")
            subprocess.run(
                ['sudo', 'apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            # Install QSSTV package
            print("[QSSTV] Installing qsstv package...")
            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y', 'qsstv'],
                check=True,
                capture_output=True
            )

            print("[QSSTV] ✓ Installed via apt-get")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[QSSTV] apt-get failed: {e}")
            print("[QSSTV] Trying source build...")
            return self.build_from_source()

    def install_via_dnf(self):
        """
        Install QSSTV via dnf (Fedora/RHEL).

        Returns:
            bool: True if installation successful
        """
        print("[QSSTV] Installing via dnf...")

        try:
            subprocess.run(
                ['sudo', 'dnf', 'install', '-y', 'qsstv'],
                check=True,
                capture_output=True
            )
            print("[QSSTV] ✓ Installed via dnf")
            return True
        except subprocess.CalledProcessError:
            return self.build_from_source()

    def install_via_pacman(self):
        """
        Install QSSTV via pacman (Arch Linux).

        Tries AUR via yay if direct pacman fails.

        Returns:
            bool: True if installation successful
        """
        print("[QSSTV] Installing via pacman...")

        try:
            subprocess.run(
                ['sudo', 'pacman', '-S', '--noconfirm', 'qsstv'],
                check=True,
                capture_output=True
            )
            print("[QSSTV] ✓ Installed via pacman")
            return True
        except subprocess.CalledProcessError:
            # Try AUR
            if shutil.which('yay'):
                try:
                    subprocess.run(
                        ['yay', '-S', '--noconfirm', 'qsstv'],
                        check=True,
                        capture_output=True
                    )
                    print("[QSSTV] ✓ Installed via yay (AUR)")
                    return True
                except subprocess.CalledProcessError:
                    pass

            return self.build_from_source()

    def build_from_source(self):
        """
        Build and install QSSTV from GitHub source.

        Clones the QSSTV repository, installs build
        dependencies, and compiles with cmake.

        Returns:
            bool: True if build successful
        """
        print("[QSSTV] Building from source...")
        build_dir = os.path.join(self.plugin_dir, '_qsstv_build')

        try:
            # Install build dependencies
            if shutil.which('apt-get'):
                print("[QSSTV] Installing build dependencies...")
                subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y'] +
                    self.BUILD_DEPS_APT,
                    check=True,
                    capture_output=True
                )

            # Clean previous build
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

            # Clone repository
            print("[QSSTV] Cloning QSSTV repository...")
            subprocess.run(
                ['git', 'clone', '--depth', '1',
                 self.QSSTV_REPO, build_dir],
                check=True,
                capture_output=True,
                timeout=120
            )

            # Create cmake build directory
            cmake_dir = os.path.join(build_dir, 'build')
            os.makedirs(cmake_dir, exist_ok=True)

            # Run cmake configuration
            print("[QSSTV] Configuring with cmake...")
            subprocess.run(
                ['cmake', '..', '-DCMAKE_INSTALL_PREFIX=/usr/local'],
                check=True,
                capture_output=True,
                cwd=cmake_dir
            )

            # Build with available CPU cores
            cpu_count = os.cpu_count() or 2
            print(f"[QSSTV] Building ({cpu_count} cores)...")
            subprocess.run(
                ['make', f'-j{cpu_count}'],
                check=True,
                capture_output=True,
                cwd=cmake_dir,
                timeout=600
            )

            # Install
            print("[QSSTV] Installing...")
            self._run_system_command(
                self._sudo + ['apt-get', ...],
                timeout=300
            )

            print("[QSSTV] ✓ Built and installed from source")
            return True

        except subprocess.TimeoutExpired:
            print("[QSSTV] ERROR: Build timed out")
            return False
        except subprocess.CalledProcessError as e:
            print(f"[QSSTV] ERROR: Build failed: {e}")
            return False
        except Exception as e:
            print(f"[QSSTV] ERROR: {e}")
            return False
        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

    def get_version(self):
        """
        Get installed QSSTV version.

        Returns:
            str: Version string or None
        """
        binary = shutil.which(self.QSSTV_BINARY)
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
            # QSSTV may output version to stderr
            return result.stderr.strip() or 'installed'
        except Exception:
            return 'installed'

    def write_install_marker(self, method, version=None):
        """
        Write installation marker file.

        Args:
            method: Installation method used
            version: QSSTV version string
        """
        marker_data = {
            'installed': True,
            'method': method,
            'version': version,
            'platform': platform.platform(),
            'arch': platform.machine(),
            'binary_path': shutil.which(self.QSSTV_BINARY)
        }

        try:
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print("[QSSTV] ✓ Installation marker written")
        except Exception as e:
            print(f"[QSSTV] WARNING: Marker write failed: {e}")

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
            print("[QSSTV] ✓ Already installed")
            return True

        # QSSTV already in PATH
        if shutil.which(self.QSSTV_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[QSSTV] ✓ Found in PATH")
            return True

        print("[QSSTV] ==========================================")
        print("[QSSTV] Starting first-run installation")
        print("[QSSTV] ==========================================")

        # Step 1: Python packages
        print("\n[QSSTV] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: QSSTV
        print("\n[QSSTV] Step 2: Installing QSSTV...")
        success = False

        if self.package_manager == 'apt-get':
            success = self.install_via_apt()
        elif self.package_manager in ('dnf', 'yum'):
            success = self.install_via_dnf()
        elif self.package_manager == 'pacman':
            success = self.install_via_pacman()
        else:
            success = self.build_from_source()

        if not success:
            print("[QSSTV] ERROR: Installation failed")
            print("[QSSTV] Manual install: https://github.com/ON4QZ/QSSTV")
            return False

        # Update binary path
        self.qsstv_binary_path = shutil.which(self.QSSTV_BINARY)

        # Write marker
        version = self.get_version()
        self.write_install_marker(
            self.package_manager or 'source',
            version
        )

        print("\n[QSSTV] ==========================================")
        print("[QSSTV] ✓ Installation complete!")
        if version:
            print(f"[QSSTV]   Version: {version}")
        print("[QSSTV] ==========================================\n")

        return True
