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

    def clone_and_build(self):
        """
        Clone GrayWolf from GitHub and build the binary.

        Complete build pipeline:
            1. Create clean build directory
            2. Clone repository (shallow)
            3. Locate go.mod in cloned repo
            4. Verify Go version compatibility
            5. Find main package directory
               (may differ from go.mod location)
            6. Download Go module dependencies
            7. Compile binary with 'go build'
            8. Copy binary to INSTALL_DIR
            9. Verify installed binary executes

        Returns:
            bool: True if build and install successful
        """
        build_dir = os.path.join(
            os.path.expanduser('~'),
            '.graywolf_build'
        )

        try:
            # -------------------------------------------------------
            # Prepare clean build directory
            # -------------------------------------------------------
            if os.path.exists(build_dir):
                print(
                    "[GrayWolf] Removing previous build dir..."
                )
                shutil.rmtree(build_dir, ignore_errors=True)

            os.makedirs(build_dir, exist_ok=True)
            print(
                f"[GrayWolf] Build directory: {build_dir}"
            )

            # -------------------------------------------------------
            # Step 1: Clone repository
            # -------------------------------------------------------
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
                    f"[GrayWolf] ERROR: Clone failed: "
                    f"{stderr}"
                )
                return False

            print("[GrayWolf] ✓ Repository cloned")

            # -------------------------------------------------------
            # Step 2: Find go.mod (defines module root)
            # -------------------------------------------------------
            go_mod_dir = None
            for root, dirs, files in os.walk(build_dir):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith('.')
                ]
                if 'go.mod' in files:
                    go_mod_dir = root
                    print(
                        f"[GrayWolf] go.mod found: {root}"
                    )
                    break

            if not go_mod_dir:
                print(
                    "[GrayWolf] ERROR: go.mod not found"
                )
                self._log_directory_tree(build_dir)
                return False

            # Print go.mod for diagnostics
            go_mod_path = os.path.join(go_mod_dir, 'go.mod')
            try:
                with open(go_mod_path, 'r') as f:
                    go_mod_content = f.read()
                print(
                    f"[GrayWolf] go.mod content:\n"
                    f"{go_mod_content[:400]}"
                )
            except Exception:
                pass

            # -------------------------------------------------------
            # Step 3: Check Go version compatibility
            # -------------------------------------------------------
            print(
                "[GrayWolf] Checking Go version "
                "compatibility..."
            )
            compatible, installed_ver, required_ver = (
                self._check_go_version_compatible(go_mod_dir)
            )

            if not compatible:
                print(
                    f"[GrayWolf] ERROR: Cannot build with "
                    f"Go {installed_ver} — need "
                    f"Go {required_ver}"
                )
                return False

            # -------------------------------------------------------
            # Step 4: Find the main package directory
            #
            # CRITICAL FIX: go.mod may be in the repo root
            # but the .go source files (package main) may be
            # in a subdirectory like cmd/graywolf/.
            # 'go build .' fails with "no Go files" if run
            # in a directory containing only go.mod.
            # We must find the directory that has the .go files.
            # -------------------------------------------------------
            main_pkg_dir = self._find_main_package_dir(
                go_mod_dir
            )

            print(
                f"[GrayWolf] Build target directory: "
                f"{main_pkg_dir}"
            )

            # -------------------------------------------------------
            # Step 5: Download Go module dependencies
            # Must run from the go.mod directory (module root)
            # -------------------------------------------------------
            print(
                "[GrayWolf] Downloading Go dependencies..."
            )
            ok, stdout, stderr = self._run_go_command(
                ['go', 'mod', 'download'],
                cwd=go_mod_dir,    # Module root, not main pkg
                timeout=300
            )

            if not ok:
                print(
                    f"[GrayWolf] WARNING: go mod download: "
                    f"{stderr[:300]}"
                )
            else:
                print(
                    "[GrayWolf] ✓ Go dependencies downloaded"
                )

            # -------------------------------------------------------
            # Step 6: Build the binary
            #
            # Build output path is in go_mod_dir so the
            # binary is findable regardless of which subdir
            # contains the main package.
            # -------------------------------------------------------
            build_output_path = os.path.join(
                go_mod_dir,
                self.GRAYWOLF_BINARY
            )

            # Calculate the build target path relative to
            # the module root. This is what we pass to go build.
            if main_pkg_dir == go_mod_dir:
                # Main package is at module root
                build_target = '.'
            else:
                # Main package is in a subdirectory.
                # We need a path relative to go_mod_dir OR
                # the module path (e.g. ./cmd/graywolf)
                rel_path = os.path.relpath(
                    main_pkg_dir, go_mod_dir
                )
                build_target = f'./{rel_path}'

            print(
                f"[GrayWolf] Building: go build "
                f"-o {self.GRAYWOLF_BINARY} {build_target}"
            )

            ok, stdout, stderr = self._run_go_command(
                [
                    'go', 'build',
                    '-v',
                    '-o', build_output_path,
                    build_target
                ],
                cwd=go_mod_dir,    # Always run from module root
                timeout=300
            )

            if not ok:
                print(
                    "[GrayWolf] ERROR: go build failed"
                )
                print(
                    "[GrayWolf] ---- FULL BUILD ERROR ----"
                )
                if stdout and stdout.strip():
                    print(
                        f"[GrayWolf] STDOUT:\n"
                        f"{stdout.strip()}"
                    )
                if stderr and stderr.strip():
                    print(
                        f"[GrayWolf] STDERR:\n"
                        f"{stderr.strip()}"
                    )
                print(
                    "[GrayWolf] ---- END BUILD ERROR ----"
                )

                # Targeted guidance
                if stderr:
                    if 'no Go files' in stderr:
                        print(
                            "[GrayWolf] HINT: No .go files in "
                            f"build target '{build_target}'. "
                            "Repository structure:"
                        )
                        self._log_directory_tree(
                            go_mod_dir,
                            max_depth=4
                        )
                    elif 'invalid go version' in stderr:
                        ver_match = re.search(
                            r"invalid go version '([\d.]+)'",
                            stderr
                        )
                        if ver_match:
                            needed = ver_match.group(1)
                            print(
                                f"[GrayWolf] HINT: Update "
                                f"Dockerfile: "
                                f"ARG GO_VERSION={needed}"
                            )
                            print(
                                "[GrayWolf] Then rebuild: "
                                "docker compose build --no-cache"
                            )
                    elif 'permission denied' in stderr.lower():
                        print(
                            "[GrayWolf] HINT: Check GOPATH "
                            f"({self.gopath}) and GOCACHE "
                            f"({self.gocache}) are writable."
                        )
                return False

            if stdout and stdout.strip():
                pkg_count = len(stdout.strip().splitlines())
                print(
                    f"[GrayWolf] ✓ Build successful: "
                    f"{pkg_count} package(s) compiled"
                )
            else:
                print("[GrayWolf] ✓ Build successful")

            # -------------------------------------------------------
            # Step 7: Verify binary was created
            # -------------------------------------------------------
            if not os.path.isfile(build_output_path):
                print(
                    f"[GrayWolf] ERROR: Binary not found "
                    f"after build at {build_output_path}"
                )
                print(
                    "[GrayWolf] go_mod_dir contents:"
                )
                for item in os.listdir(go_mod_dir):
                    print(f"  {item}")
                return False

            size_kb = os.path.getsize(
                build_output_path
            ) / 1024
            print(
                f"[GrayWolf] Binary size: {size_kb:.1f} KB"
            )

            # -------------------------------------------------------
            # Step 8: Install binary to INSTALL_DIR
            # -------------------------------------------------------
            os.makedirs(self.INSTALL_DIR, exist_ok=True)

            shutil.copy2(
                build_output_path,
                self.graywolf_binary_path
            )
            os.chmod(self.graywolf_binary_path, 0o755)

            print(
                f"[GrayWolf] ✓ Binary installed: "
                f"{self.graywolf_binary_path}"
            )

            # -------------------------------------------------------
            # Step 9: Verify installed binary executes
            # -------------------------------------------------------
            print("[GrayWolf] Verifying installed binary...")
            verified = False
            for flag in ['--version', '-version', '-h', '--help']:
                try:
                    result = subprocess.run(
                        [self.graywolf_binary_path, flag],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env=self._get_go_env()
                    )
                    output = (
                        result.stdout + result.stderr
                    ).strip()
                    if output:
                        first_line = output.splitlines()[0]
                        print(
                            f"[GrayWolf] ✓ Binary response: "
                            f"{first_line[:80]}"
                        )
                        verified = True
                        break
                except Exception:
                    continue

            if not verified:
                # Binary runs but gives no output — still ok
                # as long as the file exists and is executable
                print(
                    "[GrayWolf] ✓ Binary installed "
                    "(no version output)"
                )

            return True

        except Exception as e:
            print(
                f"[GrayWolf] Unexpected error during "
                f"build: {e}"
            )
            traceback.print_exc()
            return False

        finally:
            # Always remove build directory
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)
                print(
                    "[GrayWolf] Build directory cleaned up"
                )

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
