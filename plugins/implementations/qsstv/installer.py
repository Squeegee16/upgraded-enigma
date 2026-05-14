"""
QSSTV Installer
================
Handles first-run installation of QSSTV and dependencies.

Docker Deployment Notes:
    QSSTV is a Qt5 GUI application that requires root to
    install. In Docker the runtime user (hamradio, UID 1000)
    cannot run apt-get or sudo.

    QSSTV MUST be installed in the Dockerfile at build time.
    Add to Dockerfile before USER hamradio:

        RUN apt-get update && apt-get install -y qsstv

    This installer detects Docker and logs clear instructions
    rather than attempting a doomed runtime install.

QSSTV Installation Methods (outside Docker):
    1. apt-get (Debian/Ubuntu)
    2. dnf (Fedora/RHEL)
    3. pacman + yay AUR (Arch Linux)
    4. Build from source (GitHub fallback)

Source: https://github.com/ON4QZ/QSSTV
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import traceback
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
                if (self.is_root or not self.sudo_available)
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
            if extra_data and isinstance(extra_data, dict):
                data.update(extra_data)
            try:
                marker_dir = os.path.dirname(path)
                if marker_dir:
                    os.makedirs(marker_dir, exist_ok=True)
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[QSSTV] Marker write error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class QSStvInstaller(BaseInstaller):
    """
    Manages QSSTV installation and verification.

    Extends BaseInstaller for Docker-aware handling.
    In Docker as non-root, system installs are skipped
    with clear Dockerfile instructions logged.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # QSSTV binary name
    QSSTV_BINARY = 'qsstv'

    # GitHub repository for source builds
    QSSTV_REPO = 'https://github.com/ON4QZ/QSSTV.git'

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
        'Pillow',
        'watchdog',
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
        Initialise installer with environment detection.
        """
        super().__init__()

        self._package_manager = (
            self._detect_package_manager()
        )
        self.qsstv_binary_path = shutil.which(
            self.QSSTV_BINARY
        )

        print(
            f"[QSSTV] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"sudo: {self.sudo_available} | "
            f"pkg mgr: {self._package_manager or 'none'}"
        )

    def _detect_package_manager(self):
        """
        Detect available system package manager.

        Returns:
            str: Package manager name or None
        """
        for mgr in ['apt-get', 'dnf', 'yum', 'pacman']:
            if shutil.which(mgr):
                return mgr
        return None

    def _run_system_command(self, cmd, timeout=300):
        """
        Run a system command safely.

        Handles FileNotFoundError (missing sudo or binary)
        without raising an unhandled exception.

        Args:
            cmd: Command list to execute
            timeout: Maximum seconds to wait

        Returns:
            tuple: (success: bool, stdout: str, stderr: str)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return (
                result.returncode == 0,
                result.stdout or '',
                result.stderr or ''
            )
        except FileNotFoundError as e:
            return (
                False, '',
                f"Command not found: {cmd[0]} — {e}"
            )
        except subprocess.TimeoutExpired:
            return False, '', f"Timed out after {timeout}s"
        except Exception as e:
            return False, '', str(e)

    def is_installed(self):
        """
        Check if QSSTV is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False
        return shutil.which(self.QSSTV_BINARY) is not None

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages available
        """
        print("[QSSTV] Checking Python packages...")
        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )
        if failed and self.in_docker:
            print(
                f"[QSSTV] INFO: Add to requirements.txt: "
                f"{', '.join(failed)}"
            )
        return len(failed) == 0

    def _install_via_apt(self):
        """
        Install QSSTV via apt-get.

        Uses self._sudo prefix (empty for root, ['sudo']
        for non-root with sudo, [] for Docker non-root).

        Returns:
            bool: True if installation successful
        """
        print("[QSSTV] Installing via apt-get...")

        if not shutil.which('apt-get'):
            print("[QSSTV] apt-get not available")
            return False

        if self.in_docker and not self.is_root:
            print(
                "[QSSTV] INFO: Cannot apt-get in Docker "
                "as non-root. Add to Dockerfile:"
            )
            print(
                "[QSSTV] INFO:   RUN apt-get update && "
                "apt-get install -y qsstv"
            )
            return False

        # Update package list
        ok, _, stderr = self._run_system_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[QSSTV] apt-get update failed: "
                f"{stderr[:150]}"
            )
            return False

        # Install QSSTV
        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'qsstv'
            ],
            timeout=300
        )

        if ok:
            print("[QSSTV] ✓ Installed via apt-get")
            return True

        print(f"[QSSTV] apt-get failed: {stderr[:200]}")
        return False

    def _install_via_dnf(self):
        """
        Install QSSTV via dnf (Fedora/RHEL).

        Returns:
            bool: True if installation successful
        """
        print("[QSSTV] Installing via dnf...")

        if not shutil.which('dnf'):
            return False

        if self.in_docker and not self.is_root:
            print(
                "[QSSTV] INFO: Add to Dockerfile: "
                "RUN dnf install -y qsstv"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + ['dnf', 'install', '-y', 'qsstv'],
            timeout=300
        )

        if ok:
            print("[QSSTV] ✓ Installed via dnf")
            return True

        print(f"[QSSTV] dnf failed: {stderr[:200]}")
        return False

    def _install_via_pacman(self):
        """
        Install QSSTV via pacman (Arch Linux).

        Tries AUR via yay if direct pacman fails.

        Returns:
            bool: True if installation successful
        """
        print("[QSSTV] Installing via pacman...")

        if not shutil.which('pacman'):
            return False

        if self.in_docker and not self.is_root:
            print(
                "[QSSTV] INFO: Add to Dockerfile: "
                "RUN pacman -S --noconfirm qsstv"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'pacman', '-S', '--noconfirm', 'qsstv'
            ],
            timeout=300
        )

        if ok:
            print("[QSSTV] ✓ Installed via pacman")
            return True

        if shutil.which('yay'):
            ok, _, stderr = self._run_system_command(
                ['yay', '-S', '--noconfirm', 'qsstv'],
                timeout=300
            )
            if ok:
                print("[QSSTV] ✓ Installed via yay (AUR)")
                return True

        print(f"[QSSTV] pacman failed: {stderr[:200]}")
        return False

    def build_from_source(self):
        """
        Build and install QSSTV from GitHub source.

        Used as fallback when package managers fail.
        Not available in Docker as non-root.

        Returns:
            bool: True if build and install successful
        """
        if self.in_docker and not self.is_root:
            print(
                "[QSSTV] INFO: Cannot build from source "
                "in Docker as non-root."
            )
            print(
                "[QSSTV] INFO: Add to Dockerfile: "
                "RUN apt-get install -y qsstv"
            )
            return False

        print("[QSSTV] Building from source...")
        build_dir = os.path.join(
            os.path.expanduser('~'), '_qsstv_build'
        )

        try:
            if shutil.which('apt-get') and \
                    (self.is_root or self.sudo_available):
                ok, _, _ = self._run_system_command(
                    self._sudo + [
                        'apt-get', 'install', '-y'
                    ] + self.BUILD_DEPS_APT,
                    timeout=300
                )

            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

            ok, _, stderr = self._run_system_command(
                [
                    'git', 'clone', '--depth', '1',
                    self.QSSTV_REPO, build_dir
                ],
                timeout=120
            )
            if not ok:
                print(
                    f"[QSSTV] Clone failed: {stderr}"
                )
                return False

            cmake_dir = os.path.join(build_dir, 'build')
            os.makedirs(cmake_dir, exist_ok=True)

            ok, _, stderr = self._run_system_command(
                [
                    'cmake', '..',
                    '-DCMAKE_INSTALL_PREFIX=/usr/local'
                ],
                timeout=120
            )
            if not ok:
                print(
                    f"[QSSTV] cmake failed: {stderr[:200]}"
                )
                return False

            cpu_count = os.cpu_count() or 2
            ok, _, stderr = self._run_system_command(
                ['make', f'-j{cpu_count}'],
                timeout=600
            )
            if not ok:
                print(
                    f"[QSSTV] make failed: {stderr[:200]}"
                )
                return False

            ok, _, stderr = self._run_system_command(
                self._sudo + ['make', 'install'],
                timeout=120
            )
            if not ok:
                print(
                    f"[QSSTV] install failed: "
                    f"{stderr[:200]}"
                )
                return False

            print("[QSSTV] ✓ Built from source")
            return True

        except Exception as e:
            print(f"[QSSTV] Source build error: {e}")
            traceback.print_exc()
            return False

        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(
                    build_dir, ignore_errors=True
                )

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
                timeout=10
            )
            output = (result.stdout + result.stderr).strip()
            return output[:50] if output else 'installed'
        except Exception:
            return 'installed'

    def write_install_marker(self, method, version=None):
        """Write installation marker."""
        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': method,
                'version': version,
                'binary': shutil.which(self.QSSTV_BINARY),
                'platform': platform.platform(),
            }
        )

    def get_install_info(self):
        """Read installation marker."""
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Execute the complete installation process.

        In Docker as non-root: logs Dockerfile
        instructions and returns False.

        Outside Docker: tries apt-get, dnf, pacman,
        then source build in order.

        Returns:
            bool: True if installed or already present
        """
        if self.is_installed():
            print("[QSSTV] ✓ Already installed")
            return True

        if shutil.which(self.QSSTV_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[QSSTV] ✓ Found in PATH")
            return True

        print("[QSSTV] ==========================================")
        print("[QSSTV] Starting first-run installation")
        print("[QSSTV] ==========================================")

        # Docker non-root: cannot install system packages
        if self.in_docker and not self.is_root:
            print(
                "\n[QSSTV] ======================================"
            )
            print("[QSSTV] DOCKER INSTALLATION REQUIRED")
            print(
                "[QSSTV] ======================================"
            )
            print(
                "[QSSTV] Add to Dockerfile and rebuild:"
            )
            print()
            print(
                "[QSSTV]   RUN apt-get update && \\"
            )
            print(
                "[QSSTV]       apt-get install -y qsstv && \\"
            )
            print(
                "[QSSTV]       rm -rf /var/lib/apt/lists/*"
            )
            print()
            print(
                "[QSSTV]   docker compose build --no-cache"
            )
            print(
                "[QSSTV] ======================================"
            )
            return False

        # Step 1: Python packages
        print("\n[QSSTV] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: Install QSSTV
        print(
            f"\n[QSSTV] Step 2: Installing QSSTV "
            f"(pkg mgr: "
            f"{self._package_manager or 'none'})..."
        )
        success = False

        if self._package_manager == 'apt-get':
            success = self._install_via_apt()
        elif self._package_manager in ('dnf', 'yum'):
            success = self._install_via_dnf()
        elif self._package_manager == 'pacman':
            success = self._install_via_pacman()

        if not success:
            print(
                "[QSSTV] Package manager failed, "
                "trying source build..."
            )
            success = self.build_from_source()

        if not success:
            print("[QSSTV] ERROR: Installation failed")
            return False

        version = self.get_version()
        self.write_install_marker(
            self._package_manager or 'source',
            version
        )

        print("\n[QSSTV] ==========================================")
        print("[QSSTV] ✓ Installation complete!")
        if version:
            print(f"[QSSTV]   Version: {version}")
        print("[QSSTV] ==========================================\n")

        return True
