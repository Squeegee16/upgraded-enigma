"""
OpenWebRX Dependency Installer
================================
Handles installation of OpenWebRX and its required
dependencies on first run.

OpenWebRX Installation Methods (in priority order):
    1. apt-get via official repository (Debian/Ubuntu)
    2. Flatpak from Flathub (universal Linux)
    3. pip install (fallback)

All methods handle Docker environments correctly by
detecting whether sudo is available and whether the
process is running as root.

Python Dependencies:
    - requests   : HTTP client for API communication
    - psutil     : Process management and monitoring
    - websockets : WebSocket client for live data
    - aiohttp    : Async HTTP client

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
from pathlib import Path


class OpenWebRXInstaller:
    """
    Manages OpenWebRX installation and verification.

    Supports multiple installation methods with automatic
    fallback. Detects Docker/root environments and adjusts
    sudo usage accordingly. Tracks installation state via
    a JSON marker file.
    """

    # Installation state marker file
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # OpenWebRX Docker image
    DOCKER_IMAGE = 'jketterl/openwebrx:latest'

    # OpenWebRX Debian/Ubuntu repository
    DEBIAN_REPO = 'https://repo.openwebrx.de/debian/'

    # Flathub application ID
    FLATPAK_APP_ID = 'de.openwebrx.OpenWebRX'

    # Default HTTP port for OpenWebRX web interface
    DEFAULT_HTTP_PORT = 8073

    # Required Python packages for plugin communication
    REQUIRED_PYTHON_PACKAGES = [
        'requests',
        'psutil',
        'websockets',
        'aiohttp',
    ]

    def __init__(self):
        """
        Initialise installer with environment detection.

        Detects:
            - Running as root (common in Docker)
            - sudo availability
            - Available package managers
            - System architecture
        """
        self.plugin_dir = os.path.dirname(__file__)

        # -------------------------------------------------------
        # Environment detection
        # -------------------------------------------------------

        # Check if running as root
        # In Docker containers the process often runs as root
        # or as a non-root user without sudo
        try:
            self.is_root = (os.getuid() == 0)
        except AttributeError:
            # Windows fallback (not a target platform)
            self.is_root = False

        # Check if sudo is available
        self.sudo_available = shutil.which('sudo') is not None

        # Build sudo prefix for system commands
        # Root: no prefix needed
        # Non-root with sudo: ['sudo']
        # Non-root without sudo: [] (will fail for sys installs)
        if self.is_root:
            self._sudo = []
            print(
                "[OpenWebRX] Running as root "
                "(Docker/elevated mode)"
            )
        elif self.sudo_available:
            self._sudo = ['sudo']
        else:
            self._sudo = []
            print(
                "[OpenWebRX] WARNING: sudo not available. "
                "System package installs may fail."
            )

        # Detect package manager
        self._package_manager = self._detect_package_manager()

        # System architecture for downloads
        self._arch = platform.machine()

        print(
            f"[OpenWebRX] Package manager: "
            f"{self._package_manager or 'none detected'}"
        )

    def _detect_package_manager(self):
        """
        Detect available system package manager.

        Returns:
            str: Package manager name or None
        """
        managers = ['apt-get', 'dnf', 'yum', 'pacman', 'zypper']
        for manager in managers:
            if shutil.which(manager):
                return manager
        return None

    def _run_command(self, cmd, timeout=300, capture=True):
        """
        Execute a shell command with error handling.

        Handles missing binaries gracefully instead of
        raising FileNotFoundError.

        Args:
            cmd: Command list to execute
            timeout: Command timeout in seconds
            capture: Capture stdout/stderr if True

        Returns:
            tuple: (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=capture,
                timeout=timeout
            )
            stdout = result.stdout.decode() \
                if capture and result.stdout else ''
            return True, stdout, ''

        except FileNotFoundError as e:
            # Binary not found (e.g. sudo, apt-get)
            return False, '', f"Command not found: {cmd[0]}: {e}"

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() \
                if e.stderr else str(e)
            return False, '', stderr

        except subprocess.TimeoutExpired:
            return False, '', f"Command timed out after {timeout}s"

        except Exception as e:
            return False, '', str(e)

    def is_installed(self):
        """
        Check if OpenWebRX is installed and marker exists.

        Returns:
            bool: True if installation marker exists and
                  OpenWebRX is accessible
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Verify installation based on available method
        info = self.get_install_info()
        method = info.get('method', '')

        if method == 'docker':
            return self._check_docker_image_exists()
        elif method in ('apt', 'apt-get'):
            return shutil.which('openwebrx') is not None
        elif method == 'flatpak':
            return self._check_flatpak_installed()
        elif method == 'pip':
            return self._check_pip_installed()
        else:
            # Marker exists but method unknown
            # Check all possibilities
            return (
                shutil.which('openwebrx') is not None or
                self._check_docker_image_exists() or
                self._check_flatpak_installed()
            )

    def _check_docker_image_exists(self):
        """
        Check if the OpenWebRX Docker image is pulled.

        Returns:
            bool: True if Docker image is available locally
        """
        if not shutil.which('docker'):
            return False

        success, stdout, _ = self._run_command(
            ['docker', 'images', '-q', self.DOCKER_IMAGE],
            timeout=10
        )
        return success and bool(stdout.strip())

    def _check_flatpak_installed(self):
        """
        Check if OpenWebRX is installed via Flatpak.

        Returns:
            bool: True if Flatpak app is installed
        """
        if not shutil.which('flatpak'):
            return False

        success, stdout, _ = self._run_command(
            ['flatpak', 'list', '--app', '--columns=application'],
            timeout=15
        )
        return success and self.FLATPAK_APP_ID in stdout

    def _check_pip_installed(self):
        """
        Check if OpenWebRX pip package is installed.

        Returns:
            bool: True if importable
        """
        try:
            import openwebrx
            return True
        except ImportError:
            return False

    def install_python_packages(self):
        """
        Install required Python packages via pip.

        Uses the current Python interpreter (sys.executable)
        to ensure packages land in the active virtual
        environment.

        Returns:
            bool: True if all packages installed successfully
        """
        print("[OpenWebRX] Installing Python packages...")
        failed = []

        for package in self.REQUIRED_PYTHON_PACKAGES:
            print(f"[OpenWebRX] Installing {package}...")
            success, _, stderr = self._run_command(
                [
                    sys.executable, '-m', 'pip',
                    'install', '--quiet', package
                ],
                timeout=120
            )

            if success:
                print(f"[OpenWebRX] ✓ {package}")
            else:
                print(
                    f"[OpenWebRX] WARNING: {package} "
                    f"failed: {stderr[:100]}"
                )
                failed.append(package)

        if failed:
            print(
                f"[OpenWebRX] WARNING: Failed packages: "
                f"{failed}"
            )
            return False

        return True

    def _install_via_apt(self):
        """
        Install OpenWebRX via apt-get.

        Attempts to add the official OpenWebRX Debian
        repository and install. Falls back to Flatpak
        if apt installation fails.

        Returns:
            bool: True if installation successful
        """
        print("[OpenWebRX] Installing via apt-get...")

        if not shutil.which('apt-get'):
            print("[OpenWebRX] apt-get not available")
            return self._install_via_flatpak()

        try:
            # Install prerequisite tools
            print("[OpenWebRX] Installing prerequisites...")
            success, _, stderr = self._run_command(
                self._sudo + [
                    'apt-get', 'install', '-y',
                    'apt-transport-https',
                    'curl',
                    'gnupg',
                    'lsb-release'
                ],
                timeout=120
            )
            if not success:
                print(
                    f"[OpenWebRX] Prerequisites failed: "
                    f"{stderr[:100]}"
                )
                return self._install_via_flatpak()

            # Add OpenWebRX GPG key
            print("[OpenWebRX] Adding repository key...")
            if shutil.which('curl'):
                key_success, key_data, _ = self._run_command(
                    [
                        'curl', '-fsSL',
                        'https://repo.openwebrx.de/debian/'
                        'key.gpg.txt'
                    ],
                    timeout=30
                )

                if key_success and key_data:
                    # Add key via apt-key
                    key_proc = subprocess.Popen(
                        self._sudo + ['apt-key', 'add', '-'],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    key_proc.communicate(
                        input=key_data.encode()
                    )

            # Detect distribution codename
            distro_success, distro, _ = self._run_command(
                ['lsb_release', '-cs'],
                timeout=5
            )
            distro_name = distro.strip() if distro_success \
                else 'bullseye'

            # Add repository
            print(
                f"[OpenWebRX] Adding repository "
                f"for {distro_name}..."
            )
            repo_line = (
                f"deb [arch=amd64] "
                f"{self.DEBIAN_REPO} "
                f"{distro_name} main\n"
            )

            list_path = '/tmp/openwebrx.list'
            with open(list_path, 'w') as f:
                f.write(repo_line)

            self._run_command(
                self._sudo + [
                    'cp', list_path,
                    '/etc/apt/sources.list.d/openwebrx.list'
                ],
                timeout=10
            )

            # Update package list
            print("[OpenWebRX] Updating package list...")
            success, _, stderr = self._run_command(
                self._sudo + ['apt-get', 'update', '-q'],
                timeout=120
            )
            if not success:
                print(
                    f"[OpenWebRX] apt-get update failed: "
                    f"{stderr[:100]}"
                )
                return self._install_via_flatpak()

            # Install OpenWebRX
            print("[OpenWebRX] Installing openwebrx package...")
            success, _, stderr = self._run_command(
                self._sudo + [
                    'apt-get', 'install', '-y', 'openwebrx'
                ],
                timeout=300
            )

            if success:
                print("[OpenWebRX] ✓ Installed via apt-get")
                return True
            else:
                print(
                    f"[OpenWebRX] apt install failed: "
                    f"{stderr[:200]}"
                )
                return self._install_via_flatpak()

        except Exception as e:
            print(f"[OpenWebRX] apt installation error: {e}")
            return self._install_via_flatpak()

    def _install_via_docker(self):
        """
        Pull and set up OpenWebRX Docker image.

        Creates a wrapper script so the plugin can
        manage the container lifecycle.

        Returns:
            bool: True if image pulled successfully
        """
        print("[OpenWebRX] Installing via Docker...")

        if not shutil.which('docker'):
            print("[OpenWebRX] Docker not available")
            return self._install_via_flatpak()

        # Pull the Docker image
        print(
            f"[OpenWebRX] Pulling {self.DOCKER_IMAGE}..."
        )
        success, _, stderr = self._run_command(
            ['docker', 'pull', self.DOCKER_IMAGE],
            timeout=300
        )

        if success:
            print("[OpenWebRX] ✓ Docker image pulled")
            return True
        else:
            print(
                f"[OpenWebRX] Docker pull failed: "
                f"{stderr[:200]}"
            )
            return self._install_via_flatpak()

    def _install_via_flatpak(self):
        """
        Install OpenWebRX via Flatpak from Flathub.

        Creates a wrapper script at ~/.local/bin/openwebrx
        so the plugin can launch OpenWebRX normally.

        Returns:
            bool: True if installation successful
        """
        print("[OpenWebRX] Installing via Flatpak...")

        if not shutil.which('flatpak'):
            print("[OpenWebRX] Flatpak not available")
            return self._install_via_pip()

        # Add Flathub remote if not already added
        print("[OpenWebRX] Adding Flathub remote...")
        self._run_command(
            [
                'flatpak', 'remote-add',
                '--if-not-exists', 'flathub',
                'https://flathub.org/repo/flathub.flatpakrepo'
            ],
            timeout=30
        )

        # Install from Flathub
        print(
            f"[OpenWebRX] Installing "
            f"{self.FLATPAK_APP_ID}..."
        )
        success, _, stderr = self._run_command(
            [
                'flatpak', 'install',
                '-y', 'flathub',
                self.FLATPAK_APP_ID
            ],
            timeout=300
        )

        if not success:
            print(
                f"[OpenWebRX] Flatpak install failed: "
                f"{stderr[:200]}"
            )
            return self._install_via_pip()

        # Create CLI wrapper script
        wrapper_dir = os.path.expanduser('~/.local/bin')
        os.makedirs(wrapper_dir, exist_ok=True)

        wrapper_path = os.path.join(wrapper_dir, 'openwebrx')
        wrapper_content = (
            '#!/bin/bash\n'
            f'exec flatpak run {self.FLATPAK_APP_ID} "$@"\n'
        )

        try:
            with open(wrapper_path, 'w') as f:
                f.write(wrapper_content)
            os.chmod(wrapper_path, 0o755)
            print(
                f"[OpenWebRX] ✓ Flatpak wrapper: "
                f"{wrapper_path}"
            )
        except Exception as e:
            print(
                f"[OpenWebRX] Wrapper creation error: {e}"
            )

        print("[OpenWebRX] ✓ Installed via Flatpak")
        return True

    def _install_via_pip(self):
        """
        Install OpenWebRX via pip as a last resort.

        Note: The pip package may not include all features
        of a full OpenWebRX installation.

        Returns:
            bool: True if installation successful
        """
        print("[OpenWebRX] Installing via pip (fallback)...")

        success, _, stderr = self._run_command(
            [
                sys.executable, '-m', 'pip',
                'install', '--quiet', 'openwebrx'
            ],
            timeout=120
        )

        if success:
            print("[OpenWebRX] ✓ Installed via pip")
            return True
        else:
            print(
                f"[OpenWebRX] pip install failed: "
                f"{stderr[:200]}"
            )
            print(
                "[OpenWebRX] All installation methods failed."
            )
            print(
                "[OpenWebRX] Please install manually: "
                "https://openwebrx.de/"
            )
            return False

    def write_install_marker(self, method, version=None):
        """
        Write installation marker with metadata.

        Args:
            method: Installation method string
            version: Version string if available
        """
        marker_data = {
            'installed': True,
            'method': method,
            'version': version,
            'platform': platform.platform(),
            'arch': self._arch,
            'python_version': sys.version,
            'docker_image': (
                self.DOCKER_IMAGE
                if method == 'docker' else None
            ),
            'timestamp': str(
                __import__('datetime').datetime.utcnow()
            )
        }

        try:
            os.makedirs(
                os.path.dirname(self.INSTALL_MARKER),
                exist_ok=True
            )
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print("[OpenWebRX] ✓ Installation marker written")
        except Exception as e:
            print(
                f"[OpenWebRX] WARNING: Marker write "
                f"failed: {e}"
            )

    def get_install_info(self):
        """
        Read installation marker data.

        Returns:
            dict: Marker contents or empty dict
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return {}
        try:
            with open(self.INSTALL_MARKER, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def get_version(self):
        """
        Attempt to get installed OpenWebRX version.

        Returns:
            str: Version string or None
        """
        # Try binary
        binary = shutil.which('openwebrx')
        if binary:
            success, stdout, _ = self._run_command(
                [binary, '--version'],
                timeout=10
            )
            if success and stdout:
                return stdout.strip()

        # Try Flatpak
        if self._check_flatpak_installed():
            success, stdout, _ = self._run_command(
                [
                    'flatpak', 'info',
                    '--show-metadata',
                    self.FLATPAK_APP_ID
                ],
                timeout=15
            )
            if success and stdout:
                for line in stdout.split('\n'):
                    if 'version' in line.lower():
                        return line.split('=')[-1].strip()

        # Try pip
        try:
            import openwebrx
            return getattr(openwebrx, '__version__', 'pip')
        except ImportError:
            pass

        return None

def run(self):
        """
        Execute first-run installation.

        In Docker: checks package availability only,
        does not attempt pip or apt installs.
        Outside Docker: attempts full installation.

        Returns:
            bool: True always (plugin loads regardless)
        """
        # Already installed
        if self.is_installed():
            print("[OpenWebRX] ✓ Already installed")
            return True

        # Binary already available
        if shutil.which('openwebrx'):
            version = self.get_version()
            self.write_install_marker('existing', version)
            return True

        print("[OpenWebRX] ========================================")
        print("[OpenWebRX] First-run installation check")
        print("[OpenWebRX] ========================================")

        # Step 1: Python packages
        print("\n[OpenWebRX] Step 1: Python packages...")
        self.install_python_packages()
        # Always continue regardless of result

        # Step 2: OpenWebRX application
        print(
            f"\n[OpenWebRX] Step 2: Installing OpenWebRX..."
        )

        if self.in_docker and not self.is_root:
            # In Docker as non-root: cannot install system apps
            print(
                "[OpenWebRX] INFO: Running in Docker as "
                "non-root user."
            )
            print(
                "[OpenWebRX] INFO: OpenWebRX must be installed "
                "in the Docker image."
            )
            print(
                "[OpenWebRX] INFO: Add to Dockerfile: "
                "apt-get install openwebrx"
            )
            print(
                "[OpenWebRX] INFO: Or use Docker-in-Docker "
                "with the OpenWebRX container."
            )
            print(
                "[OpenWebRX] INFO: Plugin UI will load. "
                "Use the Install button when OpenWebRX "
                "is available."
            )
            # Write marker so we don't retry on every start
            self.write_install_marker(
                'docker_pending',
                {'note': 'Awaiting Docker image rebuild'}
            )
            # Return True so plugin still loads
            return True

        # Outside Docker: attempt installation
        success = False

        if self._package_manager in ('apt-get', 'apt'):
            success = self._install_via_apt()
        elif shutil.which('docker'):
            success = self._install_via_docker()
        elif shutil.which('flatpak'):
            success = self._install_via_flatpak()
        else:
            success = self._install_via_pip()

        if success:
            version = self.get_version()
            self.write_install_marker(
                self._package_manager or 'unknown',
                version
            )
            print("[OpenWebRX] ✓ Installation complete!")
        else:
            print(
                "[OpenWebRX] Installation failed. "
                "Plugin UI will still load."
            )

        # Always return True — let the plugin load
        return True

        return True
