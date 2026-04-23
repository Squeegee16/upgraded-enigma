"""
Winlink Plugin Installer
=========================
Handles first-run installation of Winlink dependencies.

Installation Strategy:
    Primary:   Pat Winlink client (native Linux)
               https://getpat.io/
    Secondary: Winlink Express via Wine
               https://winlink.org/WinlinkExpress

Pat Winlink is the recommended approach for Linux as it is:
    - Native Linux application
    - Open source
    - Actively maintained
    - Supports all major Winlink modes

Wine + Winlink Express is provided as an alternative for
operators who specifically require the Windows client.

Dependencies:
    - Pat Winlink binary (primary)
    - Wine (optional - for Winlink Express)
    - requests, psutil (Python packages)
    - ax25-tools (optional - for packet radio)

Reference:
    Pat: https://github.com/la5nta/pat
    Winlink Express: https://winlink.org/WinlinkExpress
"""

import os
import sys
import json
import shutil
import platform
import subprocess
from pathlib import Path


class WinlinkInstaller:
    """
    Manages installation of Winlink client and dependencies.

    Supports two installation paths:
    1. Pat Winlink - Native Linux client (recommended)
    2. Wine + Winlink Express - Windows client via compatibility layer

    Installation is tracked via a JSON marker file to prevent
    repeated installation attempts on subsequent runs.
    """

    # Installation state marker file
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # Pat Winlink GitHub releases API
    PAT_GITHUB_API = (
        'https://api.github.com/repos/la5nta/pat/releases/latest'
    )

    # Pat binary name
    PAT_BINARY = 'pat'

    # Installation directory
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    # Winlink Express download URL (requires Wine)
    WINLINK_EXPRESS_URL = (
        'https://downloads.winlink.org/User%20Programs/'
        'Winlink_Express_install_latest.zip'
    )

    def __init__(self):
        """
        Initialize installer with system detection.
        """
        self.plugin_dir = os.path.dirname(__file__)
        self.install_method = None
        self.pat_binary_path = (
            shutil.which(self.PAT_BINARY) or
            os.path.join(self.INSTALL_DIR, self.PAT_BINARY)
        )

        # Detect best installation method
        self._detect_install_method()

    def _detect_install_method(self):
        """
        Detect the best available installation method.

        Checks for:
        1. Pat already installed (best case)
        2. Package manager availability for Pat
        3. Wine availability for Winlink Express
        4. Manual download fallback
        """
        # Check if Pat is already installed
        if shutil.which(self.PAT_BINARY):
            self.install_method = 'pat_existing'
            print("[Winlink] Pat already installed in PATH")
            return

        # Check package managers for Pat
        if shutil.which('apt-get'):
            self.install_method = 'pat_apt'
        elif shutil.which('dnf'):
            self.install_method = 'pat_dnf'
        elif shutil.which('pacman'):
            self.install_method = 'pat_pacman'
        else:
            # Fall back to direct download
            self.install_method = 'pat_download'

        print(f"[Winlink] Installation method: {self.install_method}")

    def is_installed(self):
        """
        Check if Winlink client is installed.

        Returns:
            bool: True if marker exists and binary is found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Verify Pat binary exists
        pat_available = (
            shutil.which(self.PAT_BINARY) is not None or
            os.path.exists(self.pat_binary_path)
        )

        # Check Wine + Winlink Express as alternative
        wine_available = (
            shutil.which('wine') is not None and
            os.path.exists(
                os.path.expanduser(
                    '~/.wine/drive_c/Winlink Express/RMS Express.exe'
                )
            )
        )

        return pat_available or wine_available

    def install_python_packages(self):
        """
        Install required Python packages via pip.

        Returns:
            bool: True if all packages installed successfully
        """
        print("[Winlink] Installing Python packages...")
        failed = []

        for package in self.REQUIRED_PACKAGES:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install',
                     '--quiet', package],
                    check=True,
                    capture_output=True
                )
                print(f"[Winlink] ✓ {package}")
            except subprocess.CalledProcessError as e:
                print(f"[Winlink] WARNING: Failed to install {package}: {e}")
                failed.append(package)

        return len(failed) == 0

    def install_pat_apt(self):
        """
        Install Pat Winlink via apt-get.

        Adds the Pat repository and installs via apt.

        Returns:
            bool: True if installation successful
        """
        print("[Winlink] Installing Pat via apt-get...")

        try:
            # Install prerequisites
            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y',
                 'curl', 'apt-transport-https', 'gnupg'],
                check=True,
                capture_output=True
            )

            # Add Pat GPG key
            print("[Winlink] Adding Pat repository key...")
            key_cmd = subprocess.run(
                ['curl', '-fsSL',
                 'https://github.com/la5nta/pat/raw/master/packaging/key.gpg'],
                capture_output=True
            )

            if key_cmd.returncode == 0:
                subprocess.run(
                    ['sudo', 'apt-key', 'add', '-'],
                    input=key_cmd.stdout,
                    capture_output=True
                )

            # Add repository
            repo_content = (
                'deb [arch=amd64] '
                'https://updates.winlink.org/pat/deb stable main\n'
            )

            with open('/tmp/pat.list', 'w') as f:
                f.write(repo_content)

            subprocess.run(
                ['sudo', 'cp', '/tmp/pat.list',
                 '/etc/apt/sources.list.d/pat.list'],
                check=True,
                capture_output=True
            )

            # Update and install
            subprocess.run(
                ['sudo', 'apt-get', 'update', '-q'],
                check=True,
                capture_output=True
            )

            subprocess.run(
                ['sudo', 'apt-get', 'install', '-y', 'pat'],
                check=True,
                capture_output=True
            )

            print("[Winlink] ✓ Pat installed via apt")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[Winlink] apt installation failed: {e}")
            # Fall back to direct download
            return self.install_pat_download()

    def install_pat_download(self):
        """
        Install Pat by downloading the latest release from GitHub.

        Uses the GitHub API to find the latest release,
        downloads the appropriate binary for the current
        architecture, and installs it.

        Returns:
            bool: True if installation successful
        """
        print("[Winlink] Installing Pat via direct download...")

        try:
            import urllib.request

            # Query GitHub API for latest release
            print("[Winlink] Fetching latest Pat release info...")

            req = urllib.request.Request(
                self.PAT_GITHUB_API,
                headers={'User-Agent': 'HamRadioApp/1.0'}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                release_data = json.loads(response.read().decode())

            # Determine architecture for download
            machine = platform.machine().lower()
            arch_map = {
                'x86_64': 'amd64',
                'aarch64': 'arm64',
                'armv7l': 'armhf',
                'i686': '386'
            }
            arch = arch_map.get(machine, 'amd64')

            # Find appropriate asset
            target_name = f'pat_{arch}_linux'
            download_url = None
            asset_name = None

            for asset in release_data.get('assets', []):
                if (target_name in asset['name'].lower() and
                        asset['name'].endswith('.tar.gz')):
                    download_url = asset['browser_download_url']
                    asset_name = asset['name']
                    break

            if not download_url:
                print(f"[Winlink] ERROR: No download found for {arch}")
                return False

            # Download archive
            print(f"[Winlink] Downloading {asset_name}...")
            download_path = f'/tmp/{asset_name}'

            urllib.request.urlretrieve(download_url, download_path)

            # Extract binary
            print("[Winlink] Extracting Pat binary...")
            extract_dir = '/tmp/pat_extract'
            os.makedirs(extract_dir, exist_ok=True)

            subprocess.run(
                ['tar', '-xzf', download_path, '-C', extract_dir],
                check=True,
                capture_output=True
            )

            # Find Pat binary in extracted files
            pat_bin = None
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f == 'pat':
                        pat_bin = os.path.join(root, f)
                        break

            if not pat_bin:
                print("[Winlink] ERROR: Pat binary not found in archive")
                return False

            # Install to local bin
            os.makedirs(self.INSTALL_DIR, exist_ok=True)
            shutil.copy2(pat_bin, self.pat_binary_path)
            os.chmod(self.pat_binary_path, 0o755)

            print(f"[Winlink] ✓ Pat installed: {self.pat_binary_path}")

            # Cleanup
            shutil.rmtree(extract_dir, ignore_errors=True)
            os.remove(download_path)

            return True

        except Exception as e:
            print(f"[Winlink] ERROR: Download installation failed: {e}")
            return False

    def install_ax25_tools(self):
        """
        Install AX.25 tools for packet radio support (optional).

        These tools enable packet radio modes including
        VHF/UHF packet connections to Winlink gateways.

        Returns:
            bool: True if installed (non-fatal if fails)
        """
        print("[Winlink] Installing AX.25 tools (optional)...")

        try:
            if shutil.which('apt-get'):
                subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y',
                     'ax25-tools', 'ax25-apps'],
                    check=True,
                    capture_output=True
                )
                print("[Winlink] ✓ AX.25 tools installed")
                return True
        except subprocess.CalledProcessError:
            print("[Winlink] INFO: AX.25 tools not installed (optional)")

        return False

    def write_install_marker(self, method, pat_version=None):
        """
        Write installation marker with details.

        Args:
            method: Installation method used
            pat_version: Pat version string if available
        """
        marker_data = {
            'installed': True,
            'method': method,
            'pat_binary': self.pat_binary_path,
            'pat_version': pat_version,
            'platform': platform.platform(),
            'python_version': sys.version,
            'arch': platform.machine()
        }

        try:
            with open(self.INSTALL_MARKER, 'w') as f:
                json.dump(marker_data, f, indent=2)
            print("[Winlink] ✓ Installation marker written")
        except Exception as e:
            print(f"[Winlink] WARNING: Could not write marker: {e}")

    def get_pat_version(self):
        """
        Get installed Pat version string.

        Returns:
            str: Version string or None
        """
        try:
            result = subprocess.run(
                [self.pat_binary_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_install_info(self):
        """
        Read installation marker data.

        Returns:
            dict: Installation details or empty dict
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return {}

        try:
            with open(self.INSTALL_MARKER, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def run(self):
        """
        Execute the complete installation process.

        Steps:
        1. Check if already installed
        2. Install Python packages
        3. Install Pat Winlink client
        4. Optionally install AX.25 tools
        5. Write installation marker

        Returns:
            bool: True if installation successful
        """
        # Check if already installed
        if self.is_installed():
            print("[Winlink] ✓ Already installed, skipping")
            return True

        print("[Winlink] ============================================")
        print("[Winlink] Starting first-run installation")
        print("[Winlink] ============================================")

        # Step 1: Python packages
        print("\n[Winlink] Step 1: Python packages...")
        self.install_python_packages()
        # Non-fatal if some fail

        # Step 2: Install Pat
        print("\n[Winlink] Step 2: Installing Pat Winlink client...")
        success = False

        if self.install_method == 'pat_existing':
            success = True
            print("[Winlink] ✓ Using existing Pat installation")

        elif self.install_method == 'pat_apt':
            success = self.install_pat_apt()

        elif self.install_method in ('pat_download', 'pat_dnf',
                                     'pat_pacman'):
            success = self.install_pat_download()

        if not success:
            print("[Winlink] ERROR: Pat installation failed")
            print("[Winlink] Please install Pat manually:")
            print("[Winlink] https://getpat.io/")
            return False

        # Step 3: AX.25 tools (optional)
        print("\n[Winlink] Step 3: AX.25 tools (optional)...")
        self.install_ax25_tools()

        # Step 4: Write marker
        version = self.get_pat_version()
        self.write_install_marker(self.install_method, version)

        print("\n[Winlink] ============================================")
        print("[Winlink] ✓ Installation complete!")
        if version:
            print(f"[Winlink]   Pat version: {version}")
        print("[Winlink] ============================================\n")

        return True