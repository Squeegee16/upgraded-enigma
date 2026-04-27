"""
Plugin Base Installer
======================
Shared base class for all plugin installers.

Provides Docker-aware package management that correctly
handles the case where the runtime user cannot install
packages into the virtual environment.

Docker Deployment Model:
    - All Python packages are pre-installed at image
      build time via requirements.txt (running as root)
    - The runtime user (hamradio, UID 1000) has READ
      access to /opt/venv but cannot WRITE to it
    - The env var PLUGIN_SKIP_PIP_INSTALL=true signals
      that we are in Docker and should skip pip installs
    - apt-get installs are also skipped for non-root users

Usage:
    class MyInstaller(BaseInstaller):
        INSTALL_MARKER = '/path/to/.installed'
        REQUIRED_PACKAGES = ['requests', 'psutil']

        def run(self):
            if self.is_installed():
                return True
            available, failed = self.install_python_packages(
                self.REQUIRED_PACKAGES
            )
            ...

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

    Provides safe wrappers for pip install and apt-get
    that correctly detect and handle Docker environments
    where the runtime user cannot install packages.
    """

    def __init__(self):
        """
        Detect runtime environment on initialisation.

        Sets the following instance attributes:
            is_root       - True if running as UID 0
            sudo_available - True if sudo binary exists
            _sudo         - Prefix list for system commands
            in_docker     - True if Docker environment detected
        """
        # Check if running as root (UID 0)
        try:
            self.is_root = (os.getuid() == 0)
        except AttributeError:
            # Windows - not a supported platform
            self.is_root = False

        # Check for sudo availability
        self.sudo_available = shutil.which('sudo') is not None

        # Build prefix for system commands
        # Root:             no prefix needed
        # Non-root + sudo:  ['sudo']
        # Non-root, no sudo: [] (system installs will fail)
        if self.is_root:
            self._sudo = []
        elif self.sudo_available:
            self._sudo = ['sudo']
        else:
            self._sudo = []

        # Detect Docker environment via two methods:
        # 1. Environment variable set in Dockerfile
        # 2. Presence of /.dockerenv file
        env_flag = os.environ.get(
            'PLUGIN_SKIP_PIP_INSTALL', ''
        ).lower() == 'true'

        dockerenv_exists = os.path.exists('/.dockerenv')

        self.in_docker = env_flag or dockerenv_exists

    def pip_install(self, package):
        """
        Install a Python package if not already available.

        In Docker environments this method only checks
        whether the package is importable. If it is not
        importable in Docker, a warning is logged
        directing the operator to add it to requirements.txt
        and rebuild the image.

        Outside Docker, pip install is attempted normally.

        Args:
            package: Package name string, may include
                     version specifier (e.g. 'requests==2.31')

        Returns:
            bool: True if package is available or
                  installation succeeded
        """
        # Normalise package name for import checking
        # Strip version specifiers: requests==2.31 -> requests
        import_name = package \
            .split('==')[0] \
            .split('>=')[0] \
            .split('<=')[0] \
            .split('[')[0] \
            .strip()

        # Some packages have different import names
        import_name_map = {
            'pillow': 'PIL',
            'Pillow': 'PIL',
            'pyopenssl': 'OpenSSL',
            'PyOpenSSL': 'OpenSSL',
            'python-dotenv': 'dotenv',
            'scikit-learn': 'sklearn',
            'beautifulsoup4': 'bs4',
        }
        actual_import = import_name_map.get(
            import_name, import_name
        )

        # Check if already importable
        if self._is_importable(actual_import):
            return True

        # Docker environment: skip install, log guidance
        if self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"INFO: {package} not in Docker image. "
                f"Add to requirements.txt and rebuild."
            )
            # Return True so plugin loading is not blocked
            return True

        # Outside Docker: attempt pip install
        try:
            result = subprocess.run(
                [
                    sys.executable, '-m', 'pip',
                    'install', '--quiet', package
                ],
                check=True,
                capture_output=True,
                timeout=120
            )
            print(
                f"[{self.__class__.__name__}] "
                f"✓ pip installed: {package}"
            )
            return True

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(
                'utf-8', errors='replace'
            ) if e.stderr else ''

            if 'Permission denied' in stderr:
                print(
                    f"[{self.__class__.__name__}] "
                    f"WARNING: Permission denied installing "
                    f"{package}. Add to requirements.txt."
                )
            else:
                print(
                    f"[{self.__class__.__name__}] "
                    f"WARNING: pip {package} failed: "
                    f"{stderr[:100]}"
                )
            return False

        except Exception as e:
            print(
                f"[{self.__class__.__name__}] "
                f"WARNING: pip {package} error: {e}"
            )
            return False

    def _is_importable(self, module_name):
        """
        Check whether a Python module can be imported.

        Uses importlib.util.find_spec() which does not
        actually execute the module.

        Args:
            module_name: Module name to check

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

        Calls pip_install() for each package and
        collects results. In Docker, only availability
        is checked rather than actual installation.

        Args:
            packages: List of package name strings

        Returns:
            tuple: (available_count: int, failed_list: list)
        """
        if self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"Docker mode: checking package availability..."
            )
        else:
            print(
                f"[{self.__class__.__name__}] "
                f"Installing {len(packages)} package(s)..."
            )

        failed = []
        for package in packages:
            ok = self.pip_install(package)
            if not ok:
                failed.append(package)

        available = len(packages) - len(failed)

        if failed and self.in_docker:
            print(
                f"[{self.__class__.__name__}] "
                f"INFO: Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        return available, failed

    def write_marker(self, marker_path, extra_data=None):
        """
        Write an installation marker JSON file.

        Stores installation metadata including timestamp,
        platform information, and any extra data provided
        by the calling installer.

        Args:
            marker_path: Absolute path for the marker file
            extra_data:  Optional dict of additional fields
                         to include in the marker file.
                         Defaults to None.

        Note:
            The parameter is named extra_data (not extra)
            to avoid confusion with Python's **kwargs syntax.
        """
        data = {
            'installed': True,
            'timestamp': datetime.utcnow().isoformat(),
            'platform': platform.platform(),
            'python': sys.version,
            'in_docker': self.in_docker,
        }

        # Merge in any additional data from the subclass
        if extra_data and isinstance(extra_data, dict):
            data.update(extra_data)

        try:
            # Create parent directory if it does not exist
            marker_dir = os.path.dirname(marker_path)
            if marker_dir:
                os.makedirs(marker_dir, exist_ok=True)

            with open(marker_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(
                f"[{self.__class__.__name__}] "
                f"WARNING: Marker write failed: {e}"
            )

    def read_marker(self, marker_path):
        """
        Read an installation marker JSON file.

        Args:
            marker_path: Absolute path to the marker file

        Returns:
            dict: Parsed marker contents, or empty dict
                  if file does not exist or is unreadable
        """
        if not os.path.exists(marker_path):
            return {}

        try:
            with open(marker_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(
                f"[{self.__class__.__name__}] "
                f"WARNING: Marker read failed: {e}"
            )
            return {}

    def apt_install(self, *packages):
        """
        Install system packages via apt-get.

        Skips installation in Docker as non-root since
        the container user cannot run apt-get. Logs
        the Dockerfile RUN instruction needed instead.

        Args:
            *packages: Package name strings to install

        Returns:
            bool: True if packages installed successfully
        """
        if not shutil.which('apt-get'):
            print(
                f"[{self.__class__.__name__}] "
                f"apt-get not available on this system"
            )
            return False

        if self.in_docker and not self.is_root:
            print(
                f"[{self.__class__.__name__}] "
                f"INFO: Cannot apt-get in Docker as non-root."
                f" Add to Dockerfile: "
                f"RUN apt-get install -y "
                f"{' '.join(packages)}"
            )
            return False

        try:
            subprocess.run(
                self._sudo + ['apt-get', 'update', '-q'],
                check=True,
                capture_output=True,
                timeout=60
            )
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
            stderr = e.stderr.decode(
                'utf-8', errors='replace'
            ) if e.stderr else str(e)
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
