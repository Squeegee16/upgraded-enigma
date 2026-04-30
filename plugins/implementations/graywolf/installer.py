"""
GrayWolf Dependency Installer
==============================
Handles installation of GrayWolf and its required
dependencies on first run.

GrayWolf is a Winlink gateway client written in Go.
Source: https://github.com/chrissnell/graywolf

Installation Process:
    1. Verify Go toolchain is available and version-compatible
    2. Install required Python packages
    3. Verify git is available
    4. Clone GrayWolf repository from GitHub
    5. Verify go.mod version compatibility
    6. Download Go module dependencies
    7. Build binary with 'go build'
    8. Install binary to ~/.local/bin/graywolf
    9. Write installation marker

Go Version Requirements:
    The go.mod in the GrayWolf repository specifies the
    minimum Go version. This installer reads that version
    and compares it against the installed Go version before
    attempting to build. If the versions are incompatible,
    a clear error message is displayed with instructions
    to update the Dockerfile ARG GO_VERSION value.

Docker Notes:
    - Go is installed from official go.dev tarball in
      the Dockerfile (NOT from apt golang-go which is
      always outdated in Debian Bookworm)
    - The hamradio user (UID 1000) has a pre-created
      writable GOPATH at /home/hamradio/go
    - GOCACHE is at /home/hamradio/.cache/go-build
    - The built binary is installed to
      /home/hamradio/.local/bin/graywolf

Common Errors:
    go.mod version mismatch:
        Update ARG GO_VERSION in Dockerfile to the
        version required by go.mod and rebuild.
    Permission denied on GOCACHE/GOPATH:
        Ensure the pre-create RUN mkdir commands in
        the Dockerfile ran before USER hamradio.
    git clone failed:
        Check network connectivity from the container.

Author: Ham Radio App Team
Version: 1.0.0
"""

import os
import re
import sys
import json
import shutil
import platform
import subprocess
import traceback
from datetime import datetime


# ----------------------------------------------------------------
# Import shared base installer for Docker-aware pip handling.
# Falls back to an inline minimal implementation if the base
# installer module is not yet available (e.g. first install).
# ----------------------------------------------------------------
try:
    from plugins.implementations.base_installer import BaseInstaller
except ImportError:
    class BaseInstaller:
        """
        Minimal inline fallback for BaseInstaller.

        Used when plugins/implementations/base_installer.py
        cannot be imported. Provides the minimum interface
        needed by GrayWolfInstaller.
        """

        def __init__(self):
            """Detect runtime environment."""
            try:
                self.is_root = (os.getuid() == 0)
            except AttributeError:
                self.is_root = False

            self.sudo_available = (
                shutil.which('sudo') is not None
            )
            self._sudo = (
                [] if (self.is_root or not self.sudo_available)
                else ['sudo']
            )

            # Docker detection via env var or /.dockerenv
            self.in_docker = (
                os.environ.get(
                    'PLUGIN_SKIP_PIP_INSTALL', ''
                ).lower() == 'true' or
                os.path.exists('/.dockerenv')
            )

        def pip_install(self, package):
            """
            Install package or skip in Docker.

            Args:
                package: Package name to install

            Returns:
                bool: True if available or skipped
            """
            if self.in_docker:
                # In Docker all packages must be pre-installed
                # via requirements.txt — skip silently
                return True

            try:
                subprocess.run(
                    [
                        sys.executable, '-m', 'pip',
                        'install', '--quiet', package
                    ],
                    check=True,
                    capture_output=True,
                    timeout=120
                )
                return True
            except Exception:
                return False

        def install_python_packages(self, packages):
            """
            Install a list of packages.

            Args:
                packages: List of package name strings

            Returns:
                tuple: (available_count, failed_list)
            """
            failed = []
            for pkg in packages:
                if not self.pip_install(pkg):
                    failed.append(pkg)
            return len(packages) - len(failed), failed

        def write_marker(self, path, extra_data=None):
            """
            Write installation marker JSON file.

            Args:
                path: Full path for the marker file
                extra_data: Optional dict of extra fields
            """
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
                print(f"[GrayWolf] Marker write error: {e}")

        def read_marker(self, path):
            """
            Read installation marker JSON file.

            Args:
                path: Full path to marker file

            Returns:
                dict: Marker data or empty dict
            """
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}


