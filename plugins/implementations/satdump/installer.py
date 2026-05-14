"""
SatDump Installer
==================
Handles first-run installation of SatDump and dependencies.

Docker Deployment Notes:
    SatDump requires root to install. In Docker the runtime
    user (hamradio, UID 1000) cannot run apt-get or sudo.

    SatDump MUST be installed in the Dockerfile at build time.
    Add to Dockerfile before USER hamradio:

        # Add SatDump apt repository and install
        RUN apt-get update && \\
            curl -fsSL https://downloads.satdump.org/key.gpg \\
                | apt-key add - && \\
            echo "deb https://downloads.satdump.org/apt \\
                stable main" \\
                > /etc/apt/sources.list.d/satdump.list && \\
            apt-get update && \\
            apt-get install -y satdump && \\
            rm -rf /var/lib/apt/lists/*

    This installer detects Docker and logs clear instructions
    rather than attempting a doomed runtime install.

SatDump Installation Methods (outside Docker):
    1. apt-get via official PPA (Debian/Ubuntu)
    2. Flatpak from Flathub
    3. AUR via yay (Arch Linux)
    4. Build from source (GitHub fallback)

Source: https://github.com/SatDump/SatDump
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
                print(
                    f"[SatDump] Marker write error: {e}"
                )

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class SatDumpInstaller(BaseInstaller):
    """
    Manages SatDump installation and verification.

    Extends BaseInstaller for Docker-aware handling.
    In Docker as non-root, system installs are skipped
    with clear Dockerfile instructions logged.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # SatDump binary names
    SATDUMP_BINARY = 'satdump'
    SATDUMP_UI_BINARY = 'satdump-ui'

    # SatDump GitHub repository
    SATDUMP_REPO = 'https://github.com/SatDump/SatDump.git'

    # Official apt repository
    SATDUMP_APT_REPO = 'https://downloads.satdump.org'

    # Flathub application ID
    FLATPAK_APP_ID = 'org.satdump.SatDump'

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
        'Pillow',
        'watchdog',
    ]

    # Optional Python packages
    OPTIONAL_PACKAGES = [
        'ephem',
        'pyorbital',
    ]

    # Build dependencies for source compilation
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
        'libcurl4-openssl-dev',
        'libhdf5-dev',
        'libzstd-dev',
        'librtlsdr-dev',
        'libairspy-dev',
        'libhackrf-dev',
    ]

    def __init__(self):
        """
        Initialise installer with environment detection.
        """
        super().__init__()

        self._package_manager = (
            self._detect_package_manager()
        )
        self._arch = platform.machine()
        self.satdump_binary_path = shutil.which(
            self.SATDUMP_BINARY
        )

        print(
            f"[SatDump] Installer init | "
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
        Check if SatDump is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False
        return (
            shutil.which(self.SATDUMP_BINARY) is not None or
            shutil.which(self.SATDUMP_UI_BINARY) is not None
        )

    def install_python_packages(self):
        """
        Install required and optional Python packages.

        Returns:
            bool: True if required packages available
        """
        print("[SatDump] Checking Python packages...")

        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )

        # Optional packages — non-fatal
        for pkg in self.OPTIONAL_PACKAGES:
            self.pip_install(pkg)

        if failed and self.in_docker:
            print(
                f"[SatDump] INFO: Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        return len(failed) == 0

    def _install_via_apt_ppa(self):
        """
        Install SatDump via official apt PPA.

        Uses self._sudo prefix for all system commands.
        In Docker as non-root, returns False immediately.

        Returns:
            bool: True if installation successful
        """
        print("[SatDump] Installing via apt PPA...")

        if not shutil.which('apt-get'):
            print("[SatDump] apt-get not available")
            return False

        if self.in_docker and not self.is_root:
            print(
                "[SatDump] INFO: Cannot apt-get in Docker "
                "as non-root. Add to Dockerfile:"
            )
            print(
                "[SatDump] INFO:   RUN curl -fsSL "
                "https://downloads.satdump.org/key.gpg"
                " | apt-key add - && \\"
            )
            print(
                '[SatDump] INFO:       echo "deb '
                'https://downloads.satdump.org/apt '
                'stable main" '
                '> /etc/apt/sources.list.d/satdump.list'
                ' && \\'
            )
            print(
                "[SatDump] INFO:       apt-get update && "
                "apt-get install -y satdump"
            )
            return False

        # Install prerequisites
        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y',
                'curl', 'apt-transport-https', 'gnupg'
            ],
            timeout=120
        )
        if not ok:
            print(
                f"[SatDump] Prerequisites failed: "
                f"{stderr[:100]}"
            )
            return False

        # Add GPG key
        print("[SatDump] Adding repository key...")
        key_ok, key_data, _ = self._run_system_command(
            [
                'curl', '-fsSL',
                f'{self.SATDUMP_APT_REPO}/key.gpg'
            ],
            timeout=30
        )

        if key_ok and key_data:
            try:
                key_proc = subprocess.Popen(
                    self._sudo + ['apt-key', 'add', '-'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                key_proc.communicate(
                    input=key_data.encode(),
                    timeout=15
                )
            except Exception as e:
                print(
                    f"[SatDump] GPG key warning: {e}"
                )

        # Detect distro
        ok, distro, _ = self._run_system_command(
            ['lsb_release', '-cs'],
            timeout=5
        )
        distro_name = distro.strip() if ok else 'bullseye'

        # Add repository
        print(
            f"[SatDump] Adding repository "
            f"for {distro_name}..."
        )
        repo_line = (
            f"deb [arch=amd64] "
            f"{self.SATDUMP_APT_REPO}/apt "
            f"{distro_name} main\n"
        )

        try:
            list_file = '/tmp/satdump.list'
            with open(list_file, 'w') as f:
                f.write(repo_line)
            self._run_system_command(
                self._sudo + [
                    'cp', list_file,
                    '/etc/apt/sources.list.d/satdump.list'
                ],
                timeout=10
            )
        except Exception as e:
            print(
                f"[SatDump] Repo add warning: {e}"
            )

        # Update and install
        ok, _, stderr = self._run_system_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[SatDump] Update failed: {stderr[:100]}"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'satdump'
            ],
            timeout=300
        )

        if ok:
            print("[SatDump] ✓ Installed via apt PPA")
            return True

        print(
            f"[SatDump] apt install failed: {stderr[:200]}"
        )
        return False

    def _install_via_flatpak(self):
        """
        Install SatDump via Flatpak from Flathub.

        Returns:
            bool: True if installation successful
        """
        print("[SatDump] Installing via Flatpak...")

        if not shutil.which('flatpak'):
            print("[SatDump] Flatpak not available")
            return self._build_from_source()

        # Add Flathub
        self._run_system_command(
            [
                'flatpak', 'remote-add',
                '--if-not-exists', 'flathub',
                'https://flathub.org/repo/flathub.flatpakrepo'
            ],
            timeout=30
        )

        ok, _, stderr = self._run_system_command(
            [
                'flatpak', 'install',
                '-y', 'flathub', self.FLATPAK_APP_ID
            ],
            timeout=300
        )

        if not ok:
            print(
                f"[SatDump] Flatpak failed: {stderr[:200]}"
            )
            return self._build_from_source()

        # Create wrapper
        wrapper_dir = os.path.expanduser('~/.local/bin')
        os.makedirs(wrapper_dir, exist_ok=True)
        wrapper_path = os.path.join(wrapper_dir, 'satdump')

        try:
            with open(wrapper_path, 'w') as f:
                f.write(
                    '#!/bin/bash\n'
                    f'exec flatpak run '
                    f'{self.FLATPAK_APP_ID} "$@"\n'
                )
            os.chmod(wrapper_path, 0o755)
        except Exception as e:
            print(
                f"[SatDump] Wrapper warning: {e}"
            )

        print("[SatDump] ✓ Installed via Flatpak")
        return True

    def _build_from_source(self):
        """
        Build SatDump from GitHub source.

        Not available in Docker as non-root.

        Returns:
            bool: True if build successful
        """
        if self.in_docker and not self.is_root:
            print(
                "[SatDump] INFO: Cannot build from source "
                "in Docker as non-root."
            )
            return False

        print("[SatDump] Building from source...")
        build_dir = os.path.join(
            os.path.expanduser('~'), '_satdump_build'
        )

        try:
            if shutil.which('apt-get') and \
                    (self.is_root or self.sudo_available):
                self._run_system_command(
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
                    '--recurse-submodules',
                    self.SATDUMP_REPO, build_dir
                ],
                timeout=180
            )
            if not ok:
                print(
                    f"[SatDump] Clone failed: {stderr}"
                )
                return False

            cmake_dir = os.path.join(build_dir, 'build')
            os.makedirs(cmake_dir, exist_ok=True)

            ok, _, stderr = self._run_system_command(
                [
                    'cmake', '..',
                    '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_INSTALL_PREFIX=/usr/local',
                    '-DBUILD_GUI=OFF',
                    '-DPLUGIN_ALL=ON',
                ],
                timeout=300
            )
            if not ok:
                print(
                    f"[SatDump] cmake failed: {stderr[:200]}"
                )
                return False

            cpu_count = os.cpu_count() or 2
            ok, _, stderr = self._run_system_command(
                ['make', f'-j{cpu_count}'],
                timeout=1800
            )
            if not ok:
                print(
                    f"[SatDump] make failed: {stderr[:200]}"
                )
                return False

            ok, _, stderr = self._run_system_command(
                self._sudo + ['make', 'install'],
                timeout=120
            )
            if not ok:
                print(
                    f"[SatDump] install failed: "
                    f"{stderr[:200]}"
                )
                return False

            self._run_system_command(
                self._sudo + ['ldconfig'],
                timeout=30
            )

            print("[SatDump] ✓ Built from source")
            return True

        except Exception as e:
            print(f"[SatDump] Source build error: {e}")
            traceback.print_exc()
            return False

        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(
                    build_dir, ignore_errors=True
                )

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
            output = (result.stdout + result.stderr).strip()
            for line in output.splitlines():
                if 'satdump' in line.lower() or \
                        line.strip().startswith(('0.', '1.')):
                    return line.strip()[:50]
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
                'binary': shutil.which(self.SATDUMP_BINARY),
                'platform': platform.platform(),
                'arch': self._arch,
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

        Outside Docker: tries apt PPA, Flatpak,
        then source build in order.

        Returns:
            bool: True if installed or already present
        """
        if self.is_installed():
            print("[SatDump] ✓ Already installed")
            return True

        if shutil.which(self.SATDUMP_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[SatDump] ✓ Found in PATH")
            return True

        print("[SatDump] ==========================================")
        print("[SatDump] Starting first-run installation")
        print("[SatDump] ==========================================")

        # Docker non-root: cannot install system packages
        if self.in_docker and not self.is_root:
            print(
                "\n[SatDump] ======================================"
            )
            print("[SatDump] DOCKER INSTALLATION REQUIRED")
            print(
                "[SatDump] ======================================"
            )
            print(
                "[SatDump] Add to Dockerfile and rebuild:"
            )
            print()
            print("[SatDump]   # Add SatDump repository")
            print(
                "[SatDump]   RUN apt-get update && \\"
            )
            print(
                "[SatDump]       apt-get install -y "
                "curl gnupg && \\"
            )
            print(
                "[SatDump]       curl -fsSL "
                "https://downloads.satdump.org/key.gpg"
                " | apt-key add - && \\"
            )
            print(
                '[SatDump]       echo "deb '
                'https://downloads.satdump.org/apt '
                'stable main" '
                '> /etc/apt/sources.list.d/satdump.list'
                ' && \\'
            )
            print(
                "[SatDump]       apt-get update && \\"
            )
            print(
                "[SatDump]       apt-get install -y "
                "satdump && \\"
            )
            print(
                "[SatDump]       rm -rf /var/lib/apt/lists/*"
            )
            print()
            print(
                "[SatDump]   docker compose build --no-cache"
            )
            print(
                "[SatDump] ======================================"
            )
            return False

        # Step 1: Python packages
        print("\n[SatDump] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: Install SatDump
        print(
            f"\n[SatDump] Step 2: Installing SatDump "
            f"(pkg mgr: "
            f"{self._package_manager or 'none'})..."
        )
        success = False

        if self._package_manager in ('apt-get', 'apt'):
            success = self._install_via_apt_ppa()
            if not success:
                success = self._install_via_flatpak()
        elif shutil.which('flatpak'):
            success = self._install_via_flatpak()
        elif self._package_manager == 'pacman':
            if shutil.which('yay'):
                ok, _, _ = self._run_system_command(
                    ['yay', '-S', '--noconfirm', 'satdump'],
                    timeout=300
                )
                success = ok
            if not success:
                success = self._install_via_flatpak()
        else:
            success = self._install_via_flatpak()

        if not success:
            print("[SatDump] ERROR: Installation failed")
            return False

        version = self.get_version()
        self.write_install_marker(
            self._package_manager or 'flatpak',
            version
        )

        print(
            "\n[SatDump] =========================================="
        )
        print("[SatDump] ✓ Installation complete!")
        if version:
            print(f"[SatDump]   Version: {version}")
        print(
            "[SatDump] =========================================="
            "\n"
        )

        return True
