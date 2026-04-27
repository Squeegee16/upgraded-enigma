"""
OpenWebRX Dependency Installer
================================
Handles installation of OpenWebRX and its required
dependencies on first run.

This class extends BaseInstaller which provides
Docker-aware pip and apt-get handling.

OpenWebRX Installation Methods (in priority order):
    1. apt-get via official repository (Debian/Ubuntu)
    2. Docker image pull (if Docker is available)
    3. Flatpak from Flathub (universal Linux)
    4. pip install (last resort fallback)

Docker Behaviour:
    When running inside a Docker container as a non-root
    user (the standard deployment), system-level installs
    are not possible. The installer detects this via the
    PLUGIN_SKIP_PIP_INSTALL environment variable set in
    the Dockerfile and skips installation attempts.

    In this case the plugin UI still loads and displays
    an informational message. OpenWebRX must be added to
    the Dockerfile and the image rebuilt to use it.

Source:
    https://github.com/jketterl/openwebrx
    https://openwebrx.de/

Author: Ham Radio App Team
Version: 1.0.0
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from datetime import datetime

# Import the shared base installer for Docker-aware
# pip and apt-get handling
try:
    from plugins.implementations.base_installer import BaseInstaller
except ImportError:
    # Fallback if base_installer is not yet available
    # Define a minimal inline base class
    class BaseInstaller:
        """Minimal fallback base installer."""

        def __init__(self):
            try:
                self.is_root = (os.getuid() == 0)
            except AttributeError:
                self.is_root = False

            self.sudo_available = shutil.which('sudo') is not None
            self._sudo = [] if (
                self.is_root or not self.sudo_available
            ) else ['sudo']

            self.in_docker = (
                os.environ.get(
                    'PLUGIN_SKIP_PIP_INSTALL', ''
                ).lower() == 'true' or
                os.path.exists('/.dockerenv')
            )

        def pip_install(self, package):
            """Install package or skip in Docker."""
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
            """Install list of packages."""
            failed = []
            for pkg in packages:
                if not self.pip_install(pkg):
                    failed.append(pkg)
            return len(packages) - len(failed), failed

        def write_marker(self, path, extra=None):
            """Write installation marker."""
            data = {
                'installed': True,
                'timestamp': datetime.utcnow().isoformat(),
                'in_docker': self.in_docker,
            }
            if extra:
                data.update(extra)
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Installer] Marker write error: {e}")

        def read_marker(self, path):
            """Read installation marker."""
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class OpenWebRXInstaller(BaseInstaller):
    """
    Manages OpenWebRX installation and verification.

    Extends BaseInstaller to add OpenWebRX-specific
    installation logic including apt repository setup,
    Docker image pulling, Flatpak, and pip fallback.

    Inherits Docker detection and safe pip/apt wrappers
    from BaseInstaller.
    """

    # ----------------------------------------------------------
    # Class-level constants
    # ----------------------------------------------------------

    # Installation state marker file path
    # Stored inside the plugin directory
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # OpenWebRX Docker image reference
    DOCKER_IMAGE = 'jketterl/openwebrx:latest'

    # Official Debian/Ubuntu repository base URL
    DEBIAN_REPO = 'https://repo.openwebrx.de/debian/'

    # Flathub application identifier
    FLATPAK_APP_ID = 'de.openwebrx.OpenWebRX'

    # Default port for the OpenWebRX web interface
    DEFAULT_HTTP_PORT = 8073

    # Python packages required by this plugin
    # These are checked/installed via BaseInstaller
    REQUIRED_PYTHON_PACKAGES = [
        'requests',
        'psutil',
        'websockets',
        'aiohttp',
    ]

    def __init__(self):
        """
        Initialise the OpenWebRX installer.

        Calls BaseInstaller.__init__() to detect the
        runtime environment (Docker, root, sudo) then
        adds OpenWebRX-specific detection.
        """
        # Call parent init for environment detection
        super().__init__()

        # Detect available package manager
        self._package_manager = self._detect_package_manager()

        # System architecture for binary downloads
        self._arch = platform.machine()

        print(
            f"[OpenWebRX] Installer initialised | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"sudo: {self.sudo_available} | "
            f"pkg mgr: {self._package_manager or 'none'}"
        )

    # ----------------------------------------------------------
    # Private helper methods
    # ----------------------------------------------------------

    def _detect_package_manager(self):
        """
        Detect the available system package manager.

        Returns:
            str: Package manager name or None if not found
        """
        for manager in [
            'apt-get', 'dnf', 'yum', 'pacman', 'zypper'
        ]:
            if shutil.which(manager):
                return manager
        return None

    def _run_command(self, cmd, timeout=300):
        """
        Execute a shell command safely.

        Handles FileNotFoundError (missing binary),
        CalledProcessError (non-zero exit), and
        TimeoutExpired separately for clear logging.

        Args:
            cmd: Command list to execute
            timeout: Maximum seconds to wait

        Returns:
            tuple: (success: bool, stdout: str, stderr: str)
        """
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=timeout
            )
            stdout = (
                result.stdout.decode('utf-8', errors='replace')
                if result.stdout else ''
            )
            return True, stdout, ''

        except FileNotFoundError as e:
            return (
                False, '',
                f"Command not found: {cmd[0]} — {e}"
            )
        except subprocess.CalledProcessError as e:
            stderr = (
                e.stderr.decode('utf-8', errors='replace')
                if e.stderr else str(e)
            )
            return False, '', stderr
        except subprocess.TimeoutExpired:
            return (
                False, '',
                f"Timed out after {timeout}s"
            )
        except Exception as e:
            return False, '', str(e)

    # ----------------------------------------------------------
    # Installation state checks
    # ----------------------------------------------------------

    def is_installed(self):
        """
        Check whether OpenWebRX is installed.

        Verifies that both the marker file exists and
        the actual installation is still present.

        Returns:
            bool: True if OpenWebRX is available
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        info = self.get_install_info()
        method = info.get('method', '')

        # Docker-pending means we acknowledged we can't
        # install right now but will try again
        if method == 'docker_pending':
            return False

        # Check actual presence by method
        if method == 'docker':
            return self._check_docker_image()
        elif method == 'flatpak':
            return self._check_flatpak()
        elif method == 'pip':
            return self._check_pip()
        else:
            # apt / existing / unknown — check binary
            return shutil.which('openwebrx') is not None

    def _check_docker_image(self):
        """
        Verify the OpenWebRX Docker image is available.

        Returns:
            bool: True if image exists locally
        """
        if not shutil.which('docker'):
            return False
        ok, stdout, _ = self._run_command(
            ['docker', 'images', '-q', self.DOCKER_IMAGE],
            timeout=10
        )
        return ok and bool(stdout.strip())

    def _check_flatpak(self):
        """
        Verify OpenWebRX is installed via Flatpak.

        Returns:
            bool: True if Flatpak app is listed
        """
        if not shutil.which('flatpak'):
            return False
        ok, stdout, _ = self._run_command(
            [
                'flatpak', 'list',
                '--app',
                '--columns=application'
            ],
            timeout=15
        )
        return ok and self.FLATPAK_APP_ID in stdout

    def _check_pip(self):
        """
        Verify OpenWebRX pip package is importable.

        Returns:
            bool: True if import succeeds
        """
        try:
            import openwebrx
            return True
        except ImportError:
            return False

    def get_install_info(self):
        """
        Read installation marker data.

        Returns:
            dict: Stored marker data or empty dict
        """
        return self.read_marker(self.INSTALL_MARKER)

    def get_version(self):
        """
        Attempt to retrieve the installed OpenWebRX version.

        Tries binary --version, Flatpak info, then
        pip package metadata in order.

        Returns:
            str: Version string or None
        """
        # Try binary
        binary = shutil.which('openwebrx')
        if binary:
            ok, stdout, _ = self._run_command(
                [binary, '--version'],
                timeout=10
            )
            if ok and stdout.strip():
                return stdout.strip()

        # Try Flatpak metadata
        if self._check_flatpak():
            ok, stdout, _ = self._run_command(
                ['flatpak', 'info', self.FLATPAK_APP_ID],
                timeout=15
            )
            if ok and stdout:
                for line in stdout.splitlines():
                    line_lower = line.lower()
                    if 'version' in line_lower:
                        parts = line.split(':')
                        if len(parts) > 1:
                            return parts[1].strip()

        # Try pip package
        try:
            import openwebrx
            return getattr(openwebrx, '__version__', 'pip')
        except ImportError:
            pass

        return None

