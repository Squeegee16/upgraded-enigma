"""
GrayWolf Dependency Installer
==============================
Handles installation of GrayWolf and its required
dependencies on first run.

GrayWolf is a Winlink gateway client written in Go.
Source: https://github.com/chrissnell/graywolf

Installation Process:
    1. Install required Python packages
    2. Verify Go is available (installed in Dockerfile)
    3. Clone GrayWolf repository from GitHub
    4. Build binary with 'go build'
    5. Install binary to ~/.local/bin/graywolf
    6. Write installation marker

Go Build Notes:
    - Go must be installed before this runs
    - go.mod must exist in the repository root
    - Build runs in the repository directory
    - stderr is captured and logged on failure
    - The GOPATH and GOCACHE must be writable by
      the runtime user

Docker Notes:
    - golang-go is installed in the Dockerfile
    - The hamradio user (UID 1000) needs a writable
      GOPATH. Default is ~/go which is /home/hamradio/go
    - GOCACHE defaults to ~/.cache/go-build

Author: Ham Radio App Team
Version: 1.0.0
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import traceback
from pathlib import Path
from datetime import datetime

# Import shared base installer for Docker-aware pip handling
try:
    from plugins.implementations.base_installer import (
        BaseInstaller
    )
except ImportError:
    # Minimal inline fallback
    class BaseInstaller:
        def __init__(self):
            try:
                self.is_root = (os.getuid() == 0)
            except AttributeError:
                self.is_root = False
            self.sudo_available = shutil.which('sudo') is not None
            self._sudo = [] if (
                self.is_root or not self.sudo_available
            ) else ['sudo']
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
                    check=True, capture_output=True,
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
            if extra_data:
                data.update(extra_data)
            try:
                os.makedirs(
                    os.path.dirname(path), exist_ok=True
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


class GrayWolfInstaller(BaseInstaller):
    """
    Manages GrayWolf installation.

    Extends BaseInstaller to handle Go-based build
    process with proper environment setup and
    verbose error reporting.
    """

    # Installation state marker
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # GrayWolf GitHub repository
    GRAYWOLF_REPO = 'https://github.com/chrissnell/graywolf'

    # Binary name
    GRAYWOLF_BINARY = 'graywolf'

    # Install directory (in user home for non-root)
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # Required Python packages
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    def __init__(self):
        """
        Initialise installer with Go environment setup.
        """
        super().__init__()

        # Binary path (in INSTALL_DIR)
        self.graywolf_binary_path = os.path.join(
            self.INSTALL_DIR, self.GRAYWOLF_BINARY
        )

        # Go environment paths
        # Default GOPATH is ~/go
        # Default GOCACHE is ~/.cache/go-build
        self.gopath = os.environ.get(
            'GOPATH',
            os.path.expanduser('~/go')
        )
        self.gocache = os.environ.get(
            'GOCACHE',
            os.path.expanduser('~/.cache/go-build')
        )

        print(
            f"[GrayWolf] Installer init | "
            f"Docker: {self.in_docker} | "
            f"Go: {shutil.which('go') or 'not found'} | "
            f"GOPATH: {self.gopath}"
        )

    def _get_go_env(self):
        """
        Build environment variables for Go build commands.

        Ensures GOPATH and GOCACHE are set to writable
        directories for the current user.

        Returns:
            dict: Environment variables for subprocess
        """
        env = os.environ.copy()

        # Ensure GOPATH is set and writable
        env['GOPATH'] = self.gopath
        os.makedirs(self.gopath, exist_ok=True)

        # Ensure GOCACHE is set and writable
        env['GOCACHE'] = self.gocache
        os.makedirs(self.gocache, exist_ok=True)

        # Ensure HOME is set (needed by Go toolchain)
        if 'HOME' not in env:
            env['HOME'] = os.path.expanduser('~')

        # Add ~/.local/bin to PATH so installed binary
        # is immediately findable
        local_bin = os.path.expanduser('~/.local/bin')
        path_parts = env.get('PATH', '').split(':')
        if local_bin not in path_parts:
            env['PATH'] = f"{local_bin}:{env.get('PATH', '')}"

        return env

    def _run_go_command(self, cmd, cwd=None, timeout=300):
        """
        Run a Go command and capture all output.

        Unlike _run_command in the base class, this method
        intentionally captures stderr separately so that
        Go compiler errors can be displayed clearly.

        Args:
            cmd: Command list to execute
            cwd: Working directory for the command
            timeout: Maximum seconds to wait

        Returns:
            tuple: (success, stdout, stderr)
        """
        env = self._get_go_env()

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,  # Separate stdout/stderr
                timeout=timeout,
                text=True
            )

            if result.returncode == 0:
                return True, result.stdout, result.stderr
            else:
                return False, result.stdout, result.stderr

        except FileNotFoundError as e:
            return False, '', f"Command not found: {cmd[0]}: {e}"
        except subprocess.TimeoutExpired:
            return False, '', f"Timed out after {timeout}s"
        except Exception as e:
            return False, '', str(e)

    def is_installed(self):
        """
        Check if GrayWolf binary is installed.

        Returns:
            bool: True if marker exists and binary found
        """
        if not os.path.exists(self.INSTALL_MARKER):
            return False

        # Check binary in INSTALL_DIR
        if os.path.exists(self.graywolf_binary_path):
            return True

        # Check if in PATH
        return shutil.which(self.GRAYWOLF_BINARY) is not None

    def _check_go_available(self):
        """
        Verify Go toolchain is installed and working.

        Returns:
            tuple: (available, version_string)
        """
        go_binary = shutil.which('go')
        if not go_binary:
            return False, "go binary not found in PATH"

        ok, stdout, stderr = self._run_go_command(
            ['go', 'version'],
            timeout=15
        )

        if ok and stdout:
            version = stdout.strip()
            print(f"[GrayWolf] Go version: {version}")
            return True, version

        return False, stderr or "go version failed"

    def install_python_packages(self):
        """
        Install required Python packages.

        Returns:
            bool: True if all packages available
        """
        print("[GrayWolf] Installing required Python packages...")
        available, failed = super().install_python_packages(
            self.REQUIRED_PACKAGES
        )

        if failed and not self.in_docker:
            print(
                f"[GrayWolf] WARNING: Failed packages: {failed}"
            )
        return len(failed) == 0

    def clone_and_build(self):
        """
        Clone GrayWolf from GitHub and build the binary.

        Provides detailed error output when the build
        fails so the root cause is visible in logs.

        Build steps:
            1. Create build directory
            2. Clone repository
            3. Verify go.mod exists
            4. Run 'go mod download' for dependencies
            5. Run 'go build' to compile binary
            6. Copy binary to INSTALL_DIR

        Returns:
            bool: True if build and install successful
        """
        build_dir = os.path.join(
            os.path.expanduser('~'),
            '.graywolf_build'
        )

        try:
            # Clean previous failed builds
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

            os.makedirs(build_dir, exist_ok=True)

            # -------------------------------------------------------
            # Step 1: Clone repository
            # -------------------------------------------------------
            print("[GrayWolf] Cloning repository...")
            ok, stdout, stderr = self._run_go_command(
                ['git', 'clone',
                 '--depth', '1',
                 self.GRAYWOLF_REPO,
                 build_dir],
                timeout=120
            )

            if not ok:
                print(f"[GrayWolf] Clone failed: {stderr}")
                return False

            print("[GrayWolf] ✓ Repository cloned")

            # -------------------------------------------------------
            # Step 2: Verify repository structure
            # -------------------------------------------------------
            # Find the directory containing go.mod
            # Some repos have it in the root, others in a subdir
            go_mod_dir = None

            for root, dirs, files in os.walk(build_dir):
                if 'go.mod' in files:
                    go_mod_dir = root
                    print(f"[GrayWolf] go.mod found: {root}")
                    break

            if not go_mod_dir:
                print(
                    "[GrayWolf] ERROR: go.mod not found in "
                    "cloned repository"
                )
                print(
                    "[GrayWolf] Repository contents:"
                )
                for item in os.listdir(build_dir):
                    print(f"  {item}")
                return False

            # -------------------------------------------------------
            # Step 3: Download Go module dependencies
            # -------------------------------------------------------
            print("[GrayWolf] Downloading Go dependencies...")
            ok, stdout, stderr = self._run_go_command(
                ['go', 'mod', 'download'],
                cwd=go_mod_dir,
                timeout=180
            )

            if not ok:
                print(
                    f"[GrayWolf] WARNING: go mod download "
                    f"failed: {stderr}"
                )
                # Continue — may still build with cached modules

            # -------------------------------------------------------
            # Step 4: Build the binary
            # -------------------------------------------------------
            print(
                f"[GrayWolf] Building binary in {go_mod_dir}..."
            )
            build_output_path = os.path.join(
                go_mod_dir, self.GRAYWOLF_BINARY
            )

            ok, stdout, stderr = self._run_go_command(
                [
                    'go', 'build',
                    '-v',  # Verbose output for debugging
                    '-o', build_output_path,
                    '.'   # Build from current directory
                ],
                cwd=go_mod_dir,
                timeout=300
            )

            if not ok:
                # Log full build error for diagnosis
                print(
                    "[GrayWolf] ERROR: go build failed"
                )
                if stdout:
                    print(
                        f"[GrayWolf] stdout:\n{stdout[:500]}"
                    )
                if stderr:
                    print(
                        f"[GrayWolf] stderr:\n{stderr[:1000]}"
                    )

                # Try to provide helpful guidance
                if 'cannot find package' in stderr or \
                        'no required module' in stderr:
                    print(
                        "[GrayWolf] Missing Go modules. "
                        "Try: go mod tidy in the repository."
                    )
                elif 'undefined:' in stderr:
                    print(
                        "[GrayWolf] Compilation error. "
                        "The repository may need a newer "
                        "version of Go."
                    )
                elif 'permission denied' in stderr.lower():
                    print(
                        "[GrayWolf] Permission denied. "
                        f"Check GOPATH ({self.gopath}) and "
                        f"GOCACHE ({self.gocache}) are "
                        "writable."
                    )

                return False

            if stdout:
                # Verbose build output (list of compiled packages)
                print(
                    f"[GrayWolf] Build output: "
                    f"{len(stdout.splitlines())} packages compiled"
                )

            # -------------------------------------------------------
            # Step 5: Install binary to INSTALL_DIR
            # -------------------------------------------------------
            os.makedirs(self.INSTALL_DIR, exist_ok=True)

            if not os.path.exists(build_output_path):
                print(
                    f"[GrayWolf] ERROR: Built binary not found "
                    f"at {build_output_path}"
                )
                return False

            shutil.copy2(
                build_output_path,
                self.graywolf_binary_path
            )
            os.chmod(self.graywolf_binary_path, 0o755)

            print(
                f"[GrayWolf] ✓ Binary installed: "
                f"{self.graywolf_binary_path}"
            )

            # Verify the binary runs
            ok, stdout, stderr = self._run_go_command(
                [self.graywolf_binary_path, '--version'],
                timeout=10
            )
            if ok or stdout or stderr:
                print(
                    f"[GrayWolf] ✓ Binary verified: "
                    f"{(stdout or stderr or 'ok').strip()[:50]}"
                )

            return True

        except Exception as e:
            print(f"[GrayWolf] Build exception: {e}")
            traceback.print_exc()
            return False

        finally:
            # Always clean up build directory
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)
                print("[GrayWolf] Build directory cleaned up")

    def write_install_marker(self, method, version=None):
        """
        Write installation marker.

        Args:
            method: Installation method used
            version: Binary version string if available
        """
        self.write_marker(
            self.INSTALL_MARKER,
            extra_data={
                'method': method,
                'version': version,
                'binary_path': self.graywolf_binary_path,
                'platform': platform.platform(),
                'go_version': (
                    shutil.which('go') and
                    subprocess.run(
                        ['go', 'version'],
                        capture_output=True,
                        text=True
                    ).stdout.strip()
                )
            }
        )

    def get_install_info(self):
        """Read installation marker."""
        return self.read_marker(self.INSTALL_MARKER)

    def get_version(self):
        """
        Get GrayWolf binary version.

        Returns:
            str: Version string or None
        """
        binary = (
            shutil.which(self.GRAYWOLF_BINARY) or
            self.graywolf_binary_path
        )
        if not binary or not os.path.exists(binary):
            return None

        try:
            for flag in ['--version', '-v', 'version']:
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
                    return output[:50]
        except Exception:
            pass

        return 'installed'

    def run(self):
        """
        Execute the complete installation process.

        Steps:
            1. Check if already installed
            2. Verify Go toolchain is available
            3. Install Python packages
            4. Clone and build GrayWolf
            5. Write installation marker

        Returns:
            bool: True if successful or already installed
        """
        # Already installed
        if self.is_installed():
            print("[GrayWolf] ✓ Already installed")
            return True

        # Binary in PATH but no marker
        existing = shutil.which(self.GRAYWOLF_BINARY)
        if existing:
            print(f"[GrayWolf] ✓ Found in PATH: {existing}")
            self.write_install_marker('existing')
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
                "[GrayWolf] Go is installed in the Dockerfile."
            )
            print(
                "[GrayWolf] Rebuild the Docker image: "
                "docker compose build --no-cache"
            )
            return False

        print(f"[GrayWolf] ✓ Go available: {go_info}")

        # -------------------------------------------------------
        # Step 2: Python packages
        # -------------------------------------------------------
        print("\n[GrayWolf] Step 2: Python packages...")
        self.install_python_packages()
        # Non-fatal

        # -------------------------------------------------------
        # Step 3: Check git
        # -------------------------------------------------------
        print("\n[GrayWolf] Step 3: Checking git...")
        if not shutil.which('git'):
            print(
                "[GrayWolf] ERROR: git is required but "
                "not found. Add to Dockerfile: "
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
            print("[GrayWolf] ERROR: Build failed")
            print(
                "[GrayWolf] Check the error messages above"
            )
            return False

        # -------------------------------------------------------
        # Step 5: Write marker
        # -------------------------------------------------------
        version = self.get_version()
        self.write_install_marker('source', version)

        print("\n[GrayWolf] ================================")
        print("[GrayWolf] ✓ Installation complete!")
        if version:
            print(f"[GrayWolf]   Version: {version}")
        print("[GrayWolf] ================================\n")

        return True