class GrayWolfInstaller(BaseInstaller):
    """
    Manages GrayWolf installation from source.

    Extends BaseInstaller to handle the Go build process
    with proper environment setup, Go version checking,
    and verbose error reporting so failures are diagnosable
    from Docker logs.

    Installation is tracked via a JSON marker file at
    INSTALL_MARKER. Once the marker exists and the binary
    is present, no reinstallation is attempted.
    """

    # ----------------------------------------------------------
    # Class-level constants
    # ----------------------------------------------------------

    # Marker file path — stored inside the plugin directory
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # GrayWolf source repository
    GRAYWOLF_REPO = 'https://github.com/chrissnell/graywolf'

    # Output binary name
    GRAYWOLF_BINARY = 'graywolf'

    # Installation directory for the built binary
    # Uses ~/.local/bin which is on the PATH for the
    # hamradio user as configured in the Dockerfile ENV
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # Python packages required by this plugin
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    def __init__(self):
        """
        Initialise installer with Go environment detection.

        Calls BaseInstaller.__init__() for Docker/root
        detection, then sets up Go-specific paths.
        """
        super().__init__()

        # Full path to the installed GrayWolf binary
        self.graywolf_binary_path = os.path.join(
            self.INSTALL_DIR,
            self.GRAYWOLF_BINARY
        )

        # Go workspace paths
        # These match the ENV variables set in the Dockerfile
        # and the pre-created directories from RUN mkdir -p
        self.gopath = os.environ.get(
            'GOPATH',
            os.path.expanduser('~/go')
        )
        self.gocache = os.environ.get(
            'GOCACHE',
            os.path.expanduser('~/.cache/go-build')
        )
        self.goroot = os.environ.get(
            'GOROOT',
            '/usr/local/go'
        )

        print(
            f"[GrayWolf] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Root: {self.is_root} | "
            f"Go: {shutil.which('go') or 'not found'} | "
            f"GOPATH: {self.gopath}"
        )

    # ----------------------------------------------------------
    # Go environment helpers
    # ----------------------------------------------------------

    def _get_go_env(self):
        """
        Build a clean environment dict for Go subprocesses.

        Ensures GOPATH, GOCACHE, GOROOT, HOME, and PATH
        are all correctly set. Creates GOPATH and GOCACHE
        directories if they do not exist.

        Returns:
            dict: Environment variables for subprocess calls
        """
        env = os.environ.copy()

        # Set Go workspace variables
        env['GOPATH'] = self.gopath
        env['GOCACHE'] = self.gocache

        if self.goroot and os.path.exists(self.goroot):
            env['GOROOT'] = self.goroot

        # Ensure HOME is set — Go needs it for .config paths
        if 'HOME' not in env:
            env['HOME'] = os.path.expanduser('~')

        # Ensure GOPATH and GOCACHE directories exist
        try:
            os.makedirs(self.gopath, exist_ok=True)
            os.makedirs(self.gocache, exist_ok=True)
        except OSError as e:
            print(
                f"[GrayWolf] WARNING: Cannot create Go dirs: "
                f"{e}"
            )

        # Add Go bin directories and ~/.local/bin to PATH
        go_bin = os.path.join(self.goroot, 'bin') \
            if self.goroot else '/usr/local/go/bin'
        gopath_bin = os.path.join(self.gopath, 'bin')
        local_bin = os.path.expanduser('~/.local/bin')

        current_path = env.get('PATH', '')
        path_parts = current_path.split(':')

        for p in [go_bin, gopath_bin, local_bin]:
            if p not in path_parts:
                env['PATH'] = f"{p}:{env['PATH']}"

        return env

    def _run_go_command(self, cmd, cwd=None, timeout=300):
        """
        Execute a Go-related command with full output capture.

        Unlike a generic _run_command, this method captures
        stdout and stderr separately so Go compiler errors
        are fully visible in logs when a build fails.

        Args:
            cmd: Command and arguments as a list
            cwd: Working directory (None = current dir)
            timeout: Maximum seconds to allow

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

            stdout = result.stdout or ''
            stderr = result.stderr or ''

            if result.returncode == 0:
                return True, stdout, stderr
            else:
                return False, stdout, stderr

        except FileNotFoundError as e:
            return (
                False, '',
                f"Command not found: {cmd[0]} — {e}"
            )
        except subprocess.TimeoutExpired:
            return (
                False, '',
                f"Command timed out after {timeout}s: "
                f"{' '.join(cmd)}"
            )
        except Exception as e:
            return False, '', str(e)

    # ----------------------------------------------------------
    # Installation state checks
    # ----------------------------------------------------------

    def is_installed(self):
        """
        Check whether GrayWolf is installed.

        Verifies that:
        1. The installation marker file exists
        2. The GrayWolf binary is present and executable

        Returns:
            bool: True if both conditions are met
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Check the binary in INSTALL_DIR
        if os.path.isfile(self.graywolf_binary_path) and \
                os.access(self.graywolf_binary_path, os.X_OK):
            return True

        # Also check if it was installed somewhere on PATH
        return shutil.which(self.GRAYWOLF_BINARY) is not None

    def get_install_info(self):
        """
        Read the installation marker data.

        Returns:
            dict: Marker contents or empty dict if not found
        """
        return self.read_marker(self.INSTALL_MARKER)

    def get_version(self):
        """
        Get the installed GrayWolf binary version.

        Tries common version flags in order.

        Returns:
            str: Version string or None if not determinable
        """
        binary = (
            shutil.which(self.GRAYWOLF_BINARY) or
            (self.graywolf_binary_path
             if os.path.exists(self.graywolf_binary_path)
             else None)
        )

        if not binary:
            return None

        for flag in ['--version', '-version', 'version', '-v']:
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
                    # Return first non-empty line
                    first_line = output.splitlines()[0]
                    return first_line[:80]
            except Exception:
                continue

        return 'installed'

    # ----------------------------------------------------------
    # Go toolchain checks
    # ----------------------------------------------------------

    def _check_go_available(self):
        """
        Verify the Go toolchain is installed and accessible.

        Checks:
        1. 'go' binary exists in PATH
        2. 'go version' runs successfully

        Returns:
            tuple: (available: bool, info_string: str)
                   info_string is the version on success
                   or an error description on failure
        """
        go_binary = shutil.which('go')

        if not go_binary:
            # Also check GOROOT directly in case PATH is wrong
            if self.goroot:
                go_in_root = os.path.join(
                    self.goroot, 'bin', 'go'
                )
                if os.path.exists(go_in_root):
                    go_binary = go_in_root
                else:
                    return (
                        False,
                        f"go binary not found in PATH or "
                        f"GOROOT ({self.goroot}/bin/go)"
                    )
            else:
                return False, "go binary not found in PATH"

        ok, stdout, stderr = self._run_go_command(
            [go_binary, 'version'],
            timeout=15
        )

        if ok and stdout.strip():
            version_line = stdout.strip()
            print(f"[GrayWolf] Go version: {version_line}")
            return True, version_line

        return (
            False,
            stderr or "go version command failed"
        )

    def _parse_version_tuple(self, version_str):
        """
        Parse a Go version string into a comparable tuple.

        Handles formats like:
            '1.22.3'   -> (1, 22, 3)
            '1.21'     -> (1, 21, 0)
            '1.26.2'   -> (1, 26, 2)

        Args:
            version_str: Version string to parse

        Returns:
            tuple: (major, minor, patch) integers
        """
        try:
            parts = version_str.strip().split('.')
            # Pad to 3 parts
            while len(parts) < 3:
                parts.append('0')
            return tuple(int(x) for x in parts[:3])
        except (ValueError, AttributeError):
            return (0, 0, 0)

    def _check_go_version_compatible(self, go_mod_dir):
        """
        Verify installed Go version meets go.mod requirement.

        Reads the 'go' directive from go.mod and compares
        it with the installed Go version. Provides a clear,
        actionable error message if incompatible.

        Args:
            go_mod_dir: Directory containing go.mod file

        Returns:
            tuple: (
                compatible: bool,
                installed_ver: str,
                required_ver: str
            )
        """
        go_mod_path = os.path.join(go_mod_dir, 'go.mod')

        if not os.path.exists(go_mod_path):
            print(
                "[GrayWolf] WARNING: go.mod not found at "
                f"{go_mod_path}"
            )
            return True, 'unknown', 'unknown'

        # -------------------------------------------------------
        # Read required version from go.mod
        # The relevant line looks like: "go 1.26.2"
        # -------------------------------------------------------
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
                f"[GrayWolf] WARNING: Cannot read go.mod: "
                f"{e}"
            )
            return True, 'unknown', 'unknown'

        if not required_version:
            print(
                "[GrayWolf] WARNING: No 'go' directive "
                "found in go.mod"
            )
            return True, 'unknown', 'unknown'

        print(
            f"[GrayWolf] go.mod requires: Go {required_version}"
        )

        # -------------------------------------------------------
        # Get installed Go version
        # -------------------------------------------------------
        ok, stdout, stderr = self._run_go_command(
            ['go', 'version'],
            timeout=10
        )

        if not ok or not stdout:
            return (
                False,
                'not found',
                required_version
            )

        # Parse installed version from output like:
        # "go version go1.22.3 linux/amd64"
        installed_version = None
        match = re.search(
            r'go(\d+\.\d+(?:\.\d+)?)',
            stdout
        )
        if match:
            installed_version = match.group(1)
        else:
            print(
                f"[GrayWolf] WARNING: Cannot parse Go "
                f"version from: {stdout.strip()}"
            )
            return True, stdout.strip(), required_version

        # -------------------------------------------------------
        # Compare versions
        # -------------------------------------------------------
        installed_tuple = self._parse_version_tuple(
            installed_version
        )
        required_tuple = self._parse_version_tuple(
            required_version
        )

        compatible = installed_tuple >= required_tuple

        if compatible:
            print(
                f"[GrayWolf] ✓ Go version compatible: "
                f"{installed_version} >= {required_version}"
            )
        else:
            print(
                f"[GrayWolf] ERROR: Go version incompatible!"
            )
            print(
                f"[GrayWolf]   Installed : Go {installed_version}"
            )
            print(
                f"[GrayWolf]   Required  : Go {required_version}"
                f" (from go.mod)"
            )
            print(
                f"[GrayWolf]   ----------------------------------------"
            )
            print(
                f"[GrayWolf]   Fix: Update the Dockerfile ARG:"
            )
            print(
                f"[GrayWolf]     ARG GO_VERSION={required_version}"
            )
            print(
                f"[GrayWolf]   Then rebuild the Docker image:"
            )
            print(
                f"[GrayWolf]     docker compose build --no-cache"
            )
            print(
                f"[GrayWolf]   ----------------------------------------"
            )

        return compatible, installed_version, required_version

    # ----------------------------------------------------------
    # Installation methods
    # ----------------------------------------------------------

    def install_python_packages(self):
        """
        Install required Python packages.

        Delegates to BaseInstaller.install_python_packages()
        which handles Docker environments correctly by
        checking availability rather than installing.

        Returns:
            bool: True if all packages are available
        """
        print(
            "[GrayWolf] Installing required Python packages..."
        )

        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )

        if failed:
            if self.in_docker:
                print(
                    f"[GrayWolf] INFO: Packages not in Docker "
                    f"image: {failed}. Add to requirements.txt."
                )
            else:
                print(
                    f"[GrayWolf] WARNING: Failed packages: "
                    f"{failed}"
                )

        return len(failed) == 0
        
        def _find_main_package_dir(self, repo_root):
        """
        Find the directory containing the main Go package.

        In many Go repositories the main package (the
        executable entry point) is not in the repository
        root but in a subdirectory such as:
            cmd/graywolf/
            cmd/
            main/
            src/

        This method scans the repository for .go files
        containing 'package main' to find the correct
        directory to pass to 'go build'.

        Args:
            repo_root: Root directory of the cloned repo

        Returns:
            str: Path to directory with main package,
                 or repo_root if not found elsewhere
        """
        print(
            "[GrayWolf] Scanning for main package..."
        )

        # Common locations to check first (fast path)
        common_locations = [
            os.path.join(repo_root, 'cmd', 'graywolf'),
            os.path.join(repo_root, 'cmd'),
            os.path.join(repo_root, 'main'),
            os.path.join(repo_root, 'src'),
            os.path.join(repo_root, 'app'),
        ]

        for location in common_locations:
            if os.path.isdir(location):
                go_files = [
                    f for f in os.listdir(location)
                    if f.endswith('.go')
                ]
                if go_files:
                    # Check if any file declares package main
                    for go_file in go_files:
                        filepath = os.path.join(
                            location, go_file
                        )
                        try:
                            with open(filepath, 'r') as f:
                                content = f.read(512)
                            if 'package main' in content:
                                print(
                                    f"[GrayWolf] main package "
                                    f"found: {location}"
                                )
                                return location
                        except Exception:
                            continue

        # Full scan of repository for package main
        print(
            "[GrayWolf] Scanning all directories for "
            "package main..."
        )

        main_dirs = []
        for root, dirs, files in os.walk(repo_root):
            # Skip hidden dirs and vendor/test dirs
            dirs[:] = [
                d for d in dirs
                if not d.startswith('.') and
                d not in ('vendor', 'testdata', '_test')
            ]

            go_files = [f for f in files if f.endswith('.go')]
            if not go_files:
                continue

            # Check for package main declaration
            for go_file in go_files:
                filepath = os.path.join(root, go_file)
                try:
                    with open(filepath, 'r',
                              errors='ignore') as f:
                        # Only read enough to find declaration
                        content = f.read(256)
                    if 'package main' in content:
                        main_dirs.append(root)
                        print(
                            f"[GrayWolf] Found package main: "
                            f"{root}"
                        )
                        break
                except Exception:
                    continue

        if len(main_dirs) == 1:
            return main_dirs[0]
        elif len(main_dirs) > 1:
            # Prefer the shortest path (most likely root cmd)
            shortest = min(main_dirs, key=len)
            print(
                f"[GrayWolf] Multiple main packages found, "
                f"using: {shortest}"
            )
            return shortest

        # No main package found - log repo structure and
        # fall back to repo root
        print(
            "[GrayWolf] WARNING: No package main found. "
            "Repository structure:"
        )
        self._log_directory_tree(repo_root, max_depth=3)

        return repo_root

    def _log_directory_tree(self, path, max_depth=3,
                             current_depth=0, prefix=''):
        """
        Log the directory tree for diagnostic purposes.

        Shows the repository layout when the main package
        cannot be found, helping diagnose build failures.

        Args:
            path: Directory to log
            max_depth: Maximum depth to traverse
            current_depth: Current recursion depth
            prefix: Indentation prefix string
        """
        if current_depth > max_depth:
            return

        try:
            entries = sorted(os.listdir(path))
            for entry in entries:
                if entry.startswith('.'):
                    continue
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    print(f"[GrayWolf]   {prefix}{entry}/")
                    self._log_directory_tree(
                        full_path,
                        max_depth,
                        current_depth + 1,
                        prefix + '  '
                    )
                else:
                    print(f"[GrayWolf]   {prefix}{entry}")
        except Exception:
            pass

    def _install_rust(self):
        """
        Install Rust toolchain via rustup.

        GrayWolf's modem component (graywolf-modem) is
        written in Rust and requires cargo to build.

        Uses the official rustup installer which works
        on all Linux distributions.

        Returns:
            bool: True if Rust was installed successfully
        """
        print("[GrayWolf] Installing Rust via rustup...")

        try:
            env = self._get_go_env()
            env['CARGO_HOME'] = os.path.expanduser(
                '~/.cargo'
            )
            env['RUSTUP_HOME'] = os.path.expanduser(
                '~/.rustup'
            )

            # Download and run rustup installer
            result = subprocess.run(
                [
                    'sh', '-c',
                    'curl --proto "=https" --tlsv1.2 '
                    '-sSf https://sh.rustup.rs | '
                    'sh -s -- -y --no-modify-path'
                ],
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )

            if result.returncode == 0:
                # Add cargo to PATH for subsequent commands
                cargo_bin = os.path.expanduser('~/.cargo/bin')
                env['PATH'] = (
                    f"{cargo_bin}:{env.get('PATH', '')}"
                )
                os.environ['PATH'] = (
                    f"{cargo_bin}:{os.environ.get('PATH', '')}"
                )

                print("[GrayWolf] ✓ Rust installed")
                return True
            else:
                print(
                    f"[GrayWolf] Rust install failed: "
                    f"{result.stderr[:200]}"
                )
                return False

        except Exception as e:
            print(f"[GrayWolf] Rust install error: {e}")
            return False

    def _build_graywolf_modem(self, repo_dir):
        """
        Build the graywolf-modem companion binary.

        graywolf-modem is a Rust binary required by the
        main GrayWolf server. Without it, GrayWolf exits
        immediately with:
            'graywolf-modem binary not found'

        Build methods tried in order:
            1. cargo build --release in graywolf-modem/
            2. cargo build --release in repo root
            3. Download pre-built binary from GitHub releases

        Args:
            repo_dir: GrayWolf repository root directory

        Returns:
            tuple: (success: bool, binary_path_or_error: str)
        """
        modem_binary_name = 'graywolf-modem'
        modem_output_path = os.path.join(
            self.INSTALL_DIR, modem_binary_name
        )

        # -------------------------------------------------------
        # Try building from source with cargo
        # -------------------------------------------------------
        cargo = (
            shutil.which('cargo') or
            os.path.expanduser('~/.cargo/bin/cargo')
        )

        if cargo and os.path.exists(cargo):
            print(
                "[GrayWolf] Building graywolf-modem "
                "with cargo..."
            )

            # Find the Rust source directory
            modem_src_dir = None
            for candidate in [
                os.path.join(repo_dir, 'graywolf-modem'),
                os.path.join(repo_dir, 'modem'),
                repo_dir,  # Sometimes in root
            ]:
                cargo_toml = os.path.join(
                    candidate, 'Cargo.toml'
                )
                if os.path.exists(cargo_toml):
                    modem_src_dir = candidate
                    print(
                        f"[GrayWolf] Cargo.toml found: "
                        f"{candidate}"
                    )
                    break

            if modem_src_dir:
                env = self._get_go_env()
                cargo_home = os.path.expanduser('~/.cargo')
                env['CARGO_HOME'] = cargo_home
                env['PATH'] = (
                    f"{cargo_home}/bin:"
                    f"{env.get('PATH', '')}"
                )

                try:
                    result = subprocess.run(
                        [cargo, 'build', '--release'],
                        cwd=modem_src_dir,
                        capture_output=True,
                        text=True,
                        timeout=600,
                        env=env
                    )

                    if result.returncode == 0:
                        # Find the built binary
                        release_binary = os.path.join(
                            modem_src_dir,
                            'target', 'release',
                            modem_binary_name
                        )

                        if os.path.exists(release_binary):
                            shutil.copy2(
                                release_binary,
                                modem_output_path
                            )
                            os.chmod(modem_output_path, 0o755)
                            print(
                                f"[GrayWolf] ✓ "
                                f"graywolf-modem built: "
                                f"{modem_output_path}"
                            )
                            return True, modem_output_path
                        else:
                            print(
                                "[GrayWolf] cargo succeeded "
                                "but binary not found at "
                                f"{release_binary}"
                            )
                    else:
                        print(
                            f"[GrayWolf] cargo build failed: "
                            f"{result.stderr[:300]}"
                        )

                except subprocess.TimeoutExpired:
                    print(
                        "[GrayWolf] cargo build timed out"
                    )
                except Exception as e:
                    print(
                        f"[GrayWolf] cargo build error: {e}"
                    )

        # -------------------------------------------------------
        # Fallback: Download pre-built binary from GitHub
        # -------------------------------------------------------
        print(
            "[GrayWolf] Attempting to download "
            "pre-built graywolf-modem..."
        )

        downloaded = self._download_graywolf_modem(
            modem_output_path
        )
        if downloaded:
            return True, modem_output_path

        return False, (
            "Could not build or download graywolf-modem. "
            "Install Rust and retry: "
            "curl --proto '=https' --tlsv1.2 "
            "-sSf https://sh.rustup.rs | sh"
        )

    def _install_from_release(self):
        """
        Install GrayWolf from the official GitHub release.

        This is the preferred installation method because:
            1. Faster than building from source
            2. More reliable — no compiler dependencies
            3. Includes both graywolf AND graywolf-modem
               already compiled and tested
            4. Uses the exact same binaries as official docs

        The release tar.gz for linux_x86_64 contains:
            graywolf         - Main server binary (Go)
            graywolf-modem   - Radio modem binary (Rust)
            README.md
            LICENSE

        Both binaries are extracted and installed to
        ~/.local/bin/ which is on the hamradio user PATH.

        Returns:
            bool: True if both binaries installed
        """
        import urllib.request
        import tarfile

        # -------------------------------------------------------
        # Step 1: Get latest release info from GitHub API
        # -------------------------------------------------------
        api_url = (
            'https://api.github.com/repos/'
            'chrissnell/graywolf/releases/latest'
        )

        print(
            "[GrayWolf] Fetching latest release info..."
        )

        try:
            req = urllib.request.Request(
                api_url,
                headers={
                    'User-Agent': 'HamRadioApp/1.0',
                    'Accept': 'application/vnd.github.v3+json'
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
                f"[GrayWolf] GitHub API error: {e}"
            )
            return False

        tag = release_data.get('tag_name', 'unknown')
        print(
            f"[GrayWolf] Latest release: {tag}"
        )

        # Log all available assets for diagnostics
        assets = release_data.get('assets', [])
        print(
            f"[GrayWolf] Available assets "
            f"({len(assets)} total):"
        )
        for asset in assets:
            print(f"  {asset['name']}")

        # -------------------------------------------------------
        # Step 2: Find the correct asset for this platform
        # -------------------------------------------------------
        arch = platform.machine().lower()

        # Map platform.machine() to release asset naming
        arch_patterns = []
        if arch == 'x86_64':
            arch_patterns = [
                'x86_64',    # graywolf_0.11.4_linux_x86_64
                'amd64',     # graywolf_0.11.4_linux_amd64
            ]
        elif arch in ('aarch64', 'arm64'):
            arch_patterns = [
                'arm64',     # graywolf_0.11.4_linux_arm64
                'aarch64',
            ]
        else:
            arch_patterns = [arch]

        print(
            f"[GrayWolf] Platform: linux/{arch} "
            f"(patterns: {arch_patterns})"
        )

        # Find tar.gz asset matching linux + arch
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
                        f"[GrayWolf] ✓ Matched asset: "
                        f"{asset_name}"
                    )
                    break
            if download_url:
                break

        if not download_url:
            # Try .deb as fallback on apt systems
            if self._package_manager == 'apt-get':
                for pattern in arch_patterns:
                    for asset in assets:
                        name = asset['name'].lower()
                        if (name.endswith('.deb') and
                                pattern in name):
                            download_url = (
                                asset['browser_download_url']
                            )
                            asset_name = asset['name']
                            print(
                                f"[GrayWolf] Using .deb: "
                                f"{asset_name}"
                            )
                            break
                    if download_url:
                        break

            if not download_url:
                print(
                    f"[GrayWolf] ERROR: No matching asset "
                    f"found for linux/{arch}"
                )
                print(
                    "[GrayWolf] Expected a .tar.gz "
                    "containing graywolf and graywolf-modem"
                )
                return False

        # -------------------------------------------------------
        # Step 3: Download the release archive
        # -------------------------------------------------------
        download_dir = os.path.join(
            os.path.expanduser('~'),
            '.graywolf_download'
        )
        os.makedirs(download_dir, exist_ok=True)

        archive_path = os.path.join(
            download_dir, asset_name
        )

        print(
            f"[GrayWolf] Downloading {asset_name}..."
        )

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
                    if pct % 20 == 0:
                        print(
                            f"[GrayWolf]   Download: "
                            f"{pct}% "
                            f"({downloaded//1024} KB)"
                        )

            urllib.request.urlretrieve(
                download_url,
                archive_path,
                reporthook=progress_hook
            )

            size_kb = os.path.getsize(archive_path) / 1024
            print(
                f"[GrayWolf] ✓ Downloaded "
                f"{size_kb:.0f} KB"
            )

        except Exception as e:
            print(
                f"[GrayWolf] Download failed: {e}"
            )
            return False

        # -------------------------------------------------------
        # Step 4: Extract and install binaries
        # -------------------------------------------------------
        os.makedirs(self.INSTALL_DIR, exist_ok=True)

        installed_binaries = []

        try:
            if asset_name.endswith('.tar.gz'):
                installed_binaries = (
                    self._extract_tar_gz(
                        archive_path,
                        download_dir
                    )
                )

            elif asset_name.endswith('.deb'):
                installed_binaries = (
                    self._install_deb(archive_path)
                )

            else:
                print(
                    f"[GrayWolf] Unsupported archive "
                    f"format: {asset_name}"
                )
                return False

        except Exception as e:
            print(
                f"[GrayWolf] Extraction error: {e}"
            )
            traceback.print_exc()
            return False

        finally:
            # Clean up download directory
            if os.path.exists(download_dir):
                shutil.rmtree(
                    download_dir, ignore_errors=True
                )

        # -------------------------------------------------------
        # Step 5: Verify both required binaries are installed
        # -------------------------------------------------------
        required = ['graywolf', 'graywolf-modem']
        missing = []

        for binary in required:
            path = os.path.join(self.INSTALL_DIR, binary)
            if os.path.isfile(path) and \
                    os.access(path, os.X_OK):
                size_kb = os.path.getsize(path) / 1024
                print(
                    f"[GrayWolf] ✓ {binary}: "
                    f"{size_kb:.0f} KB"
                )
            else:
                missing.append(binary)
                print(
                    f"[GrayWolf] ✗ {binary}: NOT FOUND"
                )

        if missing:
            print(
                f"[GrayWolf] ERROR: Missing binaries: "
                f"{missing}"
            )
            print(
                "[GrayWolf] Contents of INSTALL_DIR:"
            )
            try:
                for f in os.listdir(self.INSTALL_DIR):
                    print(f"  {f}")
            except Exception:
                pass
            return False

        print(
            "[GrayWolf] ✓ Both binaries installed "
            "successfully"
        )
        return True

    def _extract_tar_gz(self, archive_path, extract_dir):
        """
        Extract binaries from a tar.gz archive.

        Searches for executable files named graywolf
        and graywolf-modem in the archive and installs
        them to INSTALL_DIR.

        Args:
            archive_path: Path to the .tar.gz file
            extract_dir: Directory to extract into

        Returns:
            list: Names of successfully installed binaries
        """
        import tarfile

        installed = []
        target_binaries = {'graywolf', 'graywolf-modem'}

        print(
            f"[GrayWolf] Extracting {archive_path}..."
        )

        with tarfile.open(archive_path, 'r:gz') as tar:
            # List archive contents for diagnostics
            members = tar.getmembers()
            print(
                f"[GrayWolf] Archive contains "
                f"{len(members)} files:"
            )
            for member in members:
                print(
                    f"  {member.name} "
                    f"({member.size} bytes)"
                )

            # Extract target binaries
            for member in members:
                # Get just the filename
                filename = os.path.basename(member.name)

                if filename in target_binaries:
                    print(
                        f"[GrayWolf] Extracting: "
                        f"{member.name}"
                    )

                    dest_path = os.path.join(
                        self.INSTALL_DIR, filename
                    )

                    # Extract file content
                    extracted_file = tar.extractfile(member)
                    if extracted_file:
                        with open(dest_path, 'wb') as f:
                            f.write(extracted_file.read())

                        # Make executable
                        os.chmod(dest_path, 0o755)

                        size_kb = (
                            os.path.getsize(dest_path) / 1024
                        )
                        print(
                            f"[GrayWolf] ✓ Installed "
                            f"{filename}: {size_kb:.0f} KB"
                        )
                        installed.append(filename)

        return installed

    def _install_deb(self, deb_path):
        """
        Install GrayWolf from a .deb package.

        Extracts binaries from the .deb data archive
        without requiring dpkg (works for non-root users).

        .deb structure:
            debian-binary   - Version file
            control.tar.*   - Package metadata
            data.tar.*      - Actual files to install

        Args:
            deb_path: Path to the .deb file

        Returns:
            list: Names of installed binaries
        """
        import tarfile

        installed = []
        target_binaries = {'graywolf', 'graywolf-modem'}

        print(
            f"[GrayWolf] Extracting .deb: {deb_path}..."
        )

        # .deb files are ar archives
        # Extract them manually by reading the ar format
        extract_dir = os.path.join(
            os.path.dirname(deb_path), 'deb_extract'
        )
        os.makedirs(extract_dir, exist_ok=True)

        try:
            # Use ar command if available
            if shutil.which('ar'):
                subprocess.run(
                    ['ar', 'x', deb_path],
                    cwd=extract_dir,
                    capture_output=True,
                    timeout=30
                )
            else:
                print(
                    "[GrayWolf] 'ar' not available, "
                    "trying dpkg-deb..."
                )
                if shutil.which('dpkg-deb'):
                    subprocess.run(
                        [
                            'dpkg-deb', '--extract',
                            deb_path, extract_dir
                        ],
                        capture_output=True,
                        timeout=30
                    )
                else:
                    print(
                        "[GrayWolf] ERROR: Neither 'ar' nor "
                        "'dpkg-deb' available"
                    )
                    return installed

            # Find data.tar.* in the extracted .deb
            data_tar = None
            for f in os.listdir(extract_dir):
                if f.startswith('data.tar'):
                    data_tar = os.path.join(
                        extract_dir, f
                    )
                    break

            if not data_tar:
                # dpkg-deb --extract puts files directly
                # Search for our binaries in extract_dir
                for root, dirs, files in os.walk(
                    extract_dir
                ):
                    for filename in files:
                        if filename in target_binaries:
                            src = os.path.join(root, filename)
                            dst = os.path.join(
                                self.INSTALL_DIR, filename
                            )
                            shutil.copy2(src, dst)
                            os.chmod(dst, 0o755)
                            installed.append(filename)
                            print(
                                f"[GrayWolf] ✓ Installed "
                                f"{filename}"
                            )
                return installed

            # Extract binaries from data.tar
            with tarfile.open(data_tar) as tar:
                for member in tar.getmembers():
                    filename = os.path.basename(member.name)
                    if filename in target_binaries:
                        extracted = tar.extractfile(member)
                        if extracted:
                            dst = os.path.join(
                                self.INSTALL_DIR, filename
                            )
                            with open(dst, 'wb') as f:
                                f.write(extracted.read())
                            os.chmod(dst, 0o755)
                            installed.append(filename)
                            print(
                                f"[GrayWolf] ✓ Installed "
                                f"{filename}"
                            )

        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

        return installed

    def _build_with_make(self, repo_dir):
        """
        Attempt to build GrayWolf using 'make release'.

        This builds both graywolf and graywolf-modem in
        one step using the repository Makefile.

        NOTE: This requires Rust/cargo for graywolf-modem.
        The Rust workspace issue (profiles for non-root
        package) is a warning, not a fatal error — the
        build should still succeed if we build from the
        workspace root.

        Args:
            repo_dir: Repository root directory

        Returns:
            tuple: (success: bool, error_message: str)
        """
        if not shutil.which('make'):
            return False, "make not available"

        # Check for Makefile
        if not os.path.exists(
            os.path.join(repo_dir, 'Makefile')
        ):
            return False, "No Makefile found"

        # Check cargo
        cargo = (
            shutil.which('cargo') or
            os.path.expanduser('~/.cargo/bin/cargo')
        )

        if not (cargo and os.path.exists(cargo)):
            print(
                "[GrayWolf] cargo not found — "
                "'make release' requires Rust"
            )
            return False, "cargo not available"

        print("[GrayWolf] Running 'make release'...")
        print(
            "[GrayWolf] (This may take several minutes "
            "for the Rust compilation)"
        )

        env = self._get_go_env()
        # Ensure cargo is on PATH
        cargo_bin = os.path.expanduser('~/.cargo/bin')
        env['PATH'] = f"{cargo_bin}:{env.get('PATH', '')}"
        env['CARGO_HOME'] = os.path.expanduser('~/.cargo')

        try:
            result = subprocess.run(
                ['make', 'release'],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=600,
                env=env
            )

            if result.returncode == 0:
                print(
                    "[GrayWolf] ✓ 'make release' succeeded"
                )
                return True, ""

            # Check if it's just a warning (not a real error)
            # The workspace profile warning is non-fatal
            stderr = result.stderr or ''
            stdout = result.stdout or ''
            combined = stderr + stdout

            if ('warning: profiles for the non root '
                    'package' in combined and
                    result.returncode != 0):
                # Check if binaries were actually built
                # despite the warning
                graywolf_built = os.path.exists(
                    os.path.join(repo_dir, 'graywolf')
                )
                modem_built = os.path.exists(
                    os.path.join(
                        repo_dir, 'target',
                        'release', 'graywolf-modem'
                    )
                )

                if graywolf_built or modem_built:
                    print(
                        "[GrayWolf] Make had warnings but "
                        "binaries were built"
                    )
                    return True, ""

            error_msg = (
                stderr[-500:] if stderr else
                f"exit code {result.returncode}"
            )
            return False, error_msg

        except subprocess.TimeoutExpired:
            return False, "make timed out after 600s"
        except Exception as e:
            return False, str(e)

    def clone_and_build(self):
        """
        Install GrayWolf — tries release package first,
        then falls back to building from source.

        Installation strategy (in order):
            1. Download official release tar.gz from GitHub
               (fastest, most reliable, includes both
               graywolf and graywolf-modem pre-built)
            2. If release download fails, clone and build
               from source using 'make release'
            3. If make fails, build graywolf with go build
               and graywolf-modem with cargo separately

        Returns:
            bool: True if both binaries installed
        """
        os.makedirs(self.INSTALL_DIR, exist_ok=True)

        # -------------------------------------------------------
        # Strategy 1: Install from GitHub release package
        # Fastest and most reliable - no compiler needed
        # -------------------------------------------------------
        print(
            "\n[GrayWolf] Strategy 1: "
            "Install from GitHub release..."
        )

        release_success = self._install_from_release()

        if release_success:
            print(
                "[GrayWolf] ✓ Installed from release package"
            )
            return True

        print(
            "[GrayWolf] Release install failed, "
            "falling back to source build..."
        )

        # -------------------------------------------------------
        # Strategy 2: Build from source
        # -------------------------------------------------------
        print(
            "\n[GrayWolf] Strategy 2: "
            "Building from source..."
        )

        build_dir = os.path.join(
            os.path.expanduser('~'),
            '.graywolf_build'
        )

        try:
            # Clean build directory
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)
            os.makedirs(build_dir, exist_ok=True)

            # Clone repository
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

            # Show repo structure
            print("[GrayWolf] Repository contents:")
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
                print("[GrayWolf] ERROR: go.mod not found")
                return False

            # Verify go.mod
            try:
                with open(
                    os.path.join(go_mod_dir, 'go.mod'), 'r'
                ) as f:
                    print(
                        f"[GrayWolf] go.mod:\n{f.read()[:300]}"
                    )
            except Exception:
                pass

            # Check Go version
            compatible, inst, req = (
                self._check_go_version_compatible(go_mod_dir)
            )
            if not compatible:
                print(
                    f"[GrayWolf] ERROR: Go {inst} < {req}"
                )
                return False

            # Download Go dependencies
            print("[GrayWolf] Downloading Go dependencies...")
            self._run_go_command(
                ['go', 'mod', 'download'],
                cwd=go_mod_dir,
                timeout=300
            )

            # Try make release (builds both binaries)
            print("[GrayWolf] Trying 'make release'...")
            make_ok, make_err = self._build_with_make(
                go_mod_dir
            )

            if make_ok:
                # Find and install both binaries
                gw_ok = self._find_and_install_binary(
                    go_mod_dir,
                    'graywolf',
                    self.graywolf_binary_path
                )
                modem_path = os.path.join(
                    self.INSTALL_DIR, 'graywolf-modem'
                )
                modem_ok = self._find_and_install_binary(
                    go_mod_dir,
                    'graywolf-modem',
                    modem_path
                )

                if gw_ok and modem_ok:
                    print(
                        "[GrayWolf] ✓ Both binaries "
                        "installed from make"
                    )
                    return True

            # Build graywolf with go build
            print(
                "[GrayWolf] Building graywolf with go..."
            )
            main_pkg = self._find_main_package_dir(
                go_mod_dir
            )

            if main_pkg == go_mod_dir:
                build_target = '.'
            else:
                rel = os.path.relpath(main_pkg, go_mod_dir)
                build_target = f'./{rel}'

            gw_output = os.path.join(
                go_mod_dir, 'graywolf'
            )
            ok, stdout, stderr = self._run_go_command(
                [
                    'go', 'build', '-v',
                    '-o', gw_output, build_target
                ],
                cwd=go_mod_dir,
                timeout=300
            )

            if not ok:
                print(
                    f"[GrayWolf] go build failed: {stderr}"
                )
                return False

            # Install graywolf binary
            gw_ok = self._find_and_install_binary(
                go_mod_dir,
                'graywolf',
                self.graywolf_binary_path
            )

            if not gw_ok:
                print(
                    "[GrayWolf] ERROR: graywolf binary "
                    "not found after build"
                )
                return False

            # Build graywolf-modem separately
            print(
                "[GrayWolf] Building graywolf-modem..."
            )
            modem_path = os.path.join(
                self.INSTALL_DIR, 'graywolf-modem'
            )
            modem_ok, modem_result = (
                self._build_graywolf_modem(go_mod_dir)
            )

            if not modem_ok:
                print(
                    f"[GrayWolf] ERROR: graywolf-modem "
                    f"build failed: {modem_result}"
                )
                return False

            # Verify both installed
            for binary, path in [
                ('graywolf', self.graywolf_binary_path),
                ('graywolf-modem', modem_path)
            ]:
                if not (os.path.isfile(path) and
                        os.access(path, os.X_OK)):
                    print(
                        f"[GrayWolf] ERROR: {binary} "
                        f"not executable at {path}"
                    )
                    return False

                size = os.path.getsize(path) / 1024
                print(
                    f"[GrayWolf] ✓ {binary}: {size:.0f} KB"
                )

            return True

        except Exception as e:
            print(
                f"[GrayWolf] Source build error: {e}"
            )
            traceback.print_exc()
            return False

        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(
                    build_dir, ignore_errors=True
                )
                print(
                    "[GrayWolf] Build directory cleaned up"
                )
                
    def _find_and_install_binary(self, search_root,
                                  binary_name, dest_path):
        """
        Search for a built binary and install it.

        Searches common build output locations:
            - repo root
            - target/release/
            - build/
            - cmd/<name>/

        Args:
            search_root: Repository root to search
            binary_name: Binary filename to find
            dest_path: Destination installation path

        Returns:
            bool: True if found and installed
        """
        # Common locations to check
        candidates = [
            os.path.join(search_root, binary_name),
            os.path.join(search_root, 'target',
                         'release', binary_name),
            os.path.join(search_root, 'build',
                         binary_name),
            os.path.join(search_root, 'bin', binary_name),
        ]

        # Also do a recursive search
        for root, dirs, files in os.walk(search_root):
            dirs[:] = [
                d for d in dirs
                if d not in ('.git', 'vendor')
            ]
            if binary_name in files:
                candidate = os.path.join(root, binary_name)
                if os.access(candidate, os.X_OK):
                    candidates.insert(0, candidate)

        for candidate in candidates:
            if os.path.isfile(candidate) and \
                    os.access(candidate, os.X_OK):
                print(
                    f"[GrayWolf] Found {binary_name}: "
                    f"{candidate}"
                )
                shutil.copy2(candidate, dest_path)
                os.chmod(dest_path, 0o755)
                return True

        return False

    def write_install_marker(self, method, version=None):
        """
        Write installation marker with GrayWolf metadata.

        Calls BaseInstaller.write_marker() with the
        extra_data keyword argument.

        Args:
            method: Installation method ('source', 'existing')
            version: GrayWolf version string if available
        """
        # Get installed Go version for the marker
        go_version = None
        try:
            result = subprocess.run(
                ['go', 'version'],
                capture_output=True,
                text=True,
                timeout=5,
                env=self._get_go_env()
            )
            if result.returncode == 0:
                go_version = result.stdout.strip()
        except Exception:
            pass

        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': method,
                'version': version,
                'binary_path': self.graywolf_binary_path,
                'platform': platform.platform(),
                'arch': platform.machine(),
                'go_version': go_version,
            }
        )

    # ----------------------------------------------------------
    # Main entry point
    # ----------------------------------------------------------

    def run(self):
        """
        Execute the complete first-run installation process.

        This is the primary public method called by the
        GrayWolfPlugin's initialize() method on first run.

        Installation steps:
            1. Check if already installed (skip if so)
            2. Check if binary already in PATH (mark + skip)
            3. Verify Go toolchain is available
            4. Install Python packages
            5. Verify git is available
            6. Clone and build GrayWolf
            7. Write installation marker

        Error behaviour:
            If any critical step fails, the method returns
            False. The plugin UI still loads but shows an
            install button. Full error details are printed
            to Docker logs.

        Returns:
            bool: True if installed successfully or
                  already installed. False if build failed.
        """
        # -------------------------------------------------------
        # Already installed — nothing to do
        # -------------------------------------------------------
        if self.is_installed():
            print("[GrayWolf] ✓ Already installed")
            return True

        # -------------------------------------------------------
        # Binary in PATH but no marker file
        # Write the marker and continue
        # -------------------------------------------------------
        existing_binary = shutil.which(self.GRAYWOLF_BINARY)
        if existing_binary:
            print(
                f"[GrayWolf] ✓ Found existing binary: "
                f"{existing_binary}"
            )
            version = self.get_version()
            self.write_install_marker('existing', version)
            return True

        print("[GrayWolf] ================================")
        print("[GrayWolf] Starting first-run installation")
        print("[GrayWolf] ================================")

        # -------------------------------------------------------
        # Step 1: Check Go toolchain
        # -------------------------------------------------------
        print("\n[GrayWolf] Step 1: Checking Go toolchain...")

        go_available, go_info = self._check_go_available()

        if not go_available:
            print(
                f"[GrayWolf] ERROR: Go not available: {go_info}"
            )
            print(
                "[GrayWolf] Go is installed from go.dev in "
                "the Dockerfile."
            )
            print(
                "[GrayWolf] Check the Dockerfile has: "
                "ARG GO_VERSION=<version>"
            )
            print(
                "[GrayWolf] And the install RUN block using "
                "wget from go.dev/dl/"
            )
            print(
                "[GrayWolf] Rebuild: docker compose build "
                "--no-cache"
            )
            return False

        print(f"[GrayWolf] ✓ Go available: {go_info}")

        # -------------------------------------------------------
        # Step 2: Python packages (non-fatal)
        # -------------------------------------------------------
        print("\n[GrayWolf] Step 2: Python packages...")
        self.install_python_packages()
        # Non-fatal — plugin can run without all packages

        # -------------------------------------------------------
        # Step 3: Verify git
        # -------------------------------------------------------
        print("\n[GrayWolf] Step 3: Checking git...")
        if not shutil.which('git'):
            print(
                "[GrayWolf] ERROR: git not found in PATH"
            )
            print(
                "[GrayWolf] Add to Dockerfile: "
                "apt-get install -y git"
            )
            return False

        print("[GrayWolf] ✓ git available")

        # -------------------------------------------------------
        # Step 4: Clone and build
        # -------------------------------------------------------
        print("\n[GrayWolf] Step 4: Building GrayWolf...")

        success = self.clone_and_build()

        if not success:
            print(
                "\n[GrayWolf] ERROR: Build failed"
            )
            print(
                "[GrayWolf] See error messages above "
                "for the specific failure reason."
            )
            return False

        # -------------------------------------------------------
        # Step 5: Write installation marker
        # -------------------------------------------------------
        version = self.get_version()
        self.write_install_marker('source', version)

        print("\n[GrayWolf] ================================")
        print("[GrayWolf] ✓ Installation complete!")
        if version:
            print(f"[GrayWolf]   Version : {version}")
        print(
            f"[GrayWolf]   Binary  : "
            f"{self.graywolf_binary_path}"
        )
        print("[GrayWolf] ================================\n")

        return True
