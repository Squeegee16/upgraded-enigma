"""
Plugin Base Installer
======================
Shared base class for all plugin installers.

Key Design Decisions for Docker:
    1. All Python packages are pre-installed in the Docker
       image via requirements.txt at build time.
    2. At runtime the container user (hamradio, UID 1000)
       has NO write access to /opt/venv.
    3. Plugin installers must NEVER attempt pip installs
       at runtime in Docker — they will always fail with
       Permission denied.
    4. System packages (apt-get) also cannot be installed
       at runtime without sudo/root.
    5. The PLUGIN_SKIP_PIP_INSTALL env var signals that
       we are in a Docker environment and should skip
       pip operations.

Correct approach:
    - Add all dependencies to requirements.txt
    - Rebuild the Docker image when deps change
    - At runtime: only check if packages are importable

Author: Ham Radio App Team
Version: 1.0.0
"""

import os
import sys
import json
import shutil
import subprocess
import platform
from datetime import datetime


class BaseInstaller:
    """
    Base installer with Docker-aware package management.

    Provides safe wrappers around pip and system package
    managers that correctly handle Docker environments
    where the runtime user cannot install packages.
    """

    def __init__(self):
        """
        Detect runtime environment.

        Sets flags for Docker mode, root status,
        and sudo availability.
        """
        # Running as root?
        try:
            self.is_root = (os.getuid() == 0)
        except AttributeError:
            self.is_root = False

        # sudo available?
        self.sudo_available = shutil.which('sudo') is not None

        # Build sudo prefix
        if self.is_root:
            self._sudo = []
        elif self.sudo_available:
            self._sudo = ['sudo']
        else:
            self._sudo = []

        # Are we in Docker with pre-installed packages?
        # The Dockerfile sets PLUGIN_SKIP_PIP_INSTALL=true
        self.in_docker = (
            os.environ.get('PLUGIN_SKIP_PIP_INSTALL', '')
            .lower() == 'true'
        )

        # Also detect Docker by checking for /.dockerenv
        if not self.in_docker:
            self.in_docker = os.path.exists('/.dockerenv')

        if self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"Docker environment detected — "
                f"pip installs will be skipped"
            )

    def pip_install(self, package):
        """
        Install a Python package if not already installed.

        In Docker environments, skips installation and
        only checks if the package is importable.
        If not importable in Docker, logs a warning
        directing the user to add it to requirements.txt.

        Args:
            package: Package name to install

        Returns:
            bool: True if package is available
        """
        # First check if package is already importable
        # Strip version specifiers for import check
        import_name = package.split('==')[0] \
            .split('>=')[0] \
            .split('<=')[0] \
            .strip()

        # Handle packages with different import names
        import_name_map = {
            'pillow': 'PIL',
            'Pillow': 'PIL',
            'pyopenssl': 'OpenSSL',
            'PyOpenSSL': 'OpenSSL',
            'python-dotenv': 'dotenv',
            'pynmea2': 'pynmea2',
        }
        actual_import = import_name_map.get(
            import_name, import_name
        )

        # Check importability
        if self._is_importable(actual_import):
            print(
                f"[{self.__class__.__name__}] "
                f"✓ {package} already available"
            )
            return True

        # In Docker, we cannot install — report and skip
        if self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"WARNING: {package} not available in Docker. "
                f"Add to requirements.txt and rebuild image."
            )
            # Return True to not block plugin loading
            # The plugin will handle missing deps gracefully
            return True

        # Outside Docker — attempt pip install
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip',
                 'install', '--quiet', package],
                check=True,
                capture_output=True,
                timeout=120
            )
            print(
                f"[{self.__class__.__name__}] "
                f"✓ Installed: {package}"
            )
            return True

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else ''
            if 'Permission denied' in stderr:
                print(
                    f"[{self.__class__.__name__}] "
                    f"WARNING: Permission denied installing "
                    f"{package}. Add to requirements.txt."
                )
            else:
                print(
                    f"[{self.__class__.__name__}] "
                    f"WARNING: {package} install failed: "
                    f"{stderr[:80]}"
                )
            return False

    def _is_importable(self, module_name):
        """
        Check if a Python module can be imported.

        Args:
            module_name: Module name to test

        Returns:
            bool: True if module is importable
        """
        import importlib.util
        try:
            spec = importlib.util.find_spec(module_name)
            return spec is not None
        except (ModuleNotFoundError, ValueError):
            return False

    def install_python_packages(self, packages):
        """
        Install a list of Python packages.

        In Docker, only checks availability.
        Outside Docker, attempts pip install for each.

        Args:
            packages: List of package name strings

        Returns:
            tuple: (available_count, unavailable_list)
        """
        if self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"Docker mode: checking package availability..."
            )
        else:
            print(
                f"[{self.__class__.__name__}] "
                f"Installing Python packages..."
            )

        unavailable = []

        for package in packages:
            ok = self.pip_install(package)
            if not ok:
                unavailable.append(package)

        available = len(packages) - len(unavailable)

        if unavailable and self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"INFO: Add these to requirements.txt and "
                f"rebuild: {unavailable}"
            )

        return available, unavailable

    def apt_install(self, *packages):
        """
        Install system packages via apt-get.

        In Docker without root/sudo, this will fail.
        Packages that need apt-get should be added to
        the Dockerfile RUN apt-get block.

        Args:
            *packages: Package names to install

        Returns:
            bool: True if installed successfully
        """
        if not shutil.which('apt-get'):
            print(
                f"[{self.__class__.__name__}] "
                f"apt-get not available"
            )
            return False

        if self.in_docker and not self.is_root:
            print(
                f"[{self.__class__.__name__}] "
                f"INFO: Cannot apt-get in Docker as non-root. "
                f"Add to Dockerfile: apt-get install "
                f"{' '.join(packages)}"
            )
            return False

        try:
            # Update
            subprocess.run(
                self._sudo + ['apt-get', 'update', '-q'],
                check=True,
                capture_output=True,
                timeout=60
            )
            # Install
            subprocess.run(
                self._sudo + [
                    'apt-get', 'install', '-y'
                ] + list(packages),
                check=True,
                capture_output=True,
                timeout=300
            )
            print(
                f"[{self.__class__.__name__}] "
                f"✓ apt installed: {', '.join(packages)}"
            )
            return True

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else ''
            print(
                f"[{self.__class__.__name__}] "
                f"apt-get failed: {stderr[:150]}"
            )
            return False
        except FileNotFoundError as e:
            print(
                f"[{self.__class__.__name__}] "
                f"Command not found: {e}"
            )
            return False

    def write_marker(self, marker_path, extra_data=None):
        """Write installation marker file."""
        data = {
            'installed': True,
            'timestamp': datetime.utcnow().isoformat(),
            'platform': platform.platform(),
            'python': sys.version,
            'in_docker': self.in_docker,
        }
        if extra_data:
            data.update(extra_data)

        try:
            os.makedirs(
                os.path.dirname(marker_path),
                exist_ok=True
            )
            with open(marker_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(
                f"[{self.__class__.__name__}] "
                f"Marker write error: {e}"
            )

    def read_marker(self, marker_path):
        """Read installation marker file."""
        if not os.path.exists(marker_path):
            return {}
        try:
            with open(marker_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
