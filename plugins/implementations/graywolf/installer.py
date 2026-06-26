"""
GrayWolf Dependency Installer
==============================
Handles installation of GrayWolf and its required
dependencies on first run.

GrayWolf is a Winlink gateway client written in Go.
Source: https://github.com/chrissnell/graywolf

Installation Strategy (in order):
    1. Download official release from GitHub
       Fastest — no compiler required.
       Both graywolf and graywolf-modem are pre-built.

    2. Build from source (fallback)
       Requires Go toolchain (already in Docker image).
       Used when no pre-built release exists for this
       architecture.

Go Environment:
    Go is installed in the Docker image at build time.
    GOPATH and GOCACHE are pre-created at
    /home/hamradio/go and /home/hamradio/.cache/go-build.

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
                print(f"[GrayWolf] Marker error: {e}")

        def read_marker(self, path):
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


# ------------------------------------------------------------------
# GitHub release configuration
# ------------------------------------------------------------------
GRAYWOLF_REPO = 'https://github.com/chrissnell/graywolf'
GRAYWOLF_GITHUB_API = (
    'https://api.github.com/repos/'
    'chrissnell/graywolf/releases/latest'
)


class GrayWolfInstaller(BaseInstaller):
    """
    Manages GrayWolf installation.

    Tries GitHub release download first (fastest),
    falls back to building from source using the Go
    toolchain that is already in the Docker image.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # Binary names
    GRAYWOLF_BINARY = 'graywolf'
    GRAYWOLF_MODEM_BINARY = 'graywolf-modem'

    # User-local install directory
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    # GrayWolf source repository
    GRAYWOLF_REPO = GRAYWOLF_REPO

    def __init__(self):
        """
        Initialise installer with Go environment detection.
        """
        super().__init__()

        # Installed binary paths
        self.graywolf_binary_path = (
            shutil.which(self.GRAYWOLF_BINARY) or
            os.path.join(
                self.INSTALL_DIR, self.GRAYWOLF_BINARY
            )
        )

        # Go environment
        self.goroot = os.environ.get(
            'GOROOT', '/usr/local/go'
        )
        self.gopath = os.environ.get(
            'GOPATH',
            os.path.expanduser('~/go')
        )
        self.gocache = os.environ.get(
            'GOCACHE',
            os.path.expanduser('~/.cache/go-build')
        )
        self._arch = platform.machine().lower()

        # Find Go binary
        self._go_binary = (
            shutil.which('go') or
            os.path.join(self.goroot, 'bin', 'go')
        )

        print(
            f"[GrayWolf] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"Go: {self._go_binary or 'not found'} | "
            f"GOPATH: {self.gopath}"
        )

    # ----------------------------------------------------------
    # State checks
    # ----------------------------------------------------------

    def is_installed(self):
        """
        Check if GrayWolf is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Update binary path
        found = shutil.which(self.GRAYWOLF_BINARY)
        if found:
            self.graywolf_binary_path = found
            return True

        if os.path.isfile(self.graywolf_binary_path):
            return True

        return False

    def get_install_info(self):
        """Read installation marker data."""
        return self.read_marker(self.INSTALL_MARKER)

    def get_version(self):
        """
        Get GrayWolf version string.

        Returns:
            str: Version string or None
        """
        binary = (
            shutil.which(self.GRAYWOLF_BINARY) or
            (
                self.graywolf_binary_path
                if os.path.isfile(
                    self.graywolf_binary_path
                )
                else None
            )
        )
        if not binary:
            return None

        for flag in ['--version', '-version',
                     'version', '-v', '--help']:
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
                    return output.splitlines()[0][:80]
            except Exception:
                continue

        return 'installed'

    def write_install_marker(self, method,
                              version=None):
        """Write installation marker."""
        go_version = None
        if self._go_binary:
            try:
                r = subprocess.run(
                    [self._go_binary, 'version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                go_version = r.stdout.strip()
            except Exception:
                pass

        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': method,
                'version': version,
                'binary_path': self.graywolf_binary_path,
                'platform': platform.platform(),
                'arch': self._arch,
                'go_version': go_version,
            }
        )

    # ----------------------------------------------------------
    # Go environment helpers
    # ----------------------------------------------------------

    def _get_go_env(self):
        """
        Build environment dictionary for Go commands.

        Ensures GOPATH, GOCACHE, GOROOT, HOME and PATH
        are all set correctly so Go subprocesses work.

        Returns:
            dict: Environment variables
        """
        env = os.environ.copy()

        if self.goroot and os.path.exists(self.goroot):
            env['GOROOT'] = self.goroot

        env['GOPATH'] = self.gopath
        env['GOCACHE'] = self.gocache

        if 'HOME' not in env:
            env['HOME'] = os.path.expanduser('~')

        # Ensure Go bin, GOPATH/bin, and local bin
        # are all on PATH
        go_bin = os.path.join(self.goroot, 'bin')
        gopath_bin = os.path.join(self.gopath, 'bin')
        local_bin = os.path.expanduser('~/.local/bin')

        current_path = env.get('PATH', '')
        for p in [go_bin, gopath_bin, local_bin]:
            if p not in current_path:
                env['PATH'] = (
                    f"{p}:{env['PATH']}"
                )

        # Ensure directories exist
        try:
            os.makedirs(self.gopath, exist_ok=True)
            os.makedirs(self.gocache, exist_ok=True)
        except OSError:
            pass

        return env

    def _run_go_command(self, cmd, cwd=None,
                         timeout=300):
        """
        Run a Go-related command with full output capture.

        Args:
            cmd: Command list
            cwd: Working directory
            timeout: Maximum seconds

        Returns:
            tuple: (success: bool, stdout: str, stderr: str)
        """
        env = self._get_go_env()
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True
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

    # ----------------------------------------------------------
    # Go toolchain checks
    # ----------------------------------------------------------

    def _check_go_available(self):
        """
        Verify Go toolchain is installed and working.

        Returns:
            tuple: (available: bool, info_string: str)
        """
        go = self._go_binary
        if not go or not os.path.exists(go):
            go = shutil.which('go')

        if not go:
            return (
                False,
                "go binary not found in PATH or GOROOT"
            )

        try:
            result = subprocess.run(
                [go, 'version'],
                capture_output=True,
                text=True,
                timeout=15,
                env=self._get_go_env()
            )
            if result.returncode == 0:
                version_line = result.stdout.strip()
                print(
                    f"[GrayWolf] Go version: "
                    f"{version_line}"
                )
                return True, version_line
            return (
                False,
                result.stderr.strip() or
                "go version failed"
            )
        except FileNotFoundError:
            return False, "go binary not executable"
        except subprocess.TimeoutExpired:
            return False, "go version timed out"
        except Exception as e:
            return False, str(e)

    def _parse_version_tuple(self, version_str):
        """
        Parse Go version string to comparable tuple.

        '1.22.3' -> (1, 22, 3)
        '1.21'   -> (1, 21, 0)

        Returns:
            tuple: (major, minor, patch) integers
        """
        try:
            parts = str(version_str).strip().split('.')
            while len(parts) < 3:
                parts.append('0')
            return tuple(int(x) for x in parts[:3])
        except (ValueError, AttributeError):
            return (0, 0, 0)

    def _check_go_version_compatible(self, go_mod_dir):
        """
        Check installed Go version meets go.mod requirement.

        Args:
            go_mod_dir: Directory containing go.mod

        Returns:
            tuple: (compatible: bool,
                    installed_ver: str,
                    required_ver: str)
        """
        go_mod_path = os.path.join(go_mod_dir, 'go.mod')
        if not os.path.exists(go_mod_path):
            return True, 'unknown', 'unknown'

        # Read required version from go.mod
        required_version = None
        try:
            with open(go_mod_path, 'r') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith('go '):
                        parts = stripped.split()
                        if len(parts) >= 2:
                            required_version = parts[1]
                            break
        except Exception as e:
            print(
                f"[GrayWolf] Cannot read go.mod: {e}"
            )
            return True, 'unknown', 'unknown'

        if not required_version:
            return True, 'unknown', 'unknown'

        print(
            f"[GrayWolf] go.mod requires: "
            f"Go {required_version}"
        )

        # Get installed version
        ok, go_info = self._check_go_available()
        if not ok:
            return False, 'not found', required_version

        # Extract version number e.g. go1.22.3 -> 1.22.3
        match = re.search(
            r'go(\d+\.\d+(?:\.\d+)?)', go_info
        )
        if not match:
            return True, go_info, required_version

        installed_version = match.group(1)
        installed_tuple = self._parse_version_tuple(
            installed_version
        )
        required_tuple = self._parse_version_tuple(
            required_version
        )
        compatible = installed_tuple >= required_tuple

        if compatible:
            print(
                f"[GrayWolf] ✓ Go compatible: "
                f"{installed_version} >= {required_version}"
            )
        else:
            print(
                f"[GrayWolf] ERROR: Go incompatible!"
            )
            print(
                f"[GrayWolf]   Installed: "
                f"Go {installed_version}"
            )
            print(
                f"[GrayWolf]   Required : "
                f"Go {required_version} (from go.mod)"
            )
            print(
                "[GrayWolf]   Fix in Dockerfile:"
            )
            print(
                f"[GrayWolf]     ARG GO_VERSION="
                f"{required_version}"
            )
            print(
                "[GrayWolf]   Then rebuild:"
            )
            print(
                "[GrayWolf]     docker compose build "
                "--no-cache"
            )

        return (
            compatible, installed_version, required_version
        )

    # ----------------------------------------------------------
    # Repository helpers
    # ----------------------------------------------------------

    def _find_main_package_dir(self, repo_root):
        """
        Find directory containing the main Go package.

        Some repos have main in root, others in cmd/name/.
        Scans for files declaring 'package main'.

        Args:
            repo_root: Root of cloned repository

        Returns:
            str: Path to directory with main package
        """
        print("[GrayWolf] Scanning for main package...")

        # Check common locations first
        common = [
            os.path.join(repo_root, 'cmd', 'graywolf'),
            os.path.join(repo_root, 'cmd'),
            os.path.join(repo_root, 'main'),
            os.path.join(repo_root, 'src'),
        ]
        for location in common:
            if not os.path.isdir(location):
                continue
            for gf in os.listdir(location):
                if not gf.endswith('.go'):
                    continue
                try:
                    with open(
                        os.path.join(location, gf),
                        'r', errors='ignore'
                    ) as f:
                        if 'package main' in f.read(512):
                            print(
                                f"[GrayWolf] main: "
                                f"{location}"
                            )
                            return location
                except Exception:
                    continue

        # Full scan
        main_dirs = []
        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [
                d for d in dirs
                if not d.startswith('.') and
                d not in ('vendor', 'testdata')
            ]
            for gf in files:
                if not gf.endswith('.go'):
                    continue
                try:
                    with open(
                        os.path.join(root, gf),
                        'r', errors='ignore'
                    ) as f:
                        if 'package main' in f.read(256):
                            if root not in main_dirs:
                                main_dirs.append(root)
                            break
                except Exception:
                    continue

        if len(main_dirs) == 1:
            print(
                f"[GrayWolf] main package: {main_dirs[0]}"
            )
            return main_dirs[0]
        elif len(main_dirs) > 1:
            shortest = min(main_dirs, key=len)
            print(
                f"[GrayWolf] Using shortest main: "
                f"{shortest}"
            )
            return shortest

        print(
            "[GrayWolf] No package main found, "
            "using repo root"
        )
        return repo_root

    def _log_directory_tree(self, path, max_depth=3,
                              current_depth=0, prefix=''):
        """
        Print directory tree for diagnostics.

        Args:
            path: Root directory to display
            max_depth: Maximum recursion depth
            current_depth: Current depth counter
            prefix: Indentation prefix
        """
        if current_depth > max_depth:
            return
        try:
            for entry in sorted(os.listdir(path)):
                if entry.startswith('.'):
                    continue
                full = os.path.join(path, entry)
                if os.path.isdir(full):
                    print(
                        f"[GrayWolf]   {prefix}{entry}/"
                    )
                    self._log_directory_tree(
                        full, max_depth,
                        current_depth + 1,
                        prefix + '  '
                    )
                else:
                    print(
                        f"[GrayWolf]   {prefix}{entry}"
                    )
        except Exception:
            pass

    def _find_and_install_binary(self, search_root,
                                   binary_name,
                                   dest_path):
        """
        Search for a built binary and copy to dest.

        Args:
            search_root: Directory tree to search
            binary_name: Filename to find
            dest_path: Destination path

        Returns:
            bool: True if found and installed
        """
        candidates = [
            os.path.join(search_root, binary_name),
            os.path.join(
                search_root, 'target',
                'release', binary_name
            ),
            os.path.join(search_root, 'bin', binary_name),
            os.path.join(
                search_root, 'build', binary_name
            ),
        ]

        # Recursive search
        for root, dirs, files in os.walk(search_root):
            dirs[:] = [
                d for d in dirs
                if d not in ('.git', 'vendor')
            ]
            if binary_name in files:
                candidate = os.path.join(
                    root, binary_name
                )
                if os.access(candidate, os.X_OK):
                    if candidate not in candidates:
                        candidates.insert(0, candidate)

        for candidate in candidates:
            if (os.path.isfile(candidate) and
                    os.access(candidate, os.X_OK)):
                print(
                    f"[GrayWolf] Found {binary_name}: "
                    f"{candidate}"
                )
                os.makedirs(
                    os.path.dirname(dest_path),
                    exist_ok=True
                )
                shutil.copy2(candidate, dest_path)
                os.chmod(dest_path, 0o755)
                return True

        return False

    # ----------------------------------------------------------
    # Python packages
    # ----------------------------------------------------------

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages available
        """
        print(
            "[GrayWolf] Installing required "
            "Python packages..."
        )
        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )
        if failed and self.in_docker:
            print(
                f"[GrayWolf] Add to requirements.txt: "
                f"{', '.join(failed)}"
            )
        return len(failed) == 0

    # ----------------------------------------------------------
    # Installation methods
    # ----------------------------------------------------------

    def _install_from_release(self):
        """
        Install GrayWolf from official GitHub release.

        Downloads the pre-built .tar.gz archive for
        this architecture, extracts both binaries
        (graywolf and graywolf-modem), and installs
        them to ~/.local/bin/.

        Returns:
            bool: True if both binaries installed
        """
        import tarfile
        import tempfile

        print(
            "[GrayWolf] Fetching latest release from "
            "GitHub..."
        )

        # Query GitHub API
        try:
            req = urllib.request.Request(
                GRAYWOLF_GITHUB_API,
                headers={
                    'User-Agent': 'HamRadioApp/1.0',
                    'Accept': (
                        'application/vnd.github.v3+json'
                    )
                }
            )
            with urllib.request.urlopen(
                req, timeout=30
            ) as resp:
                release_data = json.loads(
                    resp.read().decode()
                )
        except Exception as e:
            print(
                f"[GrayWolf] GitHub API error: {e}"
            )
            return False

        tag = release_data.get('tag_name', 'unknown')
        assets = release_data.get('assets', [])
        print(
            f"[GrayWolf] Latest release: {tag} "
            f"({len(assets)} assets)"
        )
        print("[GrayWolf] Available assets:")
        for asset in assets:
            print(f"[GrayWolf]   {asset['name']}")

        # Map architecture to release naming
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
            f"[GrayWolf] Platform: linux/{arch} "
            f"(patterns: {arch_patterns})"
        )

        # Find matching .tar.gz asset
        download_url = None
        asset_name = None
        for pattern in arch_patterns:
            for asset in assets:
                name = asset['name'].lower()
                if (
                    name.endswith('.tar.gz') and
                    'linux' in name and
                    pattern in name
                ):
                    download_url = (
                        asset['browser_download_url']
                    )
                    asset_name = asset['name']
                    print(
                        f"[GrayWolf] ✓ Matched: "
                        f"{asset_name}"
                    )
                    break
            if download_url:
                break

        if not download_url:
            print(
                f"[GrayWolf] No .tar.gz found for "
                f"linux/{arch}"
            )
            return False

        # Download archive
        with tempfile.TemporaryDirectory(
            prefix='graywolf_'
        ) as tmp_dir:
            archive_path = os.path.join(
                tmp_dir, asset_name
            )

            print(
                f"[GrayWolf] Downloading {asset_name}..."
            )
            try:
                req = urllib.request.Request(
                    download_url,
                    headers={
                        'User-Agent': 'HamRadioApp/1.0'
                    }
                )
                urllib.request.urlretrieve(
                    download_url, archive_path
                )
                size_kb = os.path.getsize(
                    archive_path
                ) / 1024
                print(
                    f"[GrayWolf] ✓ Downloaded "
                    f"{size_kb:.0f} KB"
                )
            except Exception as e:
                print(
                    f"[GrayWolf] Download failed: {e}"
                )
                return False

            # Extract binaries
            os.makedirs(self.INSTALL_DIR, exist_ok=True)
            installed = []
            target_binaries = {
                self.GRAYWOLF_BINARY,
                self.GRAYWOLF_MODEM_BINARY
            }

            print("[GrayWolf] Extracting binaries...")
            try:
                with tarfile.open(
                    archive_path, 'r:gz'
                ) as tar:
                    members = tar.getmembers()
                    print("[GrayWolf] Archive contents:")
                    for m in members:
                        print(
                            f"[GrayWolf]   "
                            f"{m.name} ({m.size}b)"
                        )

                    for member in members:
                        basename = os.path.basename(
                            member.name
                        )
                        if (
                            basename in target_binaries
                            and member.isfile()
                        ):
                            dest = os.path.join(
                                self.INSTALL_DIR,
                                basename
                            )
                            extracted = (
                                tar.extractfile(member)
                            )
                            if extracted:
                                with open(
                                    dest, 'wb'
                                ) as f:
                                    f.write(
                                        extracted.read()
                                    )
                                os.chmod(dest, 0o755)
                                size_kb = (
                                    os.path.getsize(dest)
                                    / 1024
                                )
                                print(
                                    f"[GrayWolf] ✓ "
                                    f"{basename}: "
                                    f"{size_kb:.0f} KB"
                                )
                                installed.append(basename)
            except Exception as e:
                print(
                    f"[GrayWolf] Extract error: {e}"
                )
                traceback.print_exc()
                return False

        # Verify both binaries are present
        for binary in [
            self.GRAYWOLF_BINARY,
            self.GRAYWOLF_MODEM_BINARY
        ]:
            path = os.path.join(self.INSTALL_DIR, binary)
            if not (
                os.path.isfile(path) and
                os.access(path, os.X_OK)
            ):
                print(
                    f"[GrayWolf] ✗ Missing: {binary}"
                )
                return False

        self.graywolf_binary_path = os.path.join(
            self.INSTALL_DIR, self.GRAYWOLF_BINARY
        )
        print(
            "[GrayWolf] ✓ Both binaries installed "
            "from release"
        )
        return True

    def _build_graywolf_modem(self, repo_dir):
        """
        Build graywolf-modem (Rust binary) separately.

        Tries cargo build, falls back to downloading
        from GitHub release.

        Args:
            repo_dir: GrayWolf repository directory

        Returns:
            tuple: (success: bool, message: str)
        """
        modem_dest = os.path.join(
            self.INSTALL_DIR, self.GRAYWOLF_MODEM_BINARY
        )

        # Try cargo build
        cargo = (
            shutil.which('cargo') or
            os.path.expanduser('~/.cargo/bin/cargo')
        )
        if cargo and os.path.exists(cargo):
            print(
                "[GrayWolf] Building graywolf-modem "
                "with cargo..."
            )

            # Find Cargo.toml
            modem_src = None
            for candidate in [
                os.path.join(repo_dir, 'graywolf-modem'),
                os.path.join(repo_dir, 'modem'),
                repo_dir,
            ]:
                if os.path.exists(
                    os.path.join(candidate, 'Cargo.toml')
                ):
                    modem_src = candidate
                    break

            if modem_src:
                env = self._get_go_env()
                cargo_home = os.path.expanduser(
                    '~/.cargo'
                )
                env['CARGO_HOME'] = cargo_home
                env['PATH'] = (
                    f"{cargo_home}/bin:"
                    f"{env.get('PATH', '')}"
                )

                try:
                    result = subprocess.run(
                        [cargo, 'build', '--release'],
                        cwd=modem_src,
                        capture_output=True,
                        text=True,
                        timeout=600,
                        env=env
                    )
                    if result.returncode == 0:
                        release_bin = os.path.join(
                            modem_src, 'target',
                            'release',
                            self.GRAYWOLF_MODEM_BINARY
                        )
                        if os.path.exists(release_bin):
                            shutil.copy2(
                                release_bin, modem_dest
                            )
                            os.chmod(modem_dest, 0o755)
                            print(
                                "[GrayWolf] ✓ "
                                "graywolf-modem built"
                            )
                            return True, modem_dest
                except Exception as e:
                    print(
                        f"[GrayWolf] cargo error: {e}"
                    )

        # Try downloading pre-built modem from release
        print(
            "[GrayWolf] Attempting to download "
            "pre-built graywolf-modem..."
        )
        downloaded = self._download_graywolf_modem(
            modem_dest
        )
        if downloaded:
            return True, modem_dest

        return False, "graywolf-modem build/download failed"

    def _download_graywolf_modem(self, dest_path):
        """
        Download pre-built graywolf-modem from release.

        Args:
            dest_path: Destination for binary

        Returns:
            bool: True if downloaded
        """
        try:
            req = urllib.request.Request(
                GRAYWOLF_GITHUB_API,
                headers={
                    'User-Agent': 'HamRadioApp/1.0',
                    'Accept': (
                        'application/vnd.github.v3+json'
                    )
                }
            )
            with urllib.request.urlopen(
                req, timeout=30
            ) as resp:
                release_data = json.loads(
                    resp.read().decode()
                )
        except Exception as e:
            print(
                f"[GrayWolf] API error: {e}"
            )
            return False

        assets = release_data.get('assets', [])
        arch = self._arch.lower()
        arch_patterns = []
        if arch in ('aarch64', 'arm64'):
            arch_patterns = ['arm64', 'aarch64']
        elif arch in ('x86_64', 'amd64'):
            arch_patterns = ['amd64', 'x86_64']
        else:
            arch_patterns = [arch]

        download_url = None
        asset_name = None
        for pattern in arch_patterns:
            for asset in assets:
                name = asset['name'].lower()
                if (
                    'graywolf-modem' in name and
                    'linux' in name and
                    name.endswith('.tar.gz') and
                    pattern in name
                ):
                    download_url = (
                        asset['browser_download_url']
                    )
                    asset_name = asset['name']
                    break
            if download_url:
                break

        if not download_url:
            print(
                "[GrayWolf] No graywolf-modem asset found"
            )
            return False

        import tarfile
        import tempfile

        try:
            with tempfile.TemporaryDirectory() as tmp:
                archive = os.path.join(tmp, asset_name)
                urllib.request.urlretrieve(
                    download_url, archive
                )
                with tarfile.open(
                    archive, 'r:gz'
                ) as tar:
                    for member in tar.getmembers():
                        if (
                            os.path.basename(
                                member.name
                            ) == self.GRAYWOLF_MODEM_BINARY
                            and member.isfile()
                        ):
                            extracted = (
                                tar.extractfile(member)
                            )
                            if extracted:
                                with open(
                                    dest_path, 'wb'
                                ) as f:
                                    f.write(
                                        extracted.read()
                                    )
                                os.chmod(
                                    dest_path, 0o755
                                )
                                print(
                                    "[GrayWolf] ✓ "
                                    "graywolf-modem "
                                    "downloaded"
                                )
                                return True
        except Exception as e:
            print(
                f"[GrayWolf] Modem download error: {e}"
            )
        return False

    def clone_and_build(self):
        """
        Install GrayWolf — tries release first,
        then falls back to source build.

        Returns:
            bool: True if both binaries installed
        """
        os.makedirs(self.INSTALL_DIR, exist_ok=True)

        # Strategy 1: GitHub release download
        print(
            "\n[GrayWolf] Strategy 1: "
            "GitHub release download..."
        )
        if self._install_from_release():
            print("[GrayWolf] ✓ Installed from release")
            return True
        print(
            "[GrayWolf] Release download failed, "
            "trying source build..."
        )

        # Strategy 2: Build from source
        print(
            "\n[GrayWolf] Strategy 2: "
            "Building from source..."
        )
        build_dir = os.path.join(
            os.path.expanduser('~'), '.graywolf_build'
        )

        try:
            if os.path.exists(build_dir):
                shutil.rmtree(
                    build_dir, ignore_errors=True
                )
            os.makedirs(build_dir, exist_ok=True)

            # Clone
            print("[GrayWolf] Cloning repository...")
            ok, stdout, stderr = self._run_go_command(
                [
                    'git', 'clone',
                    '--depth', '1',
                    self.GRAYWOLF_REPO,
                    build_dir
                ],
                timeout=120
            )
            if not ok:
                print(
                    f"[GrayWolf] Clone failed: {stderr}"
                )
                return False
            print("[GrayWolf] ✓ Repository cloned")
            self._log_directory_tree(
                build_dir, max_depth=2
            )

            # Find go.mod
            go_mod_dir = None
            for root, dirs, files in os.walk(build_dir):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith('.')
                ]
                if 'go.mod' in files:
                    go_mod_dir = root
                    break

            if not go_mod_dir:
                print("[GrayWolf] ERROR: go.mod missing")
                return False

            # Show go.mod
            try:
                with open(
                    os.path.join(go_mod_dir, 'go.mod'),
                    'r'
                ) as f:
                    print(
                        f"[GrayWolf] go.mod:\n"
                        f"{f.read()[:400]}"
                    )
            except Exception:
                pass

            # Check Go version
            compatible, inst, req = (
                self._check_go_version_compatible(
                    go_mod_dir
                )
            )
            if not compatible:
                print(
                    f"[GrayWolf] ERROR: Go {inst} < "
                    f"{req}"
                )
                return False

            # Download deps
            print(
                "[GrayWolf] Downloading dependencies..."
            )
            self._run_go_command(
                ['go', 'mod', 'download'],
                cwd=go_mod_dir,
                timeout=300
            )

            # Find main package
            main_pkg = self._find_main_package_dir(
                go_mod_dir
            )
            if main_pkg == go_mod_dir:
                build_target = '.'
            else:
                rel = os.path.relpath(
                    main_pkg, go_mod_dir
                )
                build_target = f'./{rel}'

            output_path = os.path.join(
                go_mod_dir, self.GRAYWOLF_BINARY
            )

            # Build with verbose output
            print(
                f"[GrayWolf] Building: {build_target}"
            )
            env = self._get_go_env()
            result = subprocess.run(
                [
                    'go', 'build',
                    '-v',
                    '-o', output_path,
                    build_target
                ],
                cwd=go_mod_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(
                    "[GrayWolf] ERROR: go build failed"
                )
                print(
                    "[GrayWolf] ---- BUILD ERROR ----"
                )
                if result.stdout.strip():
                    print(
                        f"[GrayWolf] STDOUT:\n"
                        f"{result.stdout.strip()}"
                    )
                if result.stderr.strip():
                    print(
                        f"[GrayWolf] STDERR:\n"
                        f"{result.stderr.strip()}"
                    )
                print(
                    "[GrayWolf] ---- END ERROR ----"
                )
                return False

            print("[GrayWolf] ✓ Build successful")

            # Install graywolf binary
            gw_ok = self._find_and_install_binary(
                go_mod_dir,
                self.GRAYWOLF_BINARY,
                self.graywolf_binary_path
            )
            if not gw_ok:
                print(
                    "[GrayWolf] ERROR: binary not found"
                )
                return False
            print(
                f"[GrayWolf] ✓ graywolf: "
                f"{self.graywolf_binary_path}"
            )

            # Build graywolf-modem
            modem_ok, modem_msg = (
                self._build_graywolf_modem(go_mod_dir)
            )
            if not modem_ok:
                print(
                    f"[GrayWolf] ERROR: "
                    f"graywolf-modem: {modem_msg}"
                )
                return False

            return True

        except Exception as e:
            print(
                f"[GrayWolf] Build exception: {e}"
            )
            traceback.print_exc()
            return False
        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(
                    build_dir, ignore_errors=True
                )
                print(
                    "[GrayWolf] Build dir cleaned up"
                )

    # ----------------------------------------------------------
    # Main entry point
    # ----------------------------------------------------------

    def run(self):
        """
        Execute the complete installation process.

        Returns:
            bool: True if GrayWolf is available
        """
        # Already installed
        if self.is_installed():
            print("[GrayWolf] ✓ Already installed")
            return True

        # Binary in PATH but no marker
        existing = shutil.which(self.GRAYWOLF_BINARY)
        if existing:
            self.graywolf_binary_path = existing
            print(
                f"[GrayWolf] ✓ Found in PATH: "
                f"{existing}"
            )
            self.write_install_marker('existing')
            return True

        print(
            "[GrayWolf] ================================"
        )
        print(
            "[GrayWolf] No existing installation found"
        )
        print(
            "[GrayWolf] Starting first-run installation"
        )
        print(
            "[GrayWolf] ================================"
        )

        # Step 1: Check Go toolchain
        print(
            "\n[GrayWolf] Step 1: Checking Go..."
        )
        go_available, go_info = (
            self._check_go_available()
        )
        if go_available:
            print(
                f"[GrayWolf] ✓ Go: {go_info}"
            )
        else:
            print(
                f"[GrayWolf] WARNING: Go not found: "
                f"{go_info}"
            )
            print(
                "[GrayWolf] Will try release download"
            )

        # Step 2: Python packages
        print(
            "\n[GrayWolf] Step 2: Python packages..."
        )
        self.install_python_packages()

        # Step 3: Check git
        print(
            "\n[GrayWolf] Step 3: Checking git..."
        )
        if shutil.which('git'):
            print("[GrayWolf] ✓ git available")
        else:
            print("[GrayWolf] WARNING: git not found")

        # Step 4: Install
        print(
            "\n[GrayWolf] Step 4: Installing..."
        )
        success = self.clone_and_build()

        if not success:
            print(
                "\n[GrayWolf] "
                "=============================="
            )
            print("[GrayWolf] INSTALLATION FAILED")
            print(
                "[GrayWolf] "
                "=============================="
            )
            print("[GrayWolf] Diagnostics:")
            print(
                f"[GrayWolf]   Go:    "
                f"{shutil.which('go') or 'NOT FOUND'}"
            )
            print(
                f"[GrayWolf]   git:   "
                f"{shutil.which('git') or 'NOT FOUND'}"
            )
            print(
                f"[GrayWolf]   arch:  {self._arch}"
            )
            print(
                f"[GrayWolf]   GOPATH:{self.gopath}"
            )
            print()
            print("[GrayWolf] Manual diagnosis:")
            print(
                "[GrayWolf]   docker compose exec "
                "app bash"
            )
            print(
                "[GrayWolf]   cd /tmp && "
                "git clone --depth 1 "
                f"{self.GRAYWOLF_REPO} gw"
            )
            print(
                "[GrayWolf]   cd gw && go build -v ./..."
            )
            return False

        # Write marker
        version = self.get_version()
        self.write_install_marker('auto', version)

        print(
            "\n[GrayWolf] "
            "================================"
        )
        print("[GrayWolf] ✓ Installation complete!")
        if version:
            print(f"[GrayWolf]   Version: {version}")
        print(
            f"[GrayWolf]   Binary: "
            f"{self.graywolf_binary_path}"
        )
        print(
            "[GrayWolf] "
            "================================\n"
        )
        return True
