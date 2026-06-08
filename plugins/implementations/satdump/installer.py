"""
SatDump Installer
==================
Handles first-run installation of SatDump and dependencies.

Installation Method:
    Downloads and installs the official SatDump .deb package
    directly from the SatDump GitHub releases page.

    This approach is used because:
        - There is no active apt repository for SatDump
        - The official .deb packages are pre-built and tested
        - .deb installation handles all system dependencies
          via dpkg/apt dependency resolution

    Package Source:
        https://github.com/SatDump/SatDump/releases/

    ARM64 (Raspberry Pi 4/5):
        satdump_1.2.2_arm64.deb

    AMD64 (x86_64 PC/server):
        satdump_1.2.2_amd64.deb

    .deb Installation Process:
        1. Detect system architecture (arm64 / amd64)
        2. Download .deb from GitHub releases
        3. Install with dpkg -i
        4. Fix any missing dependencies with apt-get -f install
        5. Verify satdump binary is executable

Docker Notes:
    In Docker as non-root (hamradio user), dpkg cannot
    be run directly. The installer detects this and logs
    clear Dockerfile instructions instead.

    Add to Dockerfile (ARM64 / Raspberry Pi):
        RUN curl -fsSL -o /tmp/satdump.deb \\
            https://github.com/SatDump/SatDump/releases/download/1.2.2/satdump_1.2.2_arm64.deb && \\
            dpkg -i /tmp/satdump.deb || \\
            apt-get install -f -y && \\
            rm /tmp/satdump.deb

    Add to Dockerfile (AMD64):
        RUN curl -fsSL -o /tmp/satdump.deb \\
            https://github.com/SatDump/SatDump/releases/download/1.2.2/satdump_1.2.2_amd64.deb && \\
            dpkg -i /tmp/satdump.deb || \\
            apt-get install -f -y && \\
            rm /tmp/satdump.deb

Author: Ham Radio App Team
Version: 1.0.0
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import urllib.request
import tempfile
from pathlib import Path
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
                if (
                    self.is_root or
                    not self.sudo_available
                )
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
            if extra_data and isinstance(
                extra_data, dict
            ):
                data.update(extra_data)
            try:
                os.makedirs(
                    os.path.dirname(path),
                    exist_ok=True
                )
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(
                    f"[SatDump] Marker error: {e}"
                )

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


# ---------------------------------------------------------------
# SatDump release configuration
# Update SATDUMP_VERSION and URLs when a new release is
# available on https://github.com/SatDump/SatDump/releases
# ---------------------------------------------------------------

SATDUMP_VERSION = '1.2.2'

SATDUMP_RELEASE_BASE = (
    f'https://github.com/SatDump/SatDump/releases/'
    f'download/{SATDUMP_VERSION}/'
)

# Architecture-specific .deb package URLs
SATDUMP_DEB_URLS = {
    'aarch64': (
        f'{SATDUMP_RELEASE_BASE}'
        f'satdump_{SATDUMP_VERSION}_arm64.deb'
    ),
    'arm64': (
        f'{SATDUMP_RELEASE_BASE}'
        f'satdump_{SATDUMP_VERSION}_arm64.deb'
    ),
    'x86_64': (
        f'{SATDUMP_RELEASE_BASE}'
        f'satdump_{SATDUMP_VERSION}_amd64.deb'
    ),
    'amd64': (
        f'{SATDUMP_RELEASE_BASE}'
        f'satdump_{SATDUMP_VERSION}_amd64.deb'
    ),
}

# Fallback: GitHub API URL for fetching latest release info
SATDUMP_RELEASES_API = (
    'https://api.github.com/repos/'
    'SatDump/SatDump/releases/latest'
)


class SatDumpInstaller(BaseInstaller):
    """
    Manages SatDump installation via official .deb package.
    """

    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    SATDUMP_BINARY = 'satdump'
    SATDUMP_UI_BINARY = 'satdump-ui'

    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
        'Pillow',
        'watchdog',
    ]

    OPTIONAL_PACKAGES = [
        'ephem',
        'pyorbital',
    ]

    def __init__(self):
        """Initialise installer with environment detection."""
        super().__init__()

        self._arch = platform.machine().lower()
        self._package_manager = (
            self._detect_package_manager()
        )

        # -------------------------------------------------------
        # satdump_binary_path: resolved path to the binary.
        #
        # Checked in order:
        #   1. satdump in PATH (system install)
        #   2. satdump-ui in PATH (GUI version)
        #   3. Fallback to /usr/bin/satdump
        #
        # Updated by:
        #   - is_installed() when binary is found
        #   - run() after successful .deb install
        #   - get_install_info() on each call
        #
        # Read by:
        #   - plugin.py SatDumpPlugin.initialize()
        #   - satdump_manager.py SatDumpManager.__init__()
        # -------------------------------------------------------
        self.satdump_binary_path = (
            shutil.which(self.SATDUMP_BINARY) or
            shutil.which(self.SATDUMP_UI_BINARY) or
            '/usr/bin/satdump'
        )

        print(
            f"[SatDump] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"Arch: {self._arch} | "
            f"Version: {SATDUMP_VERSION} | "
            f"Binary: {self.satdump_binary_path}"
        )

    def _detect_package_manager(self):
        """Detect available package manager."""
        for mgr in ['apt-get', 'dpkg']:
            if shutil.which(mgr):
                return mgr
        return None

    def _run_command(self, cmd, timeout=300):
        """
        Run a system command safely.

        Args:
            cmd: Command list
            timeout: Maximum seconds to wait

        Returns:
            tuple: (success, stdout, stderr)
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
            return False, '', f" [SatDump] Not found: {cmd[0]}: {e}"
        except subprocess.TimeoutExpired:
            return (
                False, '',
                f"[SatDump] Timed out after {timeout}s"
            )
        except Exception as e:
            return False, '', str(e)

    def is_installed(self):
        """
        Check if SatDump is installed.

        Also updates satdump_binary_path if binary
        is found so the attribute is always current.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Find binary
        binary = (
            shutil.which(self.SATDUMP_BINARY) or
            shutil.which(self.SATDUMP_UI_BINARY)
        )

        if binary:
            # Keep satdump_binary_path up to date
            self.satdump_binary_path = binary
            return True

        return False

    def get_deb_url(self):
        """
        Get the .deb download URL for this architecture.

        Normalises architecture names to match the
        SatDump release naming convention.

        Returns:
            str: Download URL or None if unsupported
        """
        arch = self._arch.lower()

        # Map architecture aliases
        arch_map = {
            'aarch64': 'aarch64',
            'arm64':   'aarch64',
            'armv8':   'aarch64',
            'x86_64':  'x86_64',
            'amd64':   'x86_64',
            'x64':     'x86_64',
        }

        normalised = arch_map.get(arch)

        if not normalised:
            print(
                f"[SatDump] WARNING: Architecture "
                f"'{arch}' may not have a pre-built "
                f"SatDump .deb package."
            )
            return None

        url = SATDUMP_DEB_URLS.get(normalised)
        if url:
            print(
                f"[SatDump] .deb URL for {arch}: {url}"
            )
        return url

    def _download_deb(self, url, dest_path):
        """
        Download the SatDump .deb package.

        Shows download progress and verifies the
        downloaded file is a valid .deb archive.

        Args:
            url: Download URL
            dest_path: Destination file path

        Returns:
            bool: True if downloaded successfully
        """
        print(
            f"[SatDump] Downloading SatDump {SATDUMP_VERSION}..."
        )
        print(f"[SatDump] URL: {url}")

        try:
            def progress_hook(block_num, block_size,
                               total_size):
                """Show download progress."""
                if total_size > 0:
                    downloaded = block_num * block_size
                    pct = min(
                        100,
                        int(downloaded * 100 / total_size)
                    )
                    if pct % 20 == 0 or pct == 100:
                        size_mb = total_size / 1024 / 1024
                        dl_mb = downloaded / 1024 / 1024
                        print(
                            f"[SatDump]   {pct}% "
                            f"({dl_mb:.1f}/{size_mb:.1f} MB)"
                        )

            # Use requests if available for better
            # error handling and progress reporting
            try:
                import requests
                print(f"[SatDump] Downloading via requests...")

                response = requests.get(
                    url,
                    stream=True,
                    timeout=120,
                    headers={
                        'User-Agent': 'HamRadioApp/1.0'
                    }
                )
                response.raise_for_status()

                total = int(
                    response.headers.get(
                        'content-length', 0
                    )
                )
                downloaded = 0

                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(
                        chunk_size=65536
                    ):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = int(
                                    downloaded * 100 / total
                                )
                                if pct % 25 == 0:
                                    print(
                                        f"[SatDump]   "
                                        f"{pct}% "
                                        f"({downloaded//1024//1024}"
                                        f"/"
                                        f"{total//1024//1024}"
                                        f" MB)"
                                    )

            except ImportError:
                # Fall back to urllib
                print(
                    "[SatDump] Downloading via urllib..."
                )
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'HamRadioApp/1.0'
                    }
                )
                urllib.request.urlretrieve(
                    url,
                    dest_path,
                    reporthook=progress_hook
                )

            # Verify download
            if not os.path.exists(dest_path):
                print("[SatDump] ERROR: Download failed")
                return False

            size = os.path.getsize(dest_path)
            size_mb = size / 1024 / 1024
            print(
                f"[SatDump] ✓ Downloaded {size_mb:.1f} MB"
            )

            # Basic sanity check — .deb files start with
            # the ar archive magic bytes '!<arch>'
            with open(dest_path, 'rb') as f:
                magic = f.read(7)
            if magic != b'!<arch>':
                print(
                    f"[SatDump] ERROR: Downloaded file "
                    f"does not appear to be a valid "
                    f".deb archive (magic: {magic})"
                )
                return False

            print("[SatDump] ✓ .deb file verified")
            return True

        except Exception as e:
            print(f"[SatDump] Download error: {e}")
            return False

    def _install_deb(self, deb_path):
        """
        Install the SatDump .deb package.

        Runs:
            dpkg -i satdump.deb
            apt-get install -f -y   (fix dependencies)

        Must run as root or with sudo.

        Args:
            deb_path: Path to the .deb file

        Returns:
            bool: True if installation succeeded
        """
        print(f"[SatDump] Installing: {deb_path}")

        if not shutil.which('dpkg'):
            print("[SatDump] ERROR: dpkg not found")
            return False

        # Step 1: dpkg -i (install the package)
        # May fail due to missing dependencies —
        # that is OK, we fix them in step 2
        print("[SatDump] Step 1: dpkg -i ...")
        ok, stdout, stderr = self._run_command(
            self._sudo + ['dpkg', '-i', deb_path],
            timeout=180
        )

        if ok:
            print("[SatDump] ✓ dpkg install succeeded")
        else:
            # dpkg may fail if dependencies are missing.
            # apt-get -f install will fix this.
            print(
                f"[SatDump] dpkg reported issues "
                f"(fixing with apt-get -f)..."
            )
            if stderr:
                print(
                    f"[SatDump] dpkg stderr: "
                    f"{stderr[:300]}"
                )

        # Step 2: apt-get install -f (fix dependencies)
        # This resolves any missing .deb dependencies
        if shutil.which('apt-get'):
            print(
                "[SatDump] Step 2: "
                "apt-get install -f -y ..."
            )
            fix_ok, fix_stdout, fix_stderr = (
                self._run_command(
                    self._sudo + [
                        'apt-get', 'install', '-f', '-y'
                    ],
                    timeout=300
                )
            )
            if fix_ok:
                print(
                    "[SatDump] ✓ Dependencies resolved"
                )
            else:
                print(
                    f"[SatDump] WARNING: "
                    f"Dependency fix failed: "
                    f"{fix_stderr[:200]}"
                )
                # Non-fatal — satdump may still work

        return True

    def install_python_packages_all(self):
        """
        Install required Python packages.

        Returns:
            bool: True if required packages available
        """
        print("[SatDump] Checking Python packages...")

        available, failed = self.install_python_packages(
            self.REQUIRED_PACKAGES
        )

        for pkg in self.OPTIONAL_PACKAGES:
            self.pip_install(pkg)

        if failed and self.in_docker:
            print(
                f"[SatDump] Add to requirements.txt: "
                f"{', '.join(failed)}"
            )

        return len(failed) == 0

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
            output = (
                result.stdout + result.stderr
            ).strip()
            if output:
                for line in output.splitlines():
                    if 'satdump' in line.lower() or \
                            any(
                                c.isdigit()
                                for c in line
                            ):
                        return line.strip()[:50]
            return f'installed (v{SATDUMP_VERSION})'
        except Exception:
            return f'installed (v{SATDUMP_VERSION})'

    def write_install_marker(self, method, version=None):
        """Write installation marker."""
        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': method,
                'version': version or SATDUMP_VERSION,
                'satdump_version': SATDUMP_VERSION,
                'platform': platform.platform(),
                'arch': self._arch,
                'binary': shutil.which(
                    self.SATDUMP_BINARY
                ),
            }
        )

def get_install_info(self):
        """
        Read installation marker data.

        Also refreshes satdump_binary_path from the
        current system state.

        Returns:
            dict: Marker contents or empty dict
        """
        # Refresh binary path
        found = (
            shutil.which(self.SATDUMP_BINARY) or
            shutil.which(self.SATDUMP_UI_BINARY)
        )
        if found:
            self.satdump_binary_path = found

        return self.read_marker(self.INSTALL_MARKER)

    def _log_dockerfile_instructions(self):
        """
        Log Dockerfile instructions for adding SatDump
        to the Docker image at build time.

        This is called when we are in Docker as non-root
        and cannot install system packages at runtime.
        """
        arch = self._arch
        deb_url = self.get_deb_url() or (
            f"{SATDUMP_RELEASE_BASE}"
            f"satdump_{SATDUMP_VERSION}_arm64.deb"
        )

        print(
            f"\n[SatDump] ======================================"
        )
        print("[SatDump] DOCKER INSTALLATION REQUIRED")
        print(
            "[SatDump] ======================================"
        )
        print(
            f"[SatDump] Architecture detected: {arch}"
        )
        print(
            "[SatDump] Add the following to your "
            "Dockerfile and rebuild:"
        )
        print()
        print(
            "[SatDump]   # Install SatDump from "
            f"official .deb (v{SATDUMP_VERSION})"
        )
        print(
            "[SatDump]   RUN set -eux; \\"
        )
        print(
            "[SatDump]       apt-get update; \\"
        )
        print(
            "[SatDump]       apt-get install -y \\"
        )
        print(
            "[SatDump]           --no-install-recommends \\"
        )
        print(
            "[SatDump]           curl ca-certificates; \\"
        )
        print(
            f"[SatDump]       curl -fsSL \\"
        )
        print(
            f"[SatDump]           -o /tmp/satdump.deb \\"
        )
        print(
            f"[SatDump]           '{deb_url}'; \\"
        )
        print(
            "[SatDump]       dpkg -i /tmp/satdump.deb \\"
        )
        print(
            "[SatDump]           || apt-get install "
            "-f -y; \\"
        )
        print(
            "[SatDump]       rm /tmp/satdump.deb; \\"
        )
        print(
            "[SatDump]       rm -rf /var/lib/apt/lists/*"
        )
        print()
        print(
            "[SatDump]   Then rebuild:"
        )
        print(
            "[SatDump]   docker compose build --no-cache"
        )
        print(
            "[SatDump] ======================================"
        )
        print()

        # Also log the direct download URL for reference
        print(
            f"[SatDump] Direct .deb URL:"
        )
        print(f"[SatDump]   {deb_url}")
        print()

        # Log all available .deb URLs
        print("[SatDump] All available .deb packages:")
        for arch_name, url in SATDUMP_DEB_URLS.items():
            if arch_name in ('aarch64', 'x86_64'):
                print(f"[SatDump]   {arch_name}: {url}")

    def run(self):
        """
        Execute the complete installation process.

        Installation strategy:
            1. Check if already installed (skip)
            2. Check if binary already in PATH (mark)
            3. Install Python packages
            4. If in Docker as non-root:
               → Log Dockerfile instructions
               → Return False (cannot install at runtime)
            5. If root or has sudo:
               → Get architecture-specific .deb URL
               → Download .deb to temp directory
               → Install with dpkg + apt-get -f
               → Verify binary is present
               → Write installation marker

        Returns:
            bool: True if installed or already present
        """
        # Already installed
        if self.is_installed():
            print("[SatDump] ✓ Already installed")
            return True

        # Binary in PATH but no marker
        if shutil.which(self.SATDUMP_BINARY):
            version = self.get_version()
            self.write_install_marker(
                'existing', version
            )
            print(
                f"[SatDump] ✓ Found in PATH: "
                f"{shutil.which(self.SATDUMP_BINARY)}"
            )
            return True

        print("[SatDump] ==========================================")
        print("[SatDump] Installing SatDump from .deb package")
        print(f"[SatDump] Version: {SATDUMP_VERSION}")
        print("[SatDump] ==========================================")

        # Step 1: Python packages (non-fatal)
        print("\n[SatDump] Step 1: Python packages...")
        self.install_python_packages_all()

        # Step 2: Check if we can install system packages
        if self.in_docker and not self.is_root:
            self._log_dockerfile_instructions()
            return False

        if not self.is_root and not self.sudo_available:
            print(
                "[SatDump] ERROR: Cannot install without "
                "root or sudo. "
                "Add satdump to Dockerfile."
            )
            self._log_dockerfile_instructions()
            return False

        # Step 3: Get .deb URL for this architecture
        print(
            f"\n[SatDump] Step 2: Downloading .deb "
            f"for {self._arch}..."
        )

        deb_url = self.get_deb_url()
        if not deb_url:
            print(
                f"[SatDump] ERROR: No .deb available "
                f"for architecture: {self._arch}"
            )
            print(
                "[SatDump] Check available packages at:"
            )
            print(
                "[SatDump]   https://github.com/"
                "SatDump/SatDump/releases"
            )
            return False

        # Step 4: Download to temp directory
        with tempfile.TemporaryDirectory(
            prefix='satdump_install_'
        ) as tmp_dir:
            deb_filename = os.path.basename(deb_url)
            deb_path = os.path.join(tmp_dir, deb_filename)

            if not self._download_deb(deb_url, deb_path):
                print(
                    "[SatDump] ERROR: Download failed. "
                    "Check internet connection and "
                    "try again."
                )
                return False

            # Step 5: Install the .deb
            print(
                f"\n[SatDump] Step 3: Installing .deb..."
            )

            if not self._install_deb(deb_path):
                print(
                    "[SatDump] ERROR: .deb installation failed"
                )
                return False

        # Step 6: Verify installation
        print("\n[SatDump] Step 4: Verifying...")

# Step 6: Verify installation
        print("\n[SatDump] Step 4: Verifying...")

        binary = shutil.which(self.SATDUMP_BINARY)
        if not binary:
            # Sometimes dpkg installs to /usr/local/bin
            for search_path in [
                '/usr/local/bin/satdump',
                '/usr/bin/satdump',
                '/opt/satdump/bin/satdump',
            ]:
                if os.path.isfile(search_path):
                    binary = search_path
                    break

        if binary:
            # Update instance attribute so plugin.py
            # and satdump_manager.py can find the binary
            self.satdump_binary_path = binary

            version = self.get_version()
            print(
                f"[SatDump] ✓ Binary found: {binary}"
            )
            if version:
                print(f"[SatDump] ✓ Version: {version}")
        else:
            print(
                "[SatDump] ERROR: satdump binary not "
                "found after installation."
            )
            return False

        # Step 7: Write marker
        version = self.get_version()
        self.write_install_marker('deb', version)

        print(
            "\n[SatDump] =========================================="
        )
        print("[SatDump] ✓ Installation complete!")
        print(f"[SatDump]   Version : {version}")
        print(f"[SatDump]   Binary  : {binary}")
        print(f"[SatDump]   Method  : .deb package")
        print(f"[SatDump]   Source  : {deb_url}")
        print(
            "[SatDump] =========================================="
            "\n"
        )

        return True
