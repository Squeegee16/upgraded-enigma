"""
Winlink (Pat) Installer
========================
Handles first-run installation of Pat Winlink client.

Installation Methods (tried in order):
    1. go install github.com/la5nta/pat@latest
       Preferred when Go is available (already in Docker).
       Builds the latest Pat from source. No root required.

    2. GitHub release .tar.gz download
       Downloads pre-built binary from GitHub releases.
       Selects correct architecture automatically.
       No root required — installs to ~/.local/bin/

    3. apt-get install pat
       Only on systems with Pat in apt repos.
       Requires root or sudo. Skipped in Docker.

Pat Winlink:
    Source:  https://github.com/la5nta/pat
    Website: https://getpat.io/
    License: MIT

Go install command:
    go install github.com/la5nta/pat@latest

GitHub releases API:
    https://api.github.com/repos/la5nta/pat/releases/latest

Author: Ham Radio App Team
Version: 1.0.0
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
                    f"[Winlink][INSTALL] Marker: {e}"
                )

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class WinlinkInstaller(BaseInstaller):
    """
    Manages Pat Winlink client installation.

    Tries three installation methods in order:
        1. go install (no root, builds latest)
        2. GitHub release download (no root, pre-built)
        3. apt-get (requires root, skipped in Docker)
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # Pat binary name
    PAT_BINARY = 'pat'

    # Go module path for go install
    PAT_GO_MODULE = 'github.com/la5nta/pat@latest'

    # GitHub API — correct URL for latest release
    PAT_GITHUB_API = (
        'https://api.github.com/repos/la5nta/pat'
        '/releases/latest'
    )

    # User-local install directory
    # On the hamradio user this is ~/.local/bin/
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    def __init__(self):
        """Initialise installer."""
        super().__init__()

        self._arch = platform.machine().lower()
        self._package_manager = (
            self._detect_package_manager()
        )

        # Full path to the installed Pat binary
        self.pat_binary_path = (
            shutil.which(self.PAT_BINARY) or
            os.path.join(self.INSTALL_DIR, self.PAT_BINARY)
        )

        # Go environment
        self._go_binary = shutil.which('go')
        self._gopath = os.environ.get(
            'GOPATH',
            os.path.expanduser('~/go')
        )

        print(
            f"[Winlink][INSTALL] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"Arch: {self._arch} | "
            f"Go: {self._go_binary or 'not found'}"
        )

    def _detect_package_manager(self):
        """Detect available package manager."""
        for mgr in ['apt-get', 'dnf', 'yum', 'pacman']:
            if shutil.which(mgr):
                return mgr
        return None

    def _run_command(self, cmd, timeout=300, env=None):
        """
        Run a command safely.

        Args:
            cmd: Command list
            timeout: Maximum seconds
            env: Optional environment dict

        Returns:
            tuple: (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            return (
                result.returncode == 0,
                result.stdout or '',
                result.stderr or ''
            )
        except FileNotFoundError as e:
            return (
                False, '',
                f"Command not found: {cmd[0]}: {e}"
            )
        except subprocess.TimeoutExpired:
            return (
                False, '',
                f"Timed out after {timeout}s"
            )
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
            shutil.which(self.PAT_BINARY) is not None
            or
            os.path.isfile(self.pat_binary_path)
        )

    def install_python_packages_all(self):
        """Install required Python packages."""
        print(
            "[Winlink][INSTALL] Checking Python packages..."
        )
        available, failed = self.install_python_packages(
            self.REQUIRED_PACKAGES
        )
        if failed and self.in_docker:
            print(
                f"[Winlink][INSTALL] Add to "
                f"requirements.txt: {', '.join(failed)}"
            )
        return len(failed) == 0

    # ----------------------------------------------------------
    # Method 1: go install
    # ----------------------------------------------------------

    def _install_via_go(self):
        """
        Install Pat using go install.

        This is the preferred method because:
        - Go is already installed in the Docker image
        - Builds the latest version from source
        - No root required
        - Works on all architectures Go supports

        The built binary lands in $GOPATH/bin/pat
        which is on PATH via the Dockerfile ENV.

        Returns:
            bool: True if installation succeeded
        """
        if not self._go_binary:
            print(
                "[Winlink][INSTALL] Go not available, "
                "skipping go install"
            )
            return False

        print(
            "[Winlink][INSTALL] Installing Pat via "
            "go install..."
        )
        print(
            f"[Winlink][INSTALL] "
            f"go install {self.PAT_GO_MODULE}"
        )

        # Build Go environment
        env = os.environ.copy()
        env['GOPATH'] = self._gopath
        env['GOCACHE'] = os.environ.get(
            'GOCACHE',
            os.path.expanduser('~/.cache/go-build')
        )
        env['GOROOT'] = os.environ.get(
            'GOROOT',
            '/usr/local/go'
        )

        # Ensure GOPATH/bin is on PATH
        gopath_bin = os.path.join(self._gopath, 'bin')
        local_bin = os.path.expanduser('~/.local/bin')
        current_path = env.get('PATH', '')
        for p in [gopath_bin, local_bin]:
            if p not in current_path:
                env['PATH'] = f"{p}:{current_path}"
                current_path = env['PATH']

        # Ensure GOPATH directories exist
        os.makedirs(gopath_bin, exist_ok=True)
        os.makedirs(
            env['GOCACHE'], exist_ok=True
        )

        print(
            f"[Winlink][INSTALL] GOPATH: {self._gopath}"
        )
        print(
            f"[Winlink][INSTALL] GOPATH/bin: {gopath_bin}"
        )

        # Run go install
        ok, stdout, stderr = self._run_command(
            [
                self._go_binary,
                'install',
                self.PAT_GO_MODULE
            ],
            timeout=600,  # 10 min — first build is slow
            env=env
        )

        if not ok:
            print(
                f"[Winlink][INSTALL] go install failed:"
            )
            if stdout:
                print(
                    f"[Winlink][INSTALL] stdout: "
                    f"{stdout[:300]}"
                )
            if stderr:
                print(
                    f"[Winlink][INSTALL] stderr: "
                    f"{stderr[:500]}"
                )
            return False

        # Find the installed binary
        pat_in_gopath = os.path.join(gopath_bin, 'pat')
        pat_found = None

        if os.path.isfile(pat_in_gopath):
            pat_found = pat_in_gopath
        elif shutil.which('pat', path=current_path):
            pat_found = shutil.which(
                'pat', path=current_path
            )

        if not pat_found:
            # Try to find it anywhere in GOPATH
            try:
                result = subprocess.run(
                    ['find', self._gopath,
                     '-name', 'pat', '-type', 'f'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.stdout.strip():
                    pat_found = (
                        result.stdout.strip()
                        .splitlines()[0]
                    )
            except Exception:
                pass

        if not pat_found:
            print(
                "[Winlink][INSTALL] go install succeeded "
                "but 'pat' binary not found in "
                f"GOPATH/bin ({gopath_bin})"
            )
            return False

        # Copy to ~/.local/bin/ so it's findable
        os.makedirs(self.INSTALL_DIR, exist_ok=True)
        dest = os.path.join(self.INSTALL_DIR, 'pat')

        if pat_found != dest:
            shutil.copy2(pat_found, dest)
            os.chmod(dest, 0o755)

        self.pat_binary_path = dest
        size_kb = os.path.getsize(dest) / 1024
        print(
            f"[Winlink][INSTALL] ✓ Pat installed via "
            f"go install: {dest} "
            f"({size_kb:.0f} KB)"
        )
        return True

    # ----------------------------------------------------------
    # Method 2: GitHub release download
    # ----------------------------------------------------------

    def _get_github_release_info(self):
        """
        Fetch latest Pat release info from GitHub API.

        Returns:
            dict: Release data or None on error
        """
        print(
            "[Winlink][INSTALL] Fetching release info "
            "from GitHub API..."
        )
        print(
            f"[Winlink][INSTALL] API: "
            f"{self.PAT_GITHUB_API}"
        )

        try:
            req = urllib.request.Request(
                self.PAT_GITHUB_API,
                headers={
                    'User-Agent': 'HamRadioApp/1.0',
                    'Accept': (
                        'application/vnd.github.v3+json'
                    ),
                }
            )

            with urllib.request.urlopen(
                req, timeout=30
            ) as response:
                if response.status != 200:
                    print(
                        f"[Winlink][INSTALL] GitHub API "
                        f"HTTP {response.status}"
                    )
                    return None

                data = json.loads(
                    response.read().decode('utf-8')
                )
                tag = data.get('tag_name', 'unknown')
                assets = data.get('assets', [])
                print(
                    f"[Winlink][INSTALL] Latest release: "
                    f"{tag} "
                    f"({len(assets)} assets)"
                )
                return data

        except urllib.error.HTTPError as e:
            print(
                f"[Winlink][INSTALL] GitHub API error: "
                f"HTTP {e.code} {e.reason}"
            )
            print(
                f"[Winlink][INSTALL] URL was: "
                f"{self.PAT_GITHUB_API}"
            )
            return None

        except urllib.error.URLError as e:
            print(
                f"[Winlink][INSTALL] Network error: {e}"
            )
            return None

        except Exception as e:
            print(
                f"[Winlink][INSTALL] API error: {e}"
            )
            return None

    def _find_release_asset(self, release_data):
        """
        Find the correct .tar.gz asset for this platform.

        Pat release naming convention:
            pat_X.Y.Z_linux_amd64.tar.gz
            pat_X.Y.Z_linux_arm64.tar.gz
            pat_X.Y.Z_linux_armhf.tar.gz

        Args:
            release_data: GitHub API release dict

        Returns:
            tuple: (asset_name, download_url) or (None, None)
        """
        assets = release_data.get('assets', [])
        tag = release_data.get('tag_name', '')

        print(
            f"[Winlink][INSTALL] Available assets "
            f"in {tag}:"
        )
        for asset in assets:
            print(
                f"[Winlink][INSTALL]   {asset['name']}"
            )

        # Map platform.machine() to Pat archive naming
        arch = self._arch.lower()
        arch_patterns = []

        if arch in ('aarch64', 'arm64'):
            arch_patterns = ['arm64', 'aarch64']
        elif arch in ('x86_64', 'amd64'):
            arch_patterns = ['amd64', 'x86_64']
        elif arch.startswith('armv'):
            arch_patterns = ['armhf', 'arm']
        else:
            arch_patterns = [arch]

        print(
            f"[Winlink][INSTALL] Platform: "
            f"linux/{arch} "
            f"(patterns: {arch_patterns})"
        )

        # Search for matching .tar.gz asset
        for pattern in arch_patterns:
            for asset in assets:
                name = asset['name'].lower()
                if (
                    name.endswith('.tar.gz') and
                    'linux' in name and
                    pattern in name
                ):
                    url = asset['browser_download_url']
                    print(
                        f"[Winlink][INSTALL] ✓ Matched: "
                        f"{asset['name']}"
                    )
                    return asset['name'], url

        print(
            f"[Winlink][INSTALL] No matching asset "
            f"found for linux/{arch}"
        )
        return None, None

    def _download_and_extract(self, url, asset_name):
        """
        Download Pat .tar.gz and extract the binary.

        Args:
            url: Download URL
            asset_name: Archive filename

        Returns:
            bool: True if downloaded and installed
        """
        import tempfile
        import tarfile

        print(
            f"[Winlink][INSTALL] Downloading "
            f"{asset_name}..."
        )

        with tempfile.TemporaryDirectory(
            prefix='pat_install_'
        ) as tmp_dir:
            archive_path = os.path.join(
                tmp_dir, asset_name
            )

            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'HamRadioApp/1.0'
                    }
                )
                urllib.request.urlretrieve(
                    url, archive_path
                )

                size_kb = os.path.getsize(
                    archive_path
                ) / 1024
                print(
                    f"[Winlink][INSTALL] ✓ Downloaded "
                    f"{size_kb:.0f} KB"
                )

            except Exception as e:
                print(
                    f"[Winlink][INSTALL] Download "
                    f"failed: {e}"
                )
                return False

            # Extract Pat binary from archive
            print(
                "[Winlink][INSTALL] Extracting Pat binary..."
            )

            try:
                with tarfile.open(
                    archive_path, 'r:gz'
                ) as tar:
                    members = tar.getmembers()
                    print(
                        "[Winlink][INSTALL] Archive contents:"
                    )
                    for m in members:
                        print(
                            f"[Winlink][INSTALL]   "
                            f"{m.name} ({m.size} bytes)"
                        )

                    # Find the 'pat' binary in the archive
                    pat_member = None
                    for member in members:
                        basename = os.path.basename(
                            member.name
                        )
                        if (
                            basename == self.PAT_BINARY and
                            member.isfile()
                        ):
                            pat_member = member
                            break

                    if not pat_member:
                        print(
                            "[Winlink][INSTALL] ERROR: "
                            "'pat' binary not found "
                            "in archive"
                        )
                        return False

                    # Extract to install directory
                    os.makedirs(
                        self.INSTALL_DIR, exist_ok=True
                    )
                    dest = os.path.join(
                        self.INSTALL_DIR,
                        self.PAT_BINARY
                    )

                    extracted = tar.extractfile(pat_member)
                    if extracted:
                        with open(dest, 'wb') as f:
                            f.write(extracted.read())
                        os.chmod(dest, 0o755)

                        size_kb = os.path.getsize(
                            dest
                        ) / 1024
                        print(
                            f"[Winlink][INSTALL] ✓ Pat "
                            f"installed: {dest} "
                            f"({size_kb:.0f} KB)"
                        )
                        self.pat_binary_path = dest
                        return True
                    else:
                        print(
                            "[Winlink][INSTALL] ERROR: "
                            "Could not extract 'pat' binary"
                        )
                        return False

            except Exception as e:
                print(
                    f"[Winlink][INSTALL] Extract "
                    f"error: {e}"
                )
                traceback.print_exc()
                return False

    def _install_via_github_release(self):
        """
        Install Pat by downloading from GitHub releases.

        No root required. Works in Docker.

        Returns:
            bool: True if installation succeeded
        """
        print(
            "[Winlink][INSTALL] Installing Pat via "
            "GitHub release download..."
        )

        # Fetch release info
        release_data = self._get_github_release_info()
        if not release_data:
            print(
                "[Winlink][INSTALL] Could not fetch "
                "release info from GitHub"
            )
            return False

        # Find correct asset
        asset_name, download_url = (
            self._find_release_asset(release_data)
        )

        if not asset_name or not download_url:
            print(
                f"[Winlink][INSTALL] No .tar.gz asset "
                f"found for {self._arch}"
            )
            return False

        # Download and install
        return self._download_and_extract(
            download_url, asset_name
        )

    # ----------------------------------------------------------
    # Method 3: apt-get
    # ----------------------------------------------------------

    def _install_via_apt(self):
        """
        Install Pat via apt-get.

        Only possible as root or with sudo.
        Skipped in Docker as non-root.

        Returns:
            bool: True if installed
        """
        print(
            "[Winlink][INSTALL]  Installing Pat "
            "via apt-get..."
        )

        if not shutil.which('apt-get'):
            print(
                "[Winlink][INSTALL] apt-get not available"
            )
            return False

        if self.in_docker and not self.is_root:
            print(
                "[Winlink][INSTALL] INFO: apt-get not "
                "available in Docker as non-root."
            )
            print(
                "[Winlink][INSTALL] INFO: Trying "
                "go install and GitHub download instead."
            )
            return False

        ok, _, stderr = self._run_command(
            self._sudo + ['apt-get', 'update', '-q'],
            timeout=120
        )
        if not ok:
            print(
                f"[Winlink][INSTALL] apt-get update "
                f"failed: {stderr[:150]}"
            )
            return False

        ok, _, stderr = self._run_command(
            self._sudo + [
                'apt-get', 'install', '-y', 'pat'
            ],
            timeout=300
        )

        if ok:
            print(
                "[Winlink][INSTALL] ✓ Pat installed "
                "via apt-get"
            )
            return True

        print(
            f"[Winlink][INSTALL] apt-get failed: "
            f"{stderr[:200]}"
        )
        return False

    # ----------------------------------------------------------
    # Optional: AX.25 tools
    # ----------------------------------------------------------

    def install_ax25_tools(self):
        """
        Install AX.25 tools for packet radio (optional).

        Returns:
            bool: True if installed
        """
        if self.in_docker and not self.is_root:
            print(
                "[Winlink][INSTALL] INFO: AX.25 tools "
                "require root. Add to Dockerfile: "
                "RUN apt-get install -y "
                "ax25-tools ax25-apps"
            )
            return False

        if not shutil.which('apt-get'):
            return False

        print(
            "[Winlink][INSTALL] Installing AX.25 tools..."
        )
        ok, _, stderr = self._run_command(
            self._sudo + [
                'apt-get', 'install', '-y',
                'ax25-tools', 'ax25-apps'
            ],
            timeout=120
        )

        if ok:
            print(
                "[Winlink][INSTALL] ✓ AX.25 tools installed"
            )
        else:
            print(
                "[Winlink][INSTALL] INFO: AX.25 tools "
                "not available (optional)"
            )
        return ok

    # ----------------------------------------------------------
    # Version and marker
    # ----------------------------------------------------------

    def get_version(self):
        """Get installed Pat version."""
        binary = (
            shutil.which(self.PAT_BINARY) or
            (
                self.pat_binary_path
                if os.path.isfile(self.pat_binary_path)
                else None
            )
        )

        if not binary:
            return None

        for flag in ['--version', 'version', '-v']:
            try:
                result = subprocess.run(
                    [binary, flag],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                output = (
                    result.stdout + result.stderr
                ).strip()
                if output:
                    first_line = (
                        output.splitlines()[0][:80]
                    )
                    return first_line
            except Exception:
                continue

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

    # ----------------------------------------------------------
    # Main entry point
    # ----------------------------------------------------------

    def run(self):
        """
        Execute the complete Pat installation process.

        Installation order:
            1. Already installed → skip
            2. Binary in PATH → write marker
            3. Python packages (non-fatal)
            4. go install github.com/la5nta/pat@latest
               → fastest when Go is available
            5. GitHub release .tar.gz download
               → fallback, pre-built binary
            6. apt-get install pat
               → only on non-Docker systems with root

        Returns:
            bool: True if Pat is available
        """
        # Already installed
        if self.is_installed():
            print("[Winlink][INSTALL] ✓ Already installed")
            return True

        # Binary in PATH but no marker
        existing = shutil.which(self.PAT_BINARY)
        if existing:
            version = self.get_version()
            self.write_install_marker(
                'existing', version
            )
            print(
                f"[Winlink][INSTALL] ✓ Found in PATH: "
                f"{existing}"
            )
            return True

        print(
            "[Winlink][INSTALL] =========================================="
        )
        print(
            "[Winlink][INSTALL] Installing Pat Winlink client"
        )
        print(
            "[Winlink][INSTALL] =========================================="
        )

        # Step 1: Python packages
        print(
            "\n[Winlink][INSTALL] Step 1: "
            "Python packages..."
        )
        self.install_python_packages_all()

        # Step 2: Try go install (preferred)
        print(
            "\n[Winlink][INSTALL] Step 2: "
            "Trying go install..."
        )
        if self._go_binary:
            success = self._install_via_go()
            if success:
                method = 'go_install'
                version = self.get_version()
                self._finalise(method, version)
                return True
            print(
                "[Winlink][INSTALL] go install failed, "
                "trying GitHub download..."
            )
        else:
            print(
                "[Winlink][INSTALL] Go not available, "
                "skipping go install"
            )

        # Step 3: GitHub release download
        print(
            "\n[Winlink][INSTALL] Step 3: "
            "Trying GitHub release download..."
        )
        success = self._install_via_github_release()
        if success:
            method = 'github_release'
            version = self.get_version()
            self._finalise(method, version)
            return True
        print(
            "[Winlink][INSTALL] GitHub download failed"
        )

        # Step 4: apt-get (non-Docker / root only)
        if not (self.in_docker and not self.is_root):
            print(
                "\n[Winlink][INSTALL] Step 4: "
                "Trying apt-get..."
            )
            success = self._install_via_apt()
            if success:
                method = 'apt_get'
                version = self.get_version()
                self._finalise(method, version)
                return True

        # All methods failed
        print(
            "\n[Winlink][INSTALL] ERROR: Pat installation failed"
        )
        print(
            "[Winlink][INSTALL] All installation methods "
            "were tried:"
        )

        if self._go_binary:
            print(
                f"[Winlink][INSTALL]   ✗ go install "
                f"{self.PAT_GO_MODULE}"
            )
        else:
            print(
                "[Winlink][INSTALL]   ✗ go install "
                "(Go not installed)"
            )

        print(
            f"[Winlink][INSTALL]   ✗ GitHub release "
            f"download"
        )

        if not (self.in_docker and not self.is_root):
            print(
                "[Winlink][INSTALL]   ✗ apt-get install"
            )

        print()
        print(
            "[Winlink][INSTALL] Manual install options:"
        )
        print(
            "[Winlink][INSTALL]   Option 1 (Go): "
            f"go install {self.PAT_GO_MODULE}"
        )
        print(
            "[Winlink][INSTALL]   Option 2 (direct): "
            "https://getpat.io/"
        )
        print(
            "[Winlink][INSTALL]   Option 3 (GitHub): "
            "https://github.com/la5nta/pat/releases"
        )

        return False

    def _finalise(self, method, version):
        """
        Write marker and log success after installation.

        Args:
            method: Installation method used
            version: Pat version string
        """
        # Install AX.25 tools (optional, non-fatal)
        print(
            "\n[Winlink][INSTALL] "
            "AX.25 tools (optional)..."
        )
        self.install_ax25_tools()

        # Write marker
        self.write_install_marker(method, version)

        print(
            "\n[Winlink][INSTALL] =========================================="
        )
        print("[Winlink][INSTALL] ✓ Pat installation complete!")
        if version:
            print(f"[Winlink][INSTALL]   Version : {version}")
        print(
            f"[Winlink][INSTALL]   Binary  : "
            f"{self.pat_binary_path}"
        )
        print(
            f"[Winlink][INSTALL]   Method  : {method}"
        )
        print(
            "[Winlink][INSTALL] =========================================="
            "\n"
        )
