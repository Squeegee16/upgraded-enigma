"""
SatDump Installer
==================
Handles first-run installation of SatDump and dependencies.

SatDump Installation Methods:
    1. apt-get via official PPA (Debian/Ubuntu)
       Adds the SatDump PPA and installs via apt
    2. Flatpak (Universal Linux)
       Installs from Flathub
    3. Build from source (GitHub)
       Clones, configures with cmake, and builds
    4. AppImage (Direct download)
       Downloads pre-built AppImage

Python Dependencies:
    - requests: HTTP client for API calls
    - psutil: Process management and monitoring
    - Pillow: Image processing for satellite images
    - watchdog: File system monitoring for products
    - ephem: Satellite orbit calculations (optional)
    - pyorbital: NOAA satellite pass prediction (optional)

System Dependencies:
    - cmake, build-essential (for source builds)
    - libfftw3-dev (FFT library)
    - libnng-dev (Messaging library)
    - libpng-dev, libjpeg-dev (Image libraries)
    - Qt5 or Qt6 (GUI framework)
    - Various SDR libraries

Source: https://github.com/SatDump/SatDump
Documentation: https://docs.satdump.org/building.html
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import urllib.request
from pathlib import Path


class SatDumpInstaller:
    """
    Manages SatDump installation and verification.

    Supports multiple installation methods with automatic
    fallback. Tracks installation state via a JSON marker
    file to prevent repeated installation.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # SatDump binary names
    SATDUMP_BINARY = 'satdump'
    SATDUMP_UI_BINARY = 'satdump-ui'

    # SatDump GitHub
    SATDUMP_REPO = 'https://github.com/SatDump/SatDump.git'

    # Official apt repository
    SATDUMP_APT_REPO = 'https://downloads.satdump.org'

    # Flathub app ID
    SATDUMP_FLATPAK_ID = 'org.satdump.SatDump'

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
        'Pillow',
        'watchdog',
    ]

    # Optional Python packages for satellite tracking
    OPTIONAL_PACKAGES = [
        'ephem',
        'pyorbital',
    ]

    # Build dependencies for apt-based systems
    BUILD_DEPS_APT = [
        'build-essential',
        'cmake',
        'git',
        'pkgconf',
        'libfftw3-dev',
        'libnng-dev',
        'libjpeg-dev',
        'libpng-dev',
        'libtiff-dev',
        'libglfw3-dev',
        'libvolk-dev',
        'libnng-dev',
        'libcurl4-openssl-dev',
        'libhdf5-dev',
        'libeckit-dev',
        'libaec-dev',
        'python3-dev',
        'libzstd-dev',
        # SDR dependencies
        'librtlsdr-dev',
        'libairspy-dev',
        'libhackrf-dev',
        'libsdrplay-dev',
    ]

    def __init__(self):
        """
        Initialize installer with system detection.

        Detects package manager, architecture, and
        determines the best installation strategy.
        """
        self.plugin_dir = os.path.dirname(__file__)
        self.package_manager = self._detect_package_manager()
        self.arch = platform.machine()
        self.satdump_binary_path = shutil.which(
            self.SATDUMP_BINARY
        )

        print(
            f"[SatDump] Package manager: "
            f"{self.package_manager or 'not found'}"
        )
        print(f"[SatDump] Architecture: {self.arch}")

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
        Check if SatDump is installed and marker exists.

        Returns:
            bool: True if SatDump binary is available
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        return (
            shutil.which(self.SATDUMP_BINARY) is not None or
            shutil.which(self.SATDUMP_UI_BINARY) is not None
        )

    def is_running(self):
        """
        Check if SatDump is currently running.

        Returns:
            bool: True if any SatDump process is active
        """
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'satdump'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def install_python_packages(self):
        """
        Install required and optional Python packages.

        Returns:
            bool: True if required packages installed
        """
        print("[SatDump] Installing Python packages...")
        failed_required = []

        # Install required packages
        for package in self.REQUIRED_PACKAGES:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[SatDump] ✓ {package}")
            except subprocess.CalledProcessError as e:
                print(f"[SatDump] WARNING: {package} failed: {e}")
                failed_required.append(package)

        # Install optional packages (non-fatal)
        for package in self.OPTIONAL_PACKAGES:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[SatDump] ✓ Optional: {package}")
            except subprocess.CalledProcessError:
                print(
                    f"[SatDump] INFO: {package} not installed "
                    f"(optional)"
                )

        return len(failed_required) == 0

    def install_via_apt_ppa(self):
        """
        Install SatDump via official apt PPA.

        Adds the SatDump repository key and PPA,
        then installs via apt-get.

        Returns:
            bool: True if installation successful
        """
        print("[SatDump] Installing via apt PPA...")

        try:
            # Install prerequisites
            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y',
                 'curl', 'apt-transport-https', 'gnupg'],
                check=True,
                capture_output=True
            )

            # Add SatDump repository key
            print("[SatDump] Adding repository key...")
            key_result = subprocess.run(
                ['curl', '-fsSL',
                 f'{self.SATDUMP_APT_REPO}/key.gpg'],
                capture_output=True
            )

            if key_result.returncode == 0:
                subprocess.run(
                    ['sudo', 'tee',
                     '/usr/share/keyrings/satdump.gpg'],
                    input=key_result.stdout,
                    capture_output=True
                )

            # Detect Ubuntu/Debian version
            try:
                distro_result = subprocess.run(
                    ['lsb_release', '-cs'],
                    capture_output=True,
                    text=True
                )
                distro = distro_result.stdout.strip()
            except Exception:
                distro = 'focal'  # Default to Ubuntu 20.04

            # Add repository
            print("[SatDump] Adding repository...")
            repo_line = (
                f"deb [arch=amd64 "
                f"signed-by=/usr/share/keyrings/satdump.gpg] "
                f"{self.SATDUMP_APT_REPO}/apt "
                f"{distro} main\n"
            )

            with open('/tmp/satdump.list', 'w') as f:
                f.write(repo_line)

            subprocess.run(
                ['sudo', 'cp', '/tmp/satdump.list',
                 '/etc/apt/sources.list.d/satdump.list'],
                check=True,
                capture_output=True
            )

            # Update and install
            print("[SatDump] Updating package list...")
            subprocess.run(
                ['sudo', 'apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            print("[SatDump] Installing satdump package...")
            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y', 'satdump'],
                check=True,
                capture_output=True
            )

            print("[SatDump] ✓ Installed via apt PPA")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[SatDump] apt PPA failed: {e}")
            return False

    def install_via_flatpak(self):
        """
        Install SatDump via Flatpak from Flathub.

        Creates a wrapper script so 'satdump' works
        from the command line after Flatpak install.

        Returns:
            bool: True if installation successful
        """
        print("[SatDump] Installing via Flatpak...")

        if not shutil.which('flatpak'):
            print("[SatDump] Flatpak not available")
            return False

        try:
            # Add Flathub repository
            subprocess.run(
                ['flatpak', 'remote-add', '--if-not-exists',
                 'flathub',
                 'https://flathub.org/repo/flathub.flatpakrepo'],
                check=True,
                capture_output=True
            )

            # Install SatDump
            subprocess.run(
                ['flatpak', 'install', '-y', 'flathub',
                 self.SATDUMP_FLATPAK_ID],
                check=True,
                capture_output=True,
                timeout=300
            )

            # Create CLI wrapper for satdump binary
            wrapper_dir = os.path.expanduser('~/.local/bin')
            os.makedirs(wrapper_dir, exist_ok=True)

            # CLI wrapper
            wrapper_path = os.path.join(wrapper_dir, 'satdump')
            with open(wrapper_path, 'w') as f:
                f.write(
                    '#!/bin/bash\n'
                    f'exec flatpak run '
                    f'{self.SATDUMP_FLATPAK_ID} "$@"\n'
                )
            os.chmod(wrapper_path, 0o755)

            print("[SatDump] ✓ Installed via Flatpak")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[SatDump] Flatpak failed: {e}")
            return self.build_from_source()

    def build_from_source(self):
        """
        Build SatDump from GitHub source.

        Clones the repository, installs build dependencies,
        configures with cmake, and installs.

        This is the most compatible method but requires
        significant disk space and build time.

        Returns:
            bool: True if build successful
        """
        print("[SatDump] Building from source...")
        build_dir = os.path.join(
            self.plugin_dir, '_satdump_build'
        )

        try:
            # Install build dependencies
            if shutil.which('apt-get'):
                print("[SatDump] Installing build deps...")
                subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y'] +
                    self.BUILD_DEPS_APT,
                    check=True,
                    capture_output=True
                )

            # Clean previous builds
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

            # Clone repository
            print("[SatDump] Cloning repository...")
            subprocess.run(
                ['git', 'clone', '--depth', '1',
                 '--recurse-submodules',
                 self.SATDUMP_REPO, build_dir],
                check=True,
                capture_output=True,
                timeout=180
            )

            # Create cmake build directory
            cmake_dir = os.path.join(build_dir, 'build')
            os.makedirs(cmake_dir, exist_ok=True)

            # Configure with cmake
            print("[SatDump] Configuring with cmake...")
            cmake_args = [
                'cmake', '..',
                '-DCMAKE_BUILD_TYPE=Release',
                '-DCMAKE_INSTALL_PREFIX=/usr/local',
                '-DBUILD_GUI=OFF',   # CLI only for server
                '-DPLUGIN_ALL=ON',  # Enable all plugins
                '-DPORTABLE_INSTALL=OFF',
            ]

            subprocess.run(
                cmake_args,
                check=True,
                capture_output=True,
                cwd=cmake_dir
            )

            # Build
            cpu_count = os.cpu_count() or 2
            print(f"[SatDump] Building ({cpu_count} cores)...")
            subprocess.run(
                ['make', f'-j{cpu_count}'],
                check=True,
                capture_output=True,
                cwd=cmake_dir,
                timeout=1800  # 30 minutes for large build
            )

            # Install
            print("[SatDump] Installing...")
            subprocess.run(
                ['sudo', 'make', 'install'],
                check=True,
                capture_output=True,
                cwd=cmake_dir
            )

            # Update shared library cache
            subprocess.run(
                ['sudo', 'ldconfig'],
                capture_output=True
            )

            print("[SatDump] ✓ Built and installed from source")
            return True

        except subprocess.TimeoutExpired:
            print("[SatDump] ERROR: Build timed out")
            return False
        except subprocess.CalledProcessError as e:
            print(f"[SatDump] ERROR: Build failed: {e}")
            return False
        except Exception as e:
            print(f"[SatDump] ERROR: {e}")
            return False
        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

    def get_version(self):
        """
        Get installed SatDump version.

        Returns:
            str: Version string or None
        """
        binary = shutil.which(self.SATDUMP_BINARY)
        if not binary:
            return None

        try:
            result = subprocess.run(
                [binary, '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout + result.stderr
            # Parse version from output
            for line in output.split('\n'):
                if 'satdump' in line.lower() or \
                        line.strip().startswith(('1.', '0.')):
                    return line.strip()
            return output.strip()[:50] or 'installed'
        except Exception:
            return 'installed'

    def write_install_marker(self, method, version=None):
        """
        Write installation marker with metadata.

        Args:
            method: Installation method used
            version: SatDump version string
        """
        marker_data = {
            'installed': True,
            'method': method,
            'version': version,
            'platform': platform.platform(),
            'arch': self.arch,
            'satdump_binary': shutil.which(self.SATDUMP_BINARY),
            'satdump_ui': shutil.which(self.SATDUMP_UI_BINARY)
        }

        try:
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print("[SatDump] ✓ Installation marker written")
        except Exception as e:
            print(f"[SatDump] WARNING: Marker write failed: {e}")

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
            print("[SatDump] ✓ Already installed")
            return True

        # Check if already in PATH
        if shutil.which(self.SATDUMP_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[SatDump] ✓ Found in PATH")
            return True

        print("[SatDump] ==========================================")
        print("[SatDump] Starting first-run installation")
        print("[SatDump] ==========================================")

        # Step 1: Python packages
        print("\n[SatDump] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: SatDump
        print("\n[SatDump] Step 2: Installing SatDump...")
        success = False

        if self.package_manager == 'apt-get':
            # Try PPA first, fall back to source
            success = self.install_via_apt_ppa()
            if not success:
                print("[SatDump] PPA failed, trying Flatpak...")
                success = self.install_via_flatpak()
        elif self.package_manager in ('dnf', 'yum'):
            success = self.install_via_flatpak()
        elif self.package_manager == 'pacman':
            # Try AUR
            if shutil.which('yay'):
                try:
                    subprocess.run(
                        ['yay', '-S', '--noconfirm', 'satdump'],
                        check=True,
                        capture_output=True
                    )
                    success = True
                    print("[SatDump] ✓ Installed via yay (AUR)")
                except Exception:
                    success = self.install_via_flatpak()
            else:
                success = self.install_via_flatpak()
        else:
            success = self.install_via_flatpak()

        if not success:
            print("[SatDump] ERROR: All installation methods failed")
            print("[SatDump] Manual install:")
            print("[SatDump] https://docs.satdump.org/building.html")
            return False

        # Update binary path
        self.satdump_binary_path = shutil.which(self.SATDUMP_BINARY)

        # Write marker
        version = self.get_version()
        self.write_install_marker(
            self.package_manager or 'flatpak',
            version
        )

        print("\n[SatDump] ==========================================")
        print("[SatDump] ✓ Installation complete!")
        if version:
            print(f"[SatDump]   Version: {version}")
        print("[SatDump] ==========================================\n")

        return True