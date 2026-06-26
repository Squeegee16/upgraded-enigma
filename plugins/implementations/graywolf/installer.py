"""
GrayWolf Dependency Installer
==============================
Handles installation of GrayWolf and its required dependencies
on first run. Checks for Go runtime, GrayWolf binary, and
required Python packages.

Dependencies managed:
    - Go runtime (for building GrayWolf)
    - GrayWolf binary (built from source)
    - requests (Python HTTP library)
    - psutil (Process management)
"""

import os
import sys
import subprocess
import shutil
import platform
import json
from pathlib import Path


class GrayWolfInstaller:
    """
    Manages installation and verification of GrayWolf dependencies.

    This class handles:
    - Checking if GrayWolf is already installed
    - Installing Go runtime if required
    - Cloning and building GrayWolf from source
    - Installing required Python packages
    - Tracking installation state via a marker file
    """

    # Installation state file - tracks whether install has been completed
    INSTALL_MARKER = os.path.join(
        os.path.dirname(__file__),
        '.installed'
    )

    # GrayWolf binary name
    GRAYWOLF_BINARY = 'graywolf'

    # Default install directory for GrayWolf binary
    INSTALL_DIR = os.path.expanduser('~/.local/bin')

    # GrayWolf GitHub repository
    GRAYWOLF_REPO = 'https://github.com/chrissnell/graywolf'

    # Required Python packages for this plugin
    REQUIRED_PACKAGES = [
        'requests',
        'psutil',
    ]

    def __init__(self):
        """Initialize the installer with path configuration."""
        self.plugin_dir = os.path.dirname(__file__)
        self.graywolf_binary_path = shutil.which(self.GRAYWOLF_BINARY) or \
            os.path.join(self.INSTALL_DIR, self.GRAYWOLF_BINARY)

    def is_installed(self):
        """
        Check if GrayWolf has been previously installed.

        Returns:
            bool: True if installation marker exists and binary is found
        """
        marker_exists = os.path.exists(self.INSTALL_MARKER)
        binary_exists = os.path.exists(self.graywolf_binary_path) or \
            shutil.which(self.GRAYWOLF_BINARY) is not None

        return marker_exists and binary_exists

    def check_go_installed(self):
        """
        Check if Go runtime is installed.

        Returns:
            bool: True if Go is available in PATH
        """
        return shutil.which('go') is not None

    def install_go(self):
        """
        Install Go runtime using system package manager.

        Returns:
            bool: True if installation was successful
        """
        print("[GrayWolf] Installing Go runtime...")

        try:
            # Detect Linux distribution package manager
            if shutil.which('apt-get'):
                # Debian/Ubuntu
                subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y', 'golang-go'],
                    check=True,
                    capture_output=True
                )
            elif shutil.which('yum'):
                # RedHat/CentOS
                subprocess.run(
                    ['sudo', 'yum', 'install', '-y', 'golang'],
                    check=True,
                    capture_output=True
                )
            elif shutil.which('dnf'):
                # Fedora
                subprocess.run(
                    ['sudo', 'dnf', 'install', '-y', 'golang'],
                    check=True,
                    capture_output=True
                )
            else:
                print("[GrayWolf] ERROR: Could not detect package manager")
                print("[GrayWolf] Please install Go manually: https://golang.org/dl/")
                return False

            print("[GrayWolf] ✓ Go runtime installed")
            return True

        except subprocess.CalledProcessError as e:
            print(f"[GrayWolf] ERROR: Failed to install Go: {e}")
            return False

    def install_python_packages(self):
        """
        Install required Python packages using pip.

        Returns:
            bool: True if all packages installed successfully
        """
        print("[GrayWolf] Installing required Python packages...")

        try:
            for package in self.REQUIRED_PACKAGES:
                print(f"[GrayWolf] Installing {package}...")
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', package],
                    check=True,
                    capture_output=True
                )
                print(f"[GrayWolf] ✓ {package} installed")

            return True

        except subprocess.CalledProcessError as e:
            print(f"[GrayWolf] ERROR: Failed to install Python packages: {e}")
            return False

    def clone_and_build(self):
        """
        Clone GrayWolf and build both required binaries.

        GrayWolf requires:
            graywolf        - Main server (Go)
            graywolf-modem  - Radio modem (Rust)

        Build strategy:
            1. Try release package download first
               (fastest, no compiler needed)
            2. Fall back to source build with verbose
               error output so failures are diagnosable

        Returns:
            bool: True if both binaries installed
        """
        os.makedirs(self.INSTALL_DIR, exist_ok=True)

        # -------------------------------------------------------
        # Strategy 1: Download from GitHub release
        # Fastest and most reliable — no compiler needed
        # -------------------------------------------------------
        print(
            "\n[GrayWolf] Strategy 1: "
            "Install from GitHub release..."
        )
        if self._install_from_release():
            print(
                "[GrayWolf] ✓ Installed from release"
            )
            return True

        print(
            "[GrayWolf] Release download failed, "
            "trying source build..."
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
                shutil.rmtree(build_dir,
                               ignore_errors=True)
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
            self._log_directory_tree(build_dir,
                                      max_depth=2)

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
                print(
                    "[GrayWolf] ERROR: go.mod not found"
                )
                return False

            # Show go.mod
            try:
                with open(
                    os.path.join(go_mod_dir, 'go.mod'),
                    'r'
                ) as f:
                    gomod = f.read()
                print(
                    f"[GrayWolf] go.mod:\n{gomod[:500]}"
                )
            except Exception:
                pass

            # Check Go version compatibility
            compatible, inst, req = (
                self._check_go_version_compatible(
                    go_mod_dir
                )
            )
            if not compatible:
                print(
                    f"[GrayWolf] ERROR: Go {inst} < "
                    f"required {req}"
                )
                return False

            # Download dependencies
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
            print(
                f"[GrayWolf] Main package: {main_pkg}"
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

            # Build with FULL verbose output
            print(
                f"[GrayWolf] Building: "
                f"go build -v -o {output_path} "
                f"{build_target}"
            )

            env = self._get_go_env()
            try:
                # Use subprocess directly for full output
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

                if result.stdout:
                    pkg_count = len(
                        result.stdout.strip().splitlines()
                    )
                    print(
                        f"[GrayWolf] Compiled "
                        f"{pkg_count} packages"
                    )

                if result.returncode != 0:
                    print(
                        "[GrayWolf] ERROR: "
                        "go build failed"
                    )
                    print(
                        "[GrayWolf] "
                        "---- FULL BUILD ERROR ----"
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
                        "[GrayWolf] "
                        "---- END BUILD ERROR ----"
                    )

                    # Provide targeted guidance
                    combined = (
                        result.stdout + result.stderr
                    )
                    if 'invalid go version' in combined:
                        import re
                        m = re.search(
                            r"invalid go version "
                            r"'([\d.]+)'",
                            combined
                        )
                        if m:
                            needed = m.group(1)
                            print(
                                f"[GrayWolf] HINT: "
                                f"Dockerfile needs "
                                f"Go {needed}:"
                            )
                            print(
                                f"[GrayWolf]   "
                                f"ARG GO_VERSION="
                                f"{needed}"
                            )
                            print(
                                "[GrayWolf]   "
                                "docker compose build "
                                "--no-cache"
                            )
                    elif 'no Go files' in combined:
                        print(
                            "[GrayWolf] HINT: "
                            "No .go files found in "
                            f"'{build_target}'. "
                            "Repo structure:"
                        )
                        self._log_directory_tree(
                            go_mod_dir, max_depth=3
                        )
                    elif 'cannot find module' in combined:
                        print(
                            "[GrayWolf] HINT: "
                            "Module download failed. "
                            "Check internet connectivity."
                        )
                    elif 'permission denied' in combined.lower():
                        print(
                            "[GrayWolf] HINT: "
                            f"GOPATH={self.gopath} "
                            "not writable."
                        )

                    return False

            except subprocess.TimeoutExpired:
                print(
                    "[GrayWolf] ERROR: Build timed out"
                )
                return False

            # Find and install graywolf binary
            gw_ok = self._find_and_install_binary(
                go_mod_dir,
                self.GRAYWOLF_BINARY,
                self.graywolf_binary_path
            )
            if not gw_ok:
                print(
                    "[GrayWolf] ERROR: graywolf binary "
                    "not found after build"
                )
                return False

            print(
                f"[GrayWolf] ✓ graywolf installed: "
                f"{self.graywolf_binary_path}"
            )

            # Build graywolf-modem
            modem_path = os.path.join(
                self.INSTALL_DIR, 'graywolf-modem'
            )
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
            import traceback
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

    def write_install_marker(self):
        """
        Write installation marker file to track completed installation.
        Stores installation details as JSON.
        """
        marker_data = {
            'installed': True,
            'binary_path': self.graywolf_binary_path,
            'install_date': str(Path(self.INSTALL_MARKER).stat().st_mtime
                                if os.path.exists(self.INSTALL_MARKER) else ''),
            'platform': platform.platform(),
            'python_version': sys.version
        }

        with open(self.INSTALL_MARKER, 'w') as f:
            json.dump(marker_data, f, indent=2)

        print(f"[GrayWolf] ✓ Installation marker written")

    def run(self):
        """
        Execute the complete installation process.

        Returns:
            bool: True if installed successfully
        """
        if self.is_installed():
            print("[GrayWolf] ✓ Already installed")
            return True

        existing = shutil.which(self.GRAYWOLF_BINARY)
        if existing:
            print(
                f"[GrayWolf] ✓ Found in PATH: "
                f"{existing}"
            )
            self.write_install_marker('existing')
            return True

        print("[GrayWolf] ================================")
        print("[GrayWolf] Starting first-run installation")
        print("[GrayWolf] ================================")

        # Step 1: Check Go toolchain
        print("\n[GrayWolf] Step 1: Checking Go...")
        go_available, go_info = (self._check_go_available())
        if go_available:
            print(f"[GrayWolf] ✓ Go: {go_info}")
        else:
            print(f"[GrayWolf] WARNING: {go_info}")
            print("[GrayWolf] Will try release download")

        # Step 2: Python packages
        print("\n[GrayWolf] Step 2: Python packages...")
        self.install_python_packages()

        # Step 3: Check git
        print("\n[GrayWolf] Step 3: Checking git...")
        if not shutil.which('git'):
            print("[GrayWolf] WARNING: git not found")
        else:
            print("[GrayWolf] ✓ git available")

        # Step 4: Install (release first, then source)
        print("\n[GrayWolf] Step 4: Installing...")
        success = self.clone_and_build()

        if not success:
            # Diagnostic summary
            print("\n[GrayWolf] ==============================")
            print("[GrayWolf] INSTALLATION FAILED")
            print("[GrayWolf] ==============================")
            print("[GrayWolf] Diagnostics:")
            print(f"[GrayWolf]   Go:      "
                f"{shutil.which('go') or 'NOT FOUND'}"
            )
            print(
                f"[GrayWolf]   git:     "
                f"{shutil.which('git') or 'NOT FOUND'}"
            )
            print(
                f"[GrayWolf]   curl:    "
                f"{shutil.which('curl') or 'NOT FOUND'}"
            )
            print(
                f"[GrayWolf]   arch:    {self._arch}"
            )
            print(
                f"[GrayWolf]   GOPATH:  {self.gopath}"
            )
            print(
                f"[GrayWolf]   Docker:  "
                f"{self.in_docker}"
            )
            print()
            print(
                "[GrayWolf] To diagnose the build error:"
            )
            print(
                "[GrayWolf]   docker compose exec app "
                "bash"
            )
            print(
                "[GrayWolf]   cd /tmp"
            )
            print(
                f"[GrayWolf]   git clone "
                f"{self.GRAYWOLF_REPO} gw"
            )
            print(
                "[GrayWolf]   cd gw"
            )
            print(
                "[GrayWolf]   go build -v ./..."
            )
            print(
                "[GrayWolf] "
                "=============================="
            )
            return False

        version = self.get_version()
        self.write_install_marker('source', version)

        print(
            "\n[GrayWolf] ================================")
        print("[GrayWolf] ✓ Installation complete!")
        
        if version:
            print(f"[GrayWolf]   Version: {version}")
        print("[GrayWolf] ================================\n")
        return True