def write_install_marker(self, method, version=None):
        """
        Write the OpenWebRX installation marker.

        Delegates to BaseInstaller.write_marker() with
        the correct extra_data keyword argument.

        Args:
            method:  Installation method string
            version: Version string if available
        """
        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={                     # <-- was 'extra='
                'method': method,
                'version': version,
                'platform': platform.platform(),
                'arch': self._arch,
                'docker_image': (
                    self.DOCKER_IMAGE
                    if method == 'docker' else None
                ),
            }
        )

    # ----------------------------------------------------------
    # Installation methods
    # ----------------------------------------------------------

    def _install_via_apt(self):
        """
        Install OpenWebRX via the official apt repository.

        Steps:
            1. Install apt prerequisites
            2. Add OpenWebRX GPG key
            3. Add OpenWebRX apt repository
            4. Run apt-get update
            5. Install openwebrx package

        Falls back to _install_via_flatpak() on failure.

        Returns:
            bool: True if installation successful
        """
        print("[OpenWebRX] Installing via apt-get...")

        if not shutil.which('apt-get'):
            print("[OpenWebRX] apt-get not found — skipping")
            return self._install_via_flatpak()

        # Step 1: Install prerequisites
        print("[OpenWebRX] Installing apt prerequisites...")
        ok, _, stderr = self._run_command(
            self._sudo + [
                'apt-get', 'install', '-y',
                'apt-transport-https',
                'curl',
                'gnupg',
                'lsb-release',
            ],
            timeout=120
        )
        if not ok:
            print(
                f"[OpenWebRX] Prerequisites failed: "
                f"{stderr[:120]}"
            )
            return self._install_via_flatpak()

        # Step 2: Add GPG key
        print("[OpenWebRX] Adding OpenWebRX GPG key...")
        if shutil.which('curl'):
            key_ok, key_data, _ = self._run_command(
                [
                    'curl', '-fsSL',
                    'https://repo.openwebrx.de/debian/'
                    'key.gpg.txt'
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
                        f"[OpenWebRX] GPG key warning: {e}"
                    )

        # Step 3: Get distro codename and add repository
        distro_ok, distro_name, _ = self._run_command(
            ['lsb_release', '-cs'],
            timeout=5
        )
        distro = distro_name.strip() \
            if distro_ok else 'bullseye'

        print(
            f"[OpenWebRX] Adding repository "
            f"for {distro}..."
        )

        repo_content = (
            f"deb [arch=amd64] "
            f"{self.DEBIAN_REPO} {distro} main\n"
        )

        try:
            list_file = '/tmp/openwebrx.list'
            with open(list_file, 'w') as f:
                f.write(repo_content)

            self._run_command(
                self._sudo + [
                    'cp', list_file,
                    '/etc/apt/sources.list.d/openwebrx.list'
                ],
                timeout=10
            )
        except Exception as e:
            print(
                f"[OpenWebRX] Repository add warning: {e}"
            )

        # Step 4: Update package list
        print("[OpenWebRX] Running apt-get update...")
        ok, _, stderr = self._run_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[OpenWebRX] apt-get update failed: "
                f"{stderr[:120]}"
            )
            return self._install_via_flatpak()

        # Step 5: Install OpenWebRX
        print("[OpenWebRX] Installing openwebrx package...")
        ok, _, stderr = self._run_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'openwebrx'
            ],
            timeout=300
        )

        if ok:
            print("[OpenWebRX] ✓ Installed via apt-get")
            return True

        print(
            f"[OpenWebRX] apt-get install failed: "
            f"{stderr[:200]}"
        )
        return self._install_via_flatpak()

    def _install_via_docker(self):
        """
        Pull the OpenWebRX Docker image.

        Creates a wrapper script so the plugin can
        manage the container lifecycle.

        Falls back to _install_via_flatpak() on failure.

        Returns:
            bool: True if image pulled successfully
        """
        print("[OpenWebRX] Installing via Docker...")

        if not shutil.which('docker'):
            print("[OpenWebRX] Docker not available")
            return self._install_via_flatpak()

        print(
            f"[OpenWebRX] Pulling {self.DOCKER_IMAGE}..."
        )
        ok, _, stderr = self._run_command(
            ['docker', 'pull', self.DOCKER_IMAGE],
            timeout=300
        )

        if ok:
            print("[OpenWebRX] ✓ Docker image pulled")
            return True

        print(
            f"[OpenWebRX] Docker pull failed: "
            f"{stderr[:200]}"
        )
        return self._install_via_flatpak()

    def _install_via_flatpak(self):
        """
        Install OpenWebRX via Flatpak from Flathub.

        Creates a CLI wrapper script at
        ~/.local/bin/openwebrx so the plugin can
        interact with the Flatpak installation normally.

        Falls back to _install_via_pip() on failure.

        Returns:
            bool: True if installation successful
        """
        print("[OpenWebRX] Installing via Flatpak...")

        if not shutil.which('flatpak'):
            print("[OpenWebRX] Flatpak not available")
            return self._install_via_pip()

        # Add Flathub remote
        print("[OpenWebRX] Adding Flathub remote...")
        self._run_command(
            [
                'flatpak', 'remote-add',
                '--if-not-exists',
                'flathub',
                'https://flathub.org/repo/'
                'flathub.flatpakrepo'
            ],
            timeout=30
        )

        # Install application
        print(
            f"[OpenWebRX] Installing "
            f"{self.FLATPAK_APP_ID}..."
        )
        ok, _, stderr = self._run_command(
            [
                'flatpak', 'install',
                '-y', 'flathub',
                self.FLATPAK_APP_ID
            ],
            timeout=300
        )

        if not ok:
            print(
                f"[OpenWebRX] Flatpak failed: "
                f"{stderr[:200]}"
            )
            return self._install_via_pip()

        # Create CLI wrapper script
        wrapper_dir = os.path.expanduser('~/.local/bin')
        os.makedirs(wrapper_dir, exist_ok=True)
        wrapper_path = os.path.join(wrapper_dir, 'openwebrx')

        try:
            with open(wrapper_path, 'w') as f:
                f.write(
                    '#!/bin/bash\n'
                    f'exec flatpak run '
                    f'{self.FLATPAK_APP_ID} "$@"\n'
                )
            os.chmod(wrapper_path, 0o755)
            print(
                f"[OpenWebRX] ✓ Wrapper: {wrapper_path}"
            )
        except Exception as e:
            print(
                f"[OpenWebRX] Wrapper error (non-fatal): "
                f"{e}"
            )

        print("[OpenWebRX] ✓ Installed via Flatpak")
        return True

    def _install_via_pip(self):
        """
        Attempt pip install of OpenWebRX as last resort.

        Note: openwebrx may not be on PyPI. This method
        will fail gracefully and log a manual install
        instruction.

        Returns:
            bool: True if pip install succeeded
        """
        print("[OpenWebRX] Trying pip (last resort)...")

        ok, _, stderr = self._run_command(
            [
                sys.executable, '-m', 'pip',
                'install', '--quiet', 'openwebrx'
            ],
            timeout=120
        )

        if ok:
            print("[OpenWebRX] ✓ Installed via pip")
            return True

        print(
            f"[OpenWebRX] pip failed: {stderr[:200]}"
        )
        print(
            "[OpenWebRX] All methods failed. "
            "Install manually: https://openwebrx.de/"
        )
        return False

    # ----------------------------------------------------------
    # Public install_python_packages override
    # ----------------------------------------------------------

    def install_python_packages(self):
        """
        Install required Python packages.

        Delegates to BaseInstaller.install_python_packages()
        which handles Docker environments correctly.

        Returns:
            bool: True if all packages available
        """
        print("[OpenWebRX] Installing Python packages...")

        available, failed = super().install_python_packages(
            self.REQUIRED_PYTHON_PACKAGES
        )

        if failed and not self.in_docker:
            print(
                f"[OpenWebRX] WARNING: "
                f"Failed packages: {failed}"
            )
            return False

        return True

    # ----------------------------------------------------------
    # Main entry point — called by the plugin on first run
    # ----------------------------------------------------------

    def run(self):
        """
        Execute the complete first-run installation process.

        This is the primary public method called by the
        plugin's initialize() method. It:

            1. Checks if already installed (skip if so)
            2. Checks if binary is already in PATH
            3. Checks if running in Docker as non-root
               (cannot install — logs guidance and returns)
            4. Installs Python packages
            5. Installs OpenWebRX via best available method:
               apt-get → Docker → Flatpak → pip

        Always returns True so the plugin UI loads even
        when OpenWebRX itself cannot be installed. The UI
        will show an appropriate status message.

        Returns:
            bool: True always (plugin UI always loads)
        """
        # Already installed — nothing to do
        if self.is_installed():
            print("[OpenWebRX] ✓ Already installed")
            return True

        # Binary found in PATH but no marker — write marker
        if shutil.which('openwebrx'):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print(
                "[OpenWebRX] ✓ Found existing installation"
            )
            return True

        print(
            "[OpenWebRX] "
            "========================================"
        )
        print("[OpenWebRX] First-run installation")
        print(
            "[OpenWebRX] "
            "========================================"
        )

        # -------------------------------------------------------
        # Docker non-root: cannot install system packages
        # -------------------------------------------------------
        if self.in_docker and not self.is_root:
            print(
                "[OpenWebRX] INFO: Running in Docker as "
                "non-root user."
            )
            print(
                "[OpenWebRX] INFO: System installs require "
                "root. Add to Dockerfile:"
            )
            print(
                "[OpenWebRX] INFO:   RUN apt-get install "
                "-y openwebrx"
            )
            print(
                "[OpenWebRX] INFO: Then rebuild: "
                "docker compose build --no-cache"
            )

            # Write marker so we skip this check next time
            # and don't spam logs on every startup
            self.write_install_marker(
                'docker_pending',
                {'note': 'Requires Docker image rebuild'}
            )

            # Return True — let the plugin UI load
            return True

        # -------------------------------------------------------
        # Step 1: Python packages
        # -------------------------------------------------------
        print("\n[OpenWebRX] Step 1: Python packages...")
        self.install_python_packages()
        # Always continue — non-fatal

        # -------------------------------------------------------
        # Step 2: Install OpenWebRX application
        # -------------------------------------------------------
        print(
            f"\n[OpenWebRX] Step 2: Installing OpenWebRX | "
            f"pkg mgr: {self._package_manager or 'none'}..."
        )

        success = False

        if self._package_manager in ('apt-get', 'apt'):
            success = self._install_via_apt()
        elif shutil.which('docker'):
            success = self._install_via_docker()
        elif shutil.which('flatpak'):
            success = self._install_via_flatpak()
        else:
            # Last resort
            success = self._install_via_pip()

        # -------------------------------------------------------
        # Post-install
        # -------------------------------------------------------
        if success:
            version = self.get_version()
            self.write_install_marker(
                self._package_manager or 'unknown',
                version
            )
            print(
                "\n[OpenWebRX] "
                "========================================"
            )
            print("[OpenWebRX] ✓ Installation complete!")
            if version:
                print(f"[OpenWebRX]   Version: {version}")
            print(
                "[OpenWebRX] "
                "========================================"
            )
        else:
            print(
                "\n[OpenWebRX] Installation failed. "
                "The plugin UI will still load."
            )
            print(
                "[OpenWebRX] Manual install: "
                "https://openwebrx.de/"
            )

        # Always return True so the plugin loads
        return True
