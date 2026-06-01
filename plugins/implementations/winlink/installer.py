"""
Winlink (Pat) Installer
========================
Handles first-run installation of Pat Winlink client
and its dependencies.

Docker Deployment Notes:
    Pat is a Go binary that can be installed from a
    GitHub release download without root. However the
    AX.25 tools require apt-get and thus root.

    For Docker, Pat can be downloaded directly to
    ~/.local/bin without any system package manager.
    This installer handles this case automatically.

    Optional: add to Dockerfile for system-wide install:
        RUN apt-get update && apt-get install -y pat

    This installer:
        - In Docker: downloads Pat binary from GitHub
          releases (no root required)
        - Outside Docker: tries apt, then download

Pat Winlink Installation Methods:
    1. apt-get (Debian/Ubuntu) — if available
    2. GitHub release download (works in Docker)
    3. AX.25 tools (optional, for packet radio)

Source: https://github.com/la5nta/pat
Website: https://getpat.io/
"""

import os
import sys
import re
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
                print(f"[Winlink][INSTALL] Marker write error: {e}") 

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                print(f"[Winlink][INSTALL] Marker read error: {e}")    
                return {}


class WinlinkInstaller(BaseInstaller):
    """
    Manages Pat Winlink client installation.

    Extends BaseInstaller for Docker-aware handling.

    Key difference from other installers:
        Pat can be installed without root by downloading
        a pre-built binary from GitHub releases. This
        makes it possible to install Pat even in Docker
        as a non-root user.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # Pat Winlink binary name
    PAT_BINARY = 'pat'

    # GitHub API for latest release info
    PAT_GITHUB_API = (
        'https://github.com/la5nta/pat.git'
        'releases/latest'
    )

    # Installation directory (user-writable, on PATH)
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

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

        self.pat_binary_path = (
            shutil.which(self.PAT_BINARY) or
            os.path.join(self.INSTALL_DIR, self.PAT_BINARY)
        )

        print(
            f"[Winlink][INSTALL] Installer init | "
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
                f"[Winlink][INSTALL] File not found: {cmd[0]} — {e}"
            )
        except subprocess.TimeoutExpired:
            return False, '', f"[Winlink][INSTALL] Timed out after {timeout}s"
        except Exception as e:
            return False, '', str(e)

    def is_installed(self):
        """
        Check if Pat is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        return (
            shutil.which(self.PAT_BINARY) is not None or
            os.path.isfile(self.pat_binary_path)
        )

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages available
        """
        print("[Winlink][INSTALL] Checking Python packages...")
        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )
        if failed and self.in_docker:
            print(
                f"[Winlink][INSTALL] INFO: Add to requirements.txt: "
                f"{', '.join(failed)}"
            )
        return len(failed) == 0

    def _install_via_apt(self):
        """
        Install Pat via apt-get.

        Uses self._sudo prefix. In Docker as non-root,
        this will return False and the installer will
        fall through to the GitHub release download
        which does NOT require root.

        Returns:
            bool: True if installation successful
        """
        print("[Winlink][INSTALL]  Installing Pat via apt-get...")

        if not shutil.which('apt-get'):
            print("[Winlink][INSTALL] apt-get not available")
            return False

        if self.in_docker and not self.is_root:
            print(
                "[Winlink][INSTALL] INFO: apt-get not available "
                "in Docker as non-root."
            )
            print(
                "[Winlink][INSTALL] INFO: Will download Pat binary "
                "from GitHub instead (no root required)."
            )
            return False

        # Update package list
        ok, _, stderr = self._run_system_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[Winlink][INSTALL] apt-get update failed: "
                f"{stderr[:150]}"
            )
            return False

        # Install Pat
        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'pat'
            ],
            timeout=300
        )

        if ok:
            print("[Winlink][INSTALL] ✓ Pat installed via apt-get")
            return True

        print(
            f"[Winlink][INSTALL] apt-get failed: {stderr[:200]}"
        )
        return False

    def _download_pat_release(self):
        """
        Download Pat binary from GitHub releases.

        This method works WITHOUT root and WITHOUT apt-get,
        making it suitable for Docker non-root containers.

        Downloads the appropriate binary for the current
        OS and architecture, extracts it, and installs
        it to ~/.local/bin/pat.

        Returns:
            bool: True if installation successful
        """
        print(
            "[Winlink][INSTALL] Downloading Pat from GitHub..."
        )

        try:
            # Query GitHub API for latest release
            req = urllib.request.Request(
                self.PAT_GITHUB_API,
                headers={
                    'User-Agent': 'HamRadioApp/1.0',
                    'Accept': (
                        'application/vnd.github.v3+json'
                    )
                }
            )
            with urllib.request.urlopen(
                req, timeout=30
            ) as response:
                release_data = json.loads(
                    response.read().decode()
                )

        except Exception as e:
            print(
                f"[Winlink][INSTALL] GitHub API error: {e}"
            )
            return False

        tag = release_data.get('tag_name', 'unknown')
        print(f"[Winlink][INSTALL] Latest release: {tag}")

        assets = release_data.get('assets', [])
        print(f"[Winlink][INSTALL] Available assets:")
        for asset in assets:
            print(f"  {asset['name']}")

        # Map architecture to release asset naming
        arch_lower = self._arch.lower()
        arch_patterns = []

        if arch_lower == 'x86_64':
            arch_patterns = ['amd64', 'x86_64']
        elif arch_lower in ('aarch64', 'arm64'):
            arch_patterns = ['arm64', 'aarch64']
        elif arch_lower.startswith('armv'):
            arch_patterns = ['armhf', 'arm']
        else:
            arch_patterns = [arch_lower]

        print(
            f"[Winlink][INSTALL] Platform: linux/{self._arch} "
            f"(patterns: {arch_patterns})"
        )

        # Find matching tar.gz asset
        download_url = None
        asset_name = None

        for pattern in arch_patterns:
            for asset in assets:
                name = asset['name'].lower()
                if (name.endswith('.tar.gz') and
                        'linux' in name and
                        pattern in name):
                    download_url = (
                        asset['browser_download_url']
                    )
                    asset_name = asset['name']
                    print(
                        f"[Winlink][INSTALL] ✓ url matched: "
                        f"{asset_name}"
                    )
                    break
            if download_url:
                break

        if not download_url:
            print(
                "[Winlink][INSTALL] ERROR: No matching url "
                f"for linux/{self._arch}"
            )
            return False

        # Download the archive
        import tempfile
        import tarfile

        download_dir = tempfile.mkdtemp(
            prefix='pat_install_'
        )

        try:
            archive_path = os.path.join(
                download_dir, asset_name
            )

            print(
                f"[Winlink][INSTALL] Downloading {asset_name}..."
            )
            urllib.request.urlretrieve(
                download_url, archive_path
            )

            size_kb = os.path.getsize(archive_path) / 1024
            print(
                f"[Winlink][INSTALL] ✓ Downloaded {size_kb:.0f} KB"
            )

            # Ensure install directory exists
            os.makedirs(self.INSTALL_DIR, exist_ok=True)

            # Extract Pat binary from archive
            print("[Winlink] Extracting Pat binary...")
            pat_installed = False

            with tarfile.open(archive_path, 'r:gz') as tar:
                members = tar.getmembers()
                print(
                    f"[Winlink][INSTALL] Archive contents:"
                )
                for m in members:
                    print(f"  {m.name}")

                for member in members:
                    filename = os.path.basename(
                        member.name
                    )
                    if filename == self.PAT_BINARY:
                        extracted = tar.extractfile(member)
                        if extracted:
                            dest = self.pat_binary_path
                            with open(dest, 'wb') as f:
                                f.write(extracted.read())
                            os.chmod(dest, 0o755)
                            size = os.path.getsize(dest)
                            print(
                                f"[Winlink][INSTALL] ✓ Pat installed: "
                                f"{dest} "
                                f"({size//1024} KB)"
                            )
                            pat_installed = True
                            break

            if not pat_installed:
                print(
                    "[Winlink][INSTALL] ERROR: 'pat' binary not "
                    "found in archive"
                )
                return False

            return True

        except Exception as e:
            print(
                f"[Winlink][INSTALL] Download/extract error: {e}"
            )
            traceback.print_exc()
            return False

        finally:
            shutil.rmtree(download_dir, ignore_errors=True)

    def install_ax25_tools(self):
        """
        Install AX.25 tools for packet radio support.

        Optional — non-fatal if installation fails.
        AX.25 tools are only needed for packet radio
        connections to Winlink gateways.

        Returns:
            bool: True if installed (non-fatal if False)
        """
        if self.in_docker and not self.is_root:
            print(
                "[Winlink][INSTALL] INFO: AX.25 tools require root. "
                "Add to Dockerfile if needed: "
                "RUN apt-get install -y ax25-tools ax25-apps"
            )
            return False

        if not shutil.which('apt-get'):
            return False

        print("[Winlink][INSTALL] Installing AX.25 tools...")
        ok, _, stderr = self._run_system_command(
            self._sudo + [
                'apt-get', 'install', '-y',
                'ax25-tools', 'ax25-apps'
            ],
            timeout=120
        )

        if ok:
            print("[Winlink][INSTALL] ✓ AX.25 tools installed")
        else:
            print(
                "[Winlink][INSTALL] INFO: AX.25 tools not available "
                "(optional, only needed for packet radio)"
            )

        return ok

    def get_version(self):
        """
        Get installed Pat version.

        Returns:
            str: Version string or None
        """
        binary = (
            shutil.which(self.PAT_BINARY) or
            (self.pat_binary_path
             if os.path.isfile(self.pat_binary_path)
             else None)
        )

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
                'pat_binary': self.pat_binary_path,
                'platform': platform.platform(),
                'arch': self._arch,
            }
        )

    def get_install_info(self):
        """Read installation marker."""
        return self.read_marker(self.INSTALL_MARKER)

    def run(self):
        """
        Execute the complete Pat installation process.

        Installation strategy:
            1. Check if already installed (skip)
            2. Check if Pat already in PATH (mark + skip)
            3. Try apt-get (skipped in Docker non-root)
            4. Download Pat binary from GitHub releases
               (works in Docker non-root — no root needed)
            5. Optionally install AX.25 tools (non-fatal)

        Note: Unlike other plugins, Pat can be installed
        in Docker as non-root by downloading the binary
        directly from GitHub releases.

        Returns:
            bool: True if Pat is installed
        """
        if self.is_installed():
            print("[Winlink][INSTALL] ✓ Already installed")
            return True

        if shutil.which(self.PAT_BINARY):
            version = self.get_version()
            self.write_install_marker('existing', version)
            print("[Winlink][INSTALL] ✓ Pat found in PATH")
            return True

        print("[Winlink][INSTALL] ==========================================")
        print("[Winlink][INSTALL]  Starting installation")
        print("[Winlink][INSTALL] ==========================================")

        # Step 1: Python packages
        print("\n[Winlink][INSTALL] Step 1: Python packages...")
        self.install_python_packages()

        # Step 2: Install Pat
        print("\n[Winlink][INSTALL] Step 2: Installing Pat Winlink...")
        success = False

        # Try apt-get first (will skip in Docker non-root)
        if self._package_manager == 'apt-get':
            success = self._install_via_apt()

        # Download from GitHub (works in Docker non-root)
        if not success:
            if self.in_docker and not self.is_root:
                print(
                    "[Winlink][INSTALL] INFO: Using GitHub release "
                    "download (no root required in Docker)"
                )
            success = self._download_pat_release()

        if not success:
            print(
                "\n[Winlink][INSTALL] ERROR: Pat installation failed"
            )
            print(
                "[Winlink][INSTALL] Manual install: "
                "https://getpat.io/"
            )
            return False

        # Step 3: AX.25 tools (optional, non-fatal)
        print(
            "\n[Winlink][INSTALL] Step 3: AX.25 tools (optional)..."
        )
        self.install_ax25_tools()

        # Write marker
        version = self.get_version()
        method = (
            'docker_download'
            if (self.in_docker and not self.is_root)
            else (self._package_manager or 'download')
        )
        self.write_install_marker(method, version)

        print(
            "\n[Winlink][INSTALL] =========================================="
        )
        print("[Winlink][INSTALL] ✓ Pat installation complete!")
        if version:
            print(f"[Winlink][INSTALL]   Version: {version}")
        print(
            f"[Winlink][INSTALL]   Binary: {self.pat_binary_path}"
        )
        print(
            "[Winlink][INSTALL] =========================================="
            "\n"
        )

        return True
