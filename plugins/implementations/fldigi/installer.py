"""
FLdigi Installer
=================
Handles first-run installation of FLdigi and dependencies.

Docker Deployment Notes:
    FLdigi is a system application that requires root to
    install via apt-get. In Docker, the runtime user
    (hamradio, UID 1000) cannot run apt-get.

    FLdigi MUST be installed in the Dockerfile at build
    time. This installer detects Docker and informs the
    user rather than attempting a doomed installation.

    Add to Dockerfile:
        RUN apt-get update && apt-get install -y fldigi

    This installer handles:
        - Docker detection (skip system installs)
        - Non-Docker: apt/dnf/pacman/source installation
        - Python package availability checks

FLdigi Installation Methods (outside Docker):
    1. apt-get (Debian/Ubuntu) — fldigi package
    2. dnf (Fedora/RHEL)
    3. pacman (Arch Linux)
    4. Build from source (GitHub fallback)

Source: https://github.com/w1hkj/fldigi/
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
                print(f"[FLdigi] Marker write error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class FldigiInstaller(BaseInstaller):
    """
    Manages FLdigi installation and dependency verification.

    Extends BaseInstaller to handle Docker environments
    where apt-get cannot be run at runtime. In Docker,
    FLdigi must be pre-installed in the image.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # FLdigi binary name
    FLDIGI_BINARY = 'fldigi'

    # GitHub repository for source builds
    FLDIGI_REPO = 'https://github.com/w1hkj/fldigi.git'

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    # apt build dependencies for source compilation
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

    def __init__(self):
        """
        Initialise installer with environment detection.
        """
        super().__init__()

        # Detect package manager
        self._package_manager = (
            self._detect_package_manager()
        )
        self.fldigi_binary = shutil.which(self.FLDIGI_BINARY)

        print(
            f"[FLdigi] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"sudo: {self.sudo_available} | "
            f"pkg mgr: {self._package_manager or 'none'} | "
            f"fldigi: {self.fldigi_binary or 'not found'}"
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

        Handles FileNotFoundError (e.g. missing sudo)
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
            stdout = result.stdout or ''
            stderr = result.stderr or ''
            return result.returncode == 0, stdout, stderr

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
        Check if FLdigi is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False
        return shutil.which(self.FLDIGI_BINARY) is not None

    def install_python_packages(self):
        """
        Install required Python packages.

        In Docker, only checks availability.
        Outside Docker, attempts pip install.

        Returns:
            bool: True if all packages available
        """
        print("[FLdigi] Checking Python packages...")
        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )

        if failed and self.in_docker:
            print(
                f"[FLdigi] INFO: Add to requirements.txt: "
                f"{', '.join(failed)}"
            )
        elif failed:
            print(
                f"[FLdigi] WARNING: Failed: {failed}"
            )

        return len(failed) == 0

    def install_via_apt(self):
        """
        Install FLdigi via apt-get.

        Uses self._sudo prefix which is correctly set
        based on whether we are root, have sudo, or
        are in a Docker container.

        In Docker as non-root without sudo:
            self._sudo = [] and self.is_root = False
            apt-get will fail with permission denied
            The correct fix is to add fldigi to the
            Dockerfile RUN apt-get block.

        Returns:
            bool: True if installation successful
        """
        print("[FLdigi] Installing via apt-get...")

        if not shutil.which('apt-get'):
            print("[FLdigi] apt-get not available")
            return False

        # In Docker as non-root, we cannot run apt-get
        if self.in_docker and not self.is_root:
            print(
                "[FLdigi] INFO: Cannot apt-get in Docker "
                "as non-root user."
            )
            print(
                "[FLdigi] INFO: Add fldigi to the "
                "Dockerfile and rebuild:"
            )
            print(
                "[FLdigi] INFO:   RUN apt-get update && "
                "apt-get install -y fldigi"
            )
            print(
                "[FLdigi] INFO:   docker compose build "
                "--no-cache"
            )
            return False

        # Outside Docker or running as root:
        # attempt installation with correct prefix

        # Step 1: Update package list
        print("[FLdigi] Updating package list...")
        ok, _, stderr = self._run_system_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[FLdigi] apt-get update failed: "
                f"{stderr[:150]}"
            )
            return False

        # Step 2: Install fldigi
        print("[FLdigi] Installing fldigi package...")
        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'fldigi'
            ],
            timeout=300
        )

        if ok:
            print("[FLdigi] ✓ Installed via apt-get")
            return True

        print(
            f"[FLdigi] apt-get install failed: "
            f"{stderr[:200]}"
        )
        return False

    def install_via_dnf(self):
        """
        Install FLdigi via dnf (Fedora/RHEL).

        Returns:
            bool: True if installation successful
        """
        print("[FLdigi] Installing via dnf...")

        if not shutil.which('dnf'):
            return False

        if self.in_docker and not self.is_root:
            print(
                "[FLdigi] INFO: Add to Dockerfile: "
                "RUN dnf install -y fldigi"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + ['dnf', 'install', '-y', 'fldigi'],
            timeout=300
        )

        if ok:
            print("[FLdigi] ✓ Installed via dnf")
            return True

        print(f"[FLdigi] dnf failed: {stderr[:200]}")
        return False

    def install_via_pacman(self):
        """
        Install FLdigi via pacman (Arch Linux).

        Returns:
            bool: True if installation successful
        """
        print("[FLdigi] Installing via pacman...")

        if not shutil.which('pacman'):
            return False

        if self.in_docker and not self.is_root:
            print(
                "[FLdigi] INFO: Add to Dockerfile: "
                "RUN pacman -S --noconfirm fldigi"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'pacman', '-S', '--noconfirm', 'fldigi'
            ],
            timeout=300
        )

        if ok:
            print("[FLdigi] ✓ Installed via pacman")
            return True

        print(
            f"[FLdigi] pacman failed: {stderr[:200]}"
        )
        return False

    def build_from_source(self):
        """
        Build and install FLdigi from GitHub source.

        Used as a fallback when package managers fail.
        Requires autotools build chain and development
        libraries.

        Returns:
            bool: True if build and install successful
        """
        if self.in_docker and not self.is_root:
            print(
                "[FLdigi] INFO: Cannot build from source "
                "in Docker as non-root."
            )
            print(
                "[FLdigi] INFO: Add to Dockerfile:"
            )
            print(
                "[FLdigi] INFO:   # Install FLdigi build deps"
            )
            print(
                "[FLdigi] INFO:   RUN apt-get install -y "
                "fldigi"
            )
            return False

        print("[FLdigi] Building from source...")
        build_dir = os.path.join(
            self._get_temp_dir(), 'fldigi_build'
        )

        try:
            if self.is_root or self.sudo_available:
                if shutil.which('apt-get'):
                    print(
                        "[FLdigi] Installing build deps..."
                    )
                    self._run_system_command(
                        self._sudo + [
                            'apt-get', 'install', '-y'
                        ] + self.BUILD_DEPS_APT,
                        timeout=300
                    )

            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)

            print("[FLdigi] Cloning repository...")
            ok, _, stderr = self._run_system_command(
                [
                    'git', 'clone', '--depth', '1',
                    self.FLDIGI_REPO, build_dir
                ],
                timeout=120
            )

            if not ok:
                print(
                    f"[FLdigi] Clone failed: {stderr}"
                )
                return False

            print("[FLdigi] Running bootstrap...")
            ok, _, stderr = self._run_system_command(
                ['./bootstrap'],
                timeout=60
            )
            if not ok:
                ok, _, stderr = self._run_system_command(
                    ['autoreconf', '-fi'],
                    timeout=60
                )

            print("[FLdigi] Configuring...")
            ok, _, stderr = self._run_system_command(
                ['./configure', '--prefix=/usr/local'],
                timeout=120
            )
            if not ok:
                print(
                    f"[FLdigi] Configure failed: "
                    f"{stderr[:200]}"
                )
                return False

            cpu_count = os.cpu_count() or 2
            print(
                f"[FLdigi] Building ({cpu_count} cores)..."
            )
            ok, _, stderr = self._run_system_command(
                ['make', f'-j{cpu_count}'],
                timeout=600
            )
            if not ok:
                print(
                    f"[FLdigi] make failed: {stderr[:200]}"
                )
                return False

            print("[FLdigi] Installing...")
            ok, _, stderr = self._run_system_command(
                self._sudo + ['make', 'install'],
                timeout=120
            )
            if not ok:
                print(
                    f"[FLdigi] make install failed: "
                    f"{stderr[:200]}"
                )
                return False

            print("[FLdigi] ✓ Built from source")
            return True

        except Exception as e:
            print(f"[FLdigi] Source build error: {e}")
            traceback.print_exc()
            return False

        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

    def _get_temp_dir(self):
        """
        Get a writable temp directory.

        Returns:
            str: Path to a writable temp directory
        """
        import tempfile
        return tempfile.gettempdir()

    def get_version(self):
        """
        Get installed FLdigi version.

        Returns:
            str: Version string or None
        """
        binary = shutil.which(self.FLDIGI_BINARY)
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
            for line in output.splitlines():
                if 'fldigi' in line.lower():
                    return line.strip()
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
                'binary': shutil.which(self.FLDIGI_BINARY),
                'platform': platform.platform(),
            }
        )

    def get_install_info(self):
        """Read installation marker."""
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Execute the complete installation process.

        Docker behaviour:
            In Docker as non-root, system package installs
            are not possible. This method detects Docker,
            logs clear instructions, and returns False
            so the plugin UI shows an appropriate message.

            To fix: add fldigi to the Dockerfile and rebuild.

        Non-Docker behaviour:
            Tries apt-get, dnf, pacman, then source build.

        Returns:
            bool: True if installed or already present
        """
        # Already installed
        if self.is_installed():
            print("[FLdigi] ✓ Already installed")
            return True

        # FLdigi already in PATH but no marker
        if shutil.which(self.FLDIGI_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print(
                f"[FLdigi] ✓ Found in PATH: "
                f"{shutil.which(self.FLDIGI_BINARY)}"
            )
            return True

        print("[FLdigi] ==========================================")
        print("[FLdigi] Starting first-run installation")
        print("[FLdigi] ==========================================")

        # -------------------------------------------------------
        # Docker non-root: cannot install system packages
        # -------------------------------------------------------
        if self.in_docker and not self.is_root:
            print(
                "\n[FLdigi] =========================================="
            )
            print(
                "[FLdigi] DOCKER INSTALLATION REQUIRED"
            )
            print(
                "[FLdigi] =========================================="
            )
            print(
                "[FLdigi] FLdigi cannot be installed at "
                "runtime in Docker."
            )
            print(
                "[FLdigi] Add the following to your "
                "Dockerfile and rebuild:"
            )
            print()
            print(
                "[FLdigi]   # Install FLdigi digital modes"
            )
            print(
                "[FLdigi]   RUN apt-get update && \\"
            )
            print(
                "[FLdigi]       apt-get install -y \\"
            )
            print(
                "[FLdigi]       fldigi \\"
            )
            print(
                "[FLdigi]       flmsg \\"
            )
            print(
                "[FLdigi]       flarq \\"
            )
            print(
                "[FLdigi]       && rm -rf /var/lib/apt/lists/*"
            )
            print()
            print(
                "[FLdigi]   Then rebuild:"
            )
            print(
                "[FLdigi]   docker compose build --no-cache"
            )
            print(
                "[FLdigi] =========================================="
            )
            return False

        # -------------------------------------------------------
        # Step 1: Python packages
        # -------------------------------------------------------
        print("\n[FLdigi] Step 1: Python packages...")
        self.install_python_packages()

        # -------------------------------------------------------
        # Step 2: Install FLdigi
        # -------------------------------------------------------
        print(
            f"\n[FLdigi] Step 2: Installing FLdigi "
            f"(pkg mgr: {self._package_manager or 'none'})..."
        )
        success = False

        if self._package_manager == 'apt-get':
            success = self.install_via_apt()
        elif self._package_manager in ('dnf', 'yum'):
            success = self.install_via_dnf()
        elif self._package_manager == 'pacman':
            success = self.install_via_pacman()

        if not success:
            print(
                "[FLdigi] Package manager install failed, "
                "trying source build..."
            )
            success = self.build_from_source()

        if not success:
            print(
                "\n[FLdigi] ERROR: All installation methods "
                "failed"
            )
            return False

        # Write marker
        version = self.get_version()
        self.write_install_marker(
            self._package_manager or 'source',
            version
        )

        print("\n[FLdigi] ==========================================")
        print("[FLdigi] ✓ Installation complete!")
        if version:
            print(f"[FLdigi]   Version: {version}")
        print("[FLdigi] ==========================================\n")

        return True
