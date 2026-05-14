"""
WSJT-X Installer
=================
Handles first-run installation of WSJT-X and dependencies.

Docker Deployment Notes:
    WSJT-X is a system application that requires root to
    install. In Docker the runtime user (hamradio, UID 1000)
    cannot run apt-get or sudo.

    WSJT-X MUST be installed in the Dockerfile at build time.
    Add to Dockerfile before USER hamradio:

        RUN apt-get update && apt-get install -y wsjtx

    This installer detects Docker and logs clear instructions
    rather than attempting a doomed runtime install.

WSJT-X Installation Methods (outside Docker):
    1. apt-get (Debian/Ubuntu)
    2. dnf (Fedora/RHEL)
    3. pacman + yay AUR (Arch Linux)
    4. Flatpak from Flathub
    5. AppImage direct download

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
                print(f"[WSJTX] Marker write error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class WSJTXInstaller(BaseInstaller):
    """
    Manages WSJT-X installation and verification.

    Extends BaseInstaller for Docker-aware handling.
    In Docker as non-root, all system installs are
    skipped with clear Dockerfile instructions logged.
    """

    # Installation state marker
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

    # Flathub application ID
    FLATPAK_APP_ID = 'org.physics.wsjtx'

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
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
        self.wsjtx_binary_path = shutil.which(
            self.WSJTX_BINARY
        )

        print(
            f"[WSJTX] Installer init | "
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
        for mgr in [
            'apt-get', 'dnf', 'yum', 'pacman', 'zypper'
        ]:
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
        Check if WSJT-X is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False
        return shutil.which(self.WSJTX_BINARY) is not None

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages available
        """
        print("[WSJTX] Checking Python packages...")
        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )
        if failed and self.in_docker:
            print(
                f"[WSJTX] INFO: Add to requirements.txt: "
                f"{', '.join(failed)}"
            )
        return len(failed) == 0

    def _install_via_apt(self):
        """
        Install WSJT-X via apt-get.

        Uses self._sudo prefix which is empty for root,
        ['sudo'] for non-root with sudo, or [] for
        non-root without sudo (Docker).

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via apt-get...")

        if not shutil.which('apt-get'):
            print("[WSJTX] apt-get not available")
            return False

        if self.in_docker and not self.is_root:
            print(
                "[WSJTX] INFO: Cannot apt-get in Docker "
                "as non-root. Add to Dockerfile:"
            )
            print(
                "[WSJTX] INFO:   RUN apt-get update && "
                "apt-get install -y wsjtx"
            )
            return False

        # Update package list
        ok, _, stderr = self._run_system_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[WSJTX] apt-get update failed: "
                f"{stderr[:150]}"
            )
            return False

        # Install WSJT-X
        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'wsjtx'
            ],
            timeout=300
        )

        if ok:
            print("[WSJTX] ✓ Installed via apt-get")
            return True

        print(
            f"[WSJTX] apt-get failed: {stderr[:200]}"
        )
        # Fall through to Flatpak
        return self._install_via_flatpak()

    def _install_via_dnf(self):
        """
        Install WSJT-X via dnf (Fedora/RHEL).

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via dnf...")

        if not shutil.which('dnf'):
            return False

        if self.in_docker and not self.is_root:
            print(
                "[WSJTX] INFO: Add to Dockerfile: "
                "RUN dnf install -y wsjtx"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + ['dnf', 'install', '-y', 'wsjtx'],
            timeout=300
        )

        if ok:
            print("[WSJTX] ✓ Installed via dnf")
            return True

        print(f"[WSJTX] dnf failed: {stderr[:200]}")
        return self._install_via_flatpak()

    def _install_via_pacman(self):
        """
        Install WSJT-X via pacman (Arch Linux).

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via pacman...")

        if not shutil.which('pacman'):
            return False

        if self.in_docker and not self.is_root:
            print(
                "[WSJTX] INFO: Add to Dockerfile: "
                "RUN pacman -S --noconfirm wsjtx"
            )
            return False

        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'pacman', '-S', '--noconfirm', 'wsjtx'
            ],
            timeout=300
        )

        if ok:
            print("[WSJTX] ✓ Installed via pacman")
            return True

        # Try AUR via yay
        if shutil.which('yay'):
            ok, _, stderr = self._run_system_command(
                ['yay', '-S', '--noconfirm', 'wsjtx'],
                timeout=300
            )
            if ok:
                print("[WSJTX] ✓ Installed via yay (AUR)")
                return True

        return self._install_via_flatpak()

    def _install_via_flatpak(self):
        """
        Install WSJT-X via Flatpak from Flathub.

        Creates a wrapper script at ~/.local/bin/wsjtx
        so the plugin can launch WSJT-X normally.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Installing via Flatpak...")

        if not shutil.which('flatpak'):
            print("[WSJTX] Flatpak not available")
            return self._install_appimage()

        # Add Flathub remote
        self._run_system_command(
            [
                'flatpak', 'remote-add',
                '--if-not-exists', 'flathub',
                'https://flathub.org/repo/flathub.flatpakrepo'
            ],
            timeout=30
        )

        # Install WSJT-X
        ok, _, stderr = self._run_system_command(
            [
                'flatpak', 'install',
                '-y', 'flathub', self.FLATPAK_APP_ID
            ],
            timeout=300
        )

        if not ok:
            print(
                f"[WSJTX] Flatpak failed: {stderr[:200]}"
            )
            return self._install_appimage()

        # Create wrapper script
        wrapper_dir = os.path.expanduser('~/.local/bin')
        os.makedirs(wrapper_dir, exist_ok=True)
        wrapper_path = os.path.join(wrapper_dir, 'wsjtx')

        try:
            with open(wrapper_path, 'w') as f:
                f.write(
                    '#!/bin/bash\n'
                    f'exec flatpak run '
                    f'{self.FLATPAK_APP_ID} "$@"\n'
                )
            os.chmod(wrapper_path, 0o755)
            print(
                f"[WSJTX] ✓ Flatpak wrapper: "
                f"{wrapper_path}"
            )
        except Exception as e:
            print(
                f"[WSJTX] Wrapper error (non-fatal): {e}"
            )

        print("[WSJTX] ✓ Installed via Flatpak")
        return True

    def _install_appimage(self):
        """
        Download and install WSJT-X AppImage.

        Downloads the AppImage for the current architecture
        and creates a wrapper script.

        Returns:
            bool: True if installation successful
        """
        print("[WSJTX] Downloading AppImage...")

        try:
            arch = 'x86_64' if self._arch == 'x86_64' \
                else 'aarch64'
            appimage_url = (
                f"{self.WSJTX_DOWNLOAD_BASE}"
                f"wsjtx_2.7.0_Linux_{arch}.AppImage"
            )

            install_dir = os.path.expanduser(
                '~/.local/share/wsjtx'
            )
            os.makedirs(install_dir, exist_ok=True)
            appimage_path = os.path.join(
                install_dir, 'wsjtx.AppImage'
            )

            print(
                f"[WSJTX] Downloading from {appimage_url}"
            )
            urllib.request.urlretrieve(
                appimage_url, appimage_path
            )
            os.chmod(appimage_path, 0o755)

            # Create wrapper script
            wrapper_dir = os.path.expanduser('~/.local/bin')
            os.makedirs(wrapper_dir, exist_ok=True)
            wrapper_path = os.path.join(wrapper_dir, 'wsjtx')

            with open(wrapper_path, 'w') as f:
                f.write(
                    f'#!/bin/bash\n'
                    f'exec "{appimage_path}" "$@"\n'
                )
            os.chmod(wrapper_path, 0o755)

            print(
                f"[WSJTX] ✓ AppImage installed: "
                f"{appimage_path}"
            )
            return True

        except Exception as e:
            print(
                f"[WSJTX] AppImage failed: {e}"
            )
            print(
                "[WSJTX] Manual install: "
                "https://physics.princeton.edu/"
                "pulsar/k1jt/wsjtx.html"
            )
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
                'binary': shutil.which(self.WSJTX_BINARY),
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

        Outside Docker: tries apt-get, dnf, pacman,
        Flatpak, then AppImage in order.

        Returns:
            bool: True if installed or already present
        """
        if self.is_installed():
            print("[WSJTX] ✓ Already installed")
            return True

        if shutil.which(self.WSJTX_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[WSJTX] ✓ Found in PATH")
            return True

        print("[WSJTX] ==========================================")
        print("[WSJTX] Starting first-run installation")
        print("[WSJTX] ==========================================")

        # Docker non-root: cannot install system packages
        if self.in_docker and not self.is_root:
            print(
                "\n[WSJTX] ======================================"
            )
            print("[WSJTX] DOCKER INSTALLATION REQUIRED")
            print(
                "[WSJTX] ======================================"
            )
            print(
                "[WSJTX] Add to Dockerfile and rebuild:"
            )
            print()
            print(
                "[WSJTX]   RUN apt-get update && \\"
            )
            print(
                "[WSJTX]       apt-get install -y wsjtx && \\"
            )
            print(
                "[WSJTX]       rm -rf /var/lib/apt/lists/*"
            )
            print()
            print(
                "[WSJTX]   docker compose build --no-cache"
            )
            print(
                "[WSJTX] ======================================"
            )
            return False

        # Step 1: Python packages
        print("\n[WSJTX] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: Install WSJT-X
        print(
            f"\n[WSJTX] Step 2: Installing WSJT-X "
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
        else:
            success = self._install_via_flatpak()

        if not success:
            print("[WSJTX] ERROR: Installation failed")
            return False

        version = self.get_version()
        self.write_install_marker(
            self._package_manager or 'flatpak',
            version
        )

        print("\n[WSJTX] ==========================================")
        print("[WSJTX] ✓ Installation complete!")
        if version:
            print(f"[WSJTX]   Version: {version}")
        print("[WSJTX] ==========================================\n")

        return True
