"""
FLdigi Installer
=================
Handles first-run installation of FLdigi and its dependencies.

FLdigi Installation Methods:
    1. apt-get (Debian/Ubuntu) - Recommended
    2. dnf/yum (RedHat/Fedora/CentOS)
    3. pacman (Arch Linux)
    4. Build from source (fallback via GitHub)

Python Dependencies:
    - requests: HTTP client for any web API calls
    - psutil: Process management and monitoring

FLdigi XML-RPC:
    FLdigi exposes an XML-RPC interface on port 7362.
    This plugin communicates via Python's built-in
    xmlrpc.client module - no extra packages needed.

Source: https://github.com/w1hkj/fldigi/

Note on macOS/Windows:
    This plugin targets Linux only. FLdigi binaries
    for other platforms are available from:
    http://www.w1hkj.com/
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from pathlib import Path


class FldigiInstaller:
    """
    Manages FLdigi installation and dependency verification.

    Detects the system package manager and installs FLdigi
    via the most appropriate method. Tracks installation
    state via a JSON marker file to prevent re-installation.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # FLdigi package names per package manager
    PACKAGE_NAMES = {
        'apt-get': 'fldigi',
        'dnf': 'fldigi',
        'yum': 'fldigi',
        'pacman': 'fldigi',
        'zypper': 'fldigi',
    }

    # Build dependencies for compiling from source
    BUILD_DEPS_APT = [
        'build-essential',
        'autoconf',
        'automake',
        'libtool',
        'libfltk1.3-dev',
        'libpulse-dev',
        'libasound2-dev',
        'libsamplerate-dev',
        'libsndfile1-dev',
        'portaudio19-dev',
        'libhamlib-dev',
        'libxft-dev',
        'libxinerama-dev',
        'libxfixes-dev',
        'libxcursor-dev',
        'libfontconfig1-dev',
        'libjpeg-dev',
        'git',
    ]

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    # FLdigi binary name
    FLDIGI_BINARY = 'fldigi'

    # GitHub source repository
    FLDIGI_REPO = 'https://github.com/w1hkj/fldigi.git'

    def __init__(self):
        """
        Initialize installer with system detection.

        Detects available package managers and determines
        the best installation strategy.
        """
        self.plugin_dir = os.path.dirname(__file__)
        self.package_manager = self._detect_package_manager()
        self.fldigi_binary = shutil.which(self.FLDIGI_BINARY)

        print(
            f"[FLdigi] Package manager: "
            f"{self.package_manager or 'not found'}"
        )

    def _detect_package_manager(self):
        """
        Detect available system package manager.

        Returns:
            str: Package manager name or None
        """
        managers = [
            'apt-get', 'dnf', 'yum', 'pacman', 'zypper'
        ]

        for manager in managers:
            if shutil.which(manager):
                return manager

        return None

    def is_installed(self):
        """
        Check if FLdigi is installed and marker exists.

        Returns:
            bool: True if FLdigi is available
        """
        # Check marker file
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Verify binary is available
        return shutil.which(self.FLDIGI_BINARY) is not None

    def is_running(self):
        """
        Check if FLdigi process is currently running.

        Returns:
            bool: True if FLdigi is running
        """
        try:
            result = subprocess.run(
                ['pgrep', '-x', self.FLDIGI_BINARY],
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
            bool: True if all packages installed successfully
        """
        print("[FLdigi] Installing Python packages...")
        failed = []

        for package in self.REQUIRED_PACKAGES:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[FLdigi] ✓ {package}")
            except subprocess.CalledProcessError as e:
                print(f"[FLdigi] WARNING: {package} failed: {e}")
                failed.append(package)

        return len(failed) == 0

    def install_via_apt(self):
        """
        Install FLdigi via apt-get package manager.

        Also installs optional companion tools:
        - flarq: FLdigi ARQ file transfer companion
        - flmsg: FLdigi message forms companion

        Returns:
            bool: True if installation successful
        """
        print("[FLdigi] Installing via apt-get...")

        try:
            # Update package list
            print("[FLdigi] Updating package list...")
            subprocess.run(
                ['sudo', 'apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            # Install FLdigi and companion applications
            packages = ['fldigi']

            # Try to install optional companions
            # flarq is the ARQ file transfer companion
            # flmsg is the message forms companion
            optional_packages = ['flarq', 'flmsg', 'flamp']

            print(f"[FLdigi] Installing: {', '.join(packages)}")
            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y'] + packages,
                check=True,
                capture_output=True
            )

            # Install optional packages (non-fatal if fail)
            for pkg in optional_packages:
                try:
                    subprocess.run(
                        ['sudo', 'apt-get', 'install', '-y', pkg],
                        check=True,
                        capture_output=True
                    )
                    print(f"[FLdigi] ✓ Optional: {pkg}")
                except subprocess.CalledProcessError:
                    print(f"[FLdigi] INFO: {pkg} not available (optional)")

            print("[FLdigi] ✓ FLdigi installed via apt-get")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[FLdigi] ERROR: apt-get failed: {e}")
            return False

    def install_via_dnf(self):
        """
        Install FLdigi via dnf (Fedora/RHEL 8+).

        Returns:
            bool: True if installation successful
        """
        print("[FLdigi] Installing via dnf...")

        try:
            subprocess.run(
                ['sudo', 'dnf', 'install', '-y', 'fldigi'],
                check=True,
                capture_output=True
            )
            print("[FLdigi] ✓ FLdigi installed via dnf")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[FLdigi] ERROR: dnf failed: {e}")
            return False

    def install_via_pacman(self):
        """
        Install FLdigi via pacman (Arch Linux).

        Returns:
            bool: True if installation successful
        """
        print("[FLdigi] Installing via pacman...")

        try:
            subprocess.run(
                ['sudo', 'pacman', '-S', '--noconfirm', 'fldigi'],
                check=True,
                capture_output=True
            )
            print("[FLdigi] ✓ FLdigi installed via pacman")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[FLdigi] ERROR: pacman failed: {e}")
            return False

    def install_from_source(self):
        """
        Build and install FLdigi from GitHub source.

        Used as a fallback when package managers fail.
        Clones the repository, configures, and builds
        using autotools.

        Returns:
            bool: True if build and install successful
        """
        print("[FLdigi] Building from source...")

        build_dir = os.path.join(self.plugin_dir, '_fldigi_build')

        try:
            # Install build dependencies
            if shutil.which('apt-get'):
                print("[FLdigi] Installing build dependencies...")
                subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y'] +
                    self.BUILD_DEPS_APT,
                    check=True,
                    capture_output=True
                )

            # Clone repository
            print("[FLdigi] Cloning FLdigi repository...")
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

            subprocess.run(
                ['git', 'clone', '--depth', '1',
                 self.FLDIGI_REPO, build_dir],
                check=True,
                capture_output=True,
                timeout=120
            )

            # Bootstrap autotools
            print("[FLdigi] Running bootstrap...")
            subprocess.run(
                ['./bootstrap'],
                check=True,
                capture_output=True,
                cwd=build_dir
            )

            # Configure build
            print("[FLdigi] Configuring build...")
            subprocess.run(
                ['./configure', '--prefix=/usr/local'],
                check=True,
                capture_output=True,
                cwd=build_dir
            )

            # Build (use all available CPU cores)
            cpu_count = os.cpu_count() or 2
            print(f"[FLdigi] Building ({cpu_count} cores)...")
            subprocess.run(
                ['make', f'-j{cpu_count}'],
                check=True,
                capture_output=True,
                cwd=build_dir,
                timeout=600  # 10 minute timeout
            )

            # Install
            print("[FLdigi] Installing...")
            subprocess.run(
                ['sudo', 'make', 'install'],
                check=True,
                capture_output=True,
                cwd=build_dir
            )

            print("[FLdigi] ✓ FLdigi built and installed from source")
            return True

        except subprocess.TimeoutExpired:
            print("[FLdigi] ERROR: Build timed out")
            return False
        except subprocess.CalledProcessError as e:
            print(f"[FLdigi] ERROR: Build failed: {e}")
            return False
        except Exception as e:
            print(f"[FLdigi] ERROR: {e}")
            return False
        finally:
            # Clean up build directory
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

    def get_fldigi_version(self):
        """
        Get installed FLdigi version string.

        Returns:
            str: Version string or None
        """
        try:
            result = subprocess.run(
                [self.FLDIGI_BINARY, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse version from output
                for line in result.stdout.split('\n'):
                    if 'fldigi' in line.lower():
                        return line.strip()
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def write_install_marker(self, method, version=None):
        """
        Write installation marker with details.

        Args:
            method: Installation method used
            version: FLdigi version string
        """
        marker_data = {
            'installed': True,
            'method': method,
            'version': version,
            'platform': platform.platform(),
            'arch': platform.machine(),
            'python_version': sys.version,
            'fldigi_binary': shutil.which(self.FLDIGI_BINARY)
        }

        try:
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print("[FLdigi] ✓ Installation marker written")
        except Exception as e:
            print(f"[FLdigi] WARNING: Could not write marker: {e}")

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

        Checks for existing installation, installs Python
        packages and FLdigi via the best available method.

        Returns:
            bool: True if installation successful or pre-existing
        """
        # Already installed
        if self.is_installed():
            print("[FLdigi] ✓ Already installed")
            return True

        # FLdigi already in PATH but no marker
        if shutil.which(self.FLDIGI_BINARY):
            print("[FLdigi] FLdigi found in PATH")
            version = self.get_fldigi_version()
            self.write_install_marker('existing', version)
            return True

        print("[FLdigi] ==========================================")
        print("[FLdigi] Starting first-run installation")
        print("[FLdigi] ==========================================")

        # Step 1: Python packages
        print("\n[FLdigi] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: Install FLdigi
        print("\n[FLdigi] Step 2: Installing FLdigi...")
        success = False

        if self.package_manager == 'apt-get':
            success = self.install_via_apt()
        elif self.package_manager in ('dnf', 'yum'):
            success = self.install_via_dnf()
        elif self.package_manager == 'pacman':
            success = self.install_via_pacman()

        # Fall back to source build
        if not success:
            print("[FLdigi] Package install failed, trying source...")
            success = self.install_from_source()

        if not success:
            print("[FLdigi] ERROR: All installation methods failed")
            print("[FLdigi] Please install FLdigi manually:")
            print("[FLdigi] https://github.com/w1hkj/fldigi/")
            return False

        # Step 3: Update binary path
        self.fldigi_binary = shutil.which(self.FLDIGI_BINARY)

        # Step 4: Write marker
        version = self.get_fldigi_version()
        self.write_install_marker(
            self.package_manager or 'source',
            version
        )

        print("\n[FLdigi] ==========================================")
        print("[FLdigi] ✓ Installation complete!")
        if version:
            print(f"[FLdigi]   Version: {version}")
        print("[FLdigi] ==========================================\n")

        return True