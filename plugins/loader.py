"""
Plugin Loader
=============
Discovers and loads plugins from the plugins directory.

Excludes utility/helper files that are not plugins:
    - base_installer.py
    - Any file not containing a BasePlugin subclass
"""

import os
import sys
import importlib
import importlib.util
import inspect
import traceback
from plugins.base import BasePlugin


class PluginLoader:
    """
    Plugin discovery and loading system.

    Scans plugins/implementations/ for packages and
    single files containing BasePlugin subclasses.
    Explicitly excludes helper modules.
    """

    # Files and directories to skip during discovery.
    # Add any helper modules here to prevent them from
    # being treated as plugins.
    EXCLUDED_FILES = {
        'base_installer.py',
        'base_installer',
        '__init__.py',
        '__pycache__',
    }

    def __init__(self, app, plugins_dir, devices):
        """
        Initialise plugin loader.

        Args:
            app: Flask application instance
            plugins_dir: Path to plugins/implementations/
            devices: Dict of device interface instances
        """
        self.app = app
        self.plugins_dir = plugins_dir
        self.devices = devices
        self.plugins = {}
        self._registered_blueprints = set()

    def discover_plugins(self):
        """
        Scan plugins directory for plugin classes.

        Returns:
            list: (plugin_class, module_name) tuples
        """
        discovered = []

        if not os.path.exists(self.plugins_dir):
            print(
                f"[PluginLoader] Directory not found: "
                f"{self.plugins_dir}"
            )
            os.makedirs(self.plugins_dir, exist_ok=True)
            return discovered

        print(f"\n[PluginLoader] Scanning: {self.plugins_dir}")

        # Ensure correct paths on sys.path
        plugins_parent = os.path.dirname(self.plugins_dir)
        if plugins_parent not in sys.path:
            sys.path.insert(0, plugins_parent)

        impl_parent = os.path.dirname(
            os.path.dirname(self.plugins_dir)
        )
        if impl_parent not in sys.path:
            sys.path.insert(0, impl_parent)

        try:
            entries = sorted(os.listdir(self.plugins_dir))
        except OSError as e:
            print(f"[PluginLoader] Cannot list directory: {e}")
            return discovered

        for entry in entries:
            # Skip hidden files, __pycache__, and excluded files
            if (entry.startswith('_') or
                    entry.startswith('.') or
                    entry in self.EXCLUDED_FILES):
                if entry not in ('__init__.py', '__pycache__'):
                    print(
                        f"[PluginLoader] Skipping "
                        f"excluded: {entry}"
                    )
                continue

            entry_path = os.path.join(self.plugins_dir, entry)

            # Package plugin: directory with __init__.py
            if os.path.isdir(entry_path):
                init_file = os.path.join(
                    entry_path, '__init__.py'
                )
                if os.path.exists(init_file):
                    print(
                        f"[PluginLoader] Found package "
                        f"plugin: {entry}"
                    )
                    result = self._discover_package_plugin(
                        entry, entry_path
                    )
                    if result:
                        discovered.append(result)

            # Single-file plugin: .py file
            elif entry.endswith('.py'):
                module_name = entry[:-3]

                # Double-check against exclusion list
                if module_name in self.EXCLUDED_FILES:
                    print(
                        f"[PluginLoader] Skipping "
                        f"excluded file: {entry}"
                    )
                    continue

                print(
                    f"[PluginLoader] Found file "
                    f"plugin: {module_name}"
                )
                result = self._discover_file_plugin(
                    module_name, entry_path
                )
                if result:
                    discovered.append(result)

        print(
            f"[PluginLoader] Discovered "
            f"{len(discovered)} plugin(s)"
        )
        return discovered

    def _discover_package_plugin(self, package_name, package_path):
        """
        Discover a package-style plugin.

        Args:
            package_name: Package directory name
            package_path: Full path to package directory

        Returns:
            tuple: (plugin_class, module_name) or None
        """
        try:
            module_path = (
                f"plugins.implementations.{package_name}"
            )

            if module_path in sys.modules:
                module = sys.modules[module_path]
                importlib.reload(module)
            else:
                module = importlib.import_module(module_path)

            plugin_class = self._find_plugin_class(module)

            if plugin_class:
                print(
                    f"[PluginLoader] ✓ Found class: "
                    f"{plugin_class.__name__} in {package_name}"
                )
                return (plugin_class, package_name)

            # Try plugin.py directly
            plugin_module_path = (
                f"plugins.implementations."
                f"{package_name}.plugin"
            )
            try:
                plugin_module = importlib.import_module(
                    plugin_module_path
                )
                plugin_class = self._find_plugin_class(
                    plugin_module
                )
                if plugin_class:
                    print(
                        f"[PluginLoader] ✓ Found class: "
                        f"{plugin_class.__name__} "
                        f"in {package_name}.plugin"
                    )
                    return (plugin_class, package_name)
            except ImportError:
                pass

            print(
                f"[PluginLoader] WARNING: No BasePlugin "
                f"subclass in {package_name}"
            )
            return None

        except ImportError as e:
            print(
                f"[PluginLoader] Import error for "
                f"{package_name}: {e}"
            )
            traceback.print_exc()
            return None
        except Exception as e:
            print(
                f"[PluginLoader] Error loading "
                f"{package_name}: {e}"
            )
            traceback.print_exc()
            return None

    def _discover_file_plugin(self, module_name, file_path):
        """
        Discover a single-file plugin.

        Args:
            module_name: Module name (without .py)
            file_path: Full path to .py file

        Returns:
            tuple: (plugin_class, module_name) or None
        """
        try:
            module_path = (
                f"plugins.implementations.{module_name}"
            )

            if module_path in sys.modules:
                module = sys.modules[module_path]
            else:
                spec = importlib.util.spec_from_file_location(
                    module_path, file_path
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_path] = module
                spec.loader.exec_module(module)

            plugin_class = self._find_plugin_class(module)

            if plugin_class:
                print(
                    f"[PluginLoader] ✓ Found class: "
                    f"{plugin_class.__name__} "
                    f"in {module_name}"
                )
                return (plugin_class, module_name)

            print(
                f"[PluginLoader] WARNING: No BasePlugin "
                f"subclass in {module_name}"
            )
            return None

        except Exception as e:
            print(
                f"[PluginLoader] Error loading "
                f"{module_name}: {e}"
            )
            traceback.print_exc()
            return None

    def _find_plugin_class(self, module):
        """
        Find a BasePlugin subclass in a module.

        Args:
            module: Imported Python module

        Returns:
            class: Plugin class or None
        """
        for name, obj in inspect.getmembers(
            module, inspect.isclass
        ):
            try:
                if (issubclass(obj, BasePlugin) and
                        obj is not BasePlugin and
                        obj.__name__ != 'BasePlugin'):
                    return obj
            except TypeError:
                continue
        return None

    def load_plugin(self, plugin_class, module_name):
        """
        Instantiate and register a plugin.

        Args:
            plugin_class: Plugin class to instantiate
            module_name: Source module name

        Returns:
            BasePlugin: Plugin instance or None
        """
        try:
            plugin = plugin_class(
                app=self.app,
                devices=self.devices
            )

            print(
                f"[PluginLoader] Loading: "
                f"{plugin.name} v{plugin.version}"
            )

            # Initialise plugin (non-fatal if fails)
            try:
                plugin.initialize()
            except Exception as e:
                print(
                    f"[PluginLoader] Init error for "
                    f"{plugin.name}: {e}"
                )
                traceback.print_exc()

            # Register Flask blueprint
            try:
                blueprint = plugin.get_blueprint()
                if blueprint is not None:
                    bp_name = blueprint.name
                    if bp_name not in \
                            self._registered_blueprints:
                        self.app.register_blueprint(blueprint)
                        self._registered_blueprints.add(bp_name)
                        print(
                            f"[PluginLoader] ✓ Blueprint "
                            f"registered: {bp_name} "
                            f"({blueprint.url_prefix})"
                        )
                    else:
                        print(
                            f"[PluginLoader] Blueprint "
                            f"{bp_name} already registered"
                        )
            except Exception as e:
                print(
                    f"[PluginLoader] Blueprint error for "
                    f"{plugin.name}: {e}"
                )
                traceback.print_exc()

            plugin.enable()
            self.plugins[plugin.name] = plugin

            print(
                f"[PluginLoader] ✓ Plugin loaded: "
                f"{plugin.name}"
            )
            return plugin

        except Exception as e:
            print(
                f"[PluginLoader] Failed to load "
                f"{plugin_class.__name__}: {e}"
            )
            traceback.print_exc()
            return None

    def load_all_plugins(self):
        """
        Discover and load all available plugins.

        Returns:
            dict: Loaded plugins keyed by name
        """
        print("[PluginLoader] ================================")
        print("[PluginLoader] Loading all plugins...")
        print("[PluginLoader] ================================\n")

        plugin_classes = self.discover_plugins()

        if not plugin_classes:
            print("[PluginLoader] No plugins found")
            return self.plugins

        for plugin_class, module_name in plugin_classes:
            self.load_plugin(plugin_class, module_name)

        print(
            f"\n[PluginLoader] ================================"
        )
        print(
            f"[PluginLoader] Loaded "
            f"{len(self.plugins)} plugin(s): "
            f"{list(self.plugins.keys())}"
        )
        print(
            "[PluginLoader] ================================\n"
        )
        return self.plugins

    def get_plugin(self, name):
        """Get a loaded plugin by name."""
        return self.plugins.get(name)

    def get_all_plugins(self):
        """Get all loaded plugins as a dict."""
        return dict(self.plugins)

    def get_plugin_list(self):
        """
        Get structured plugin info list for the UI.

        Returns:
            list: Plugin info dicts for dashboard display
        """
        plugin_list = []

        for name, plugin in self.plugins.items():
            try:
                plugin_list.append({
                    'name': plugin.name,
                    'description': plugin.description,
                    'version': plugin.version,
                    'author': plugin.author,
                    'enabled': plugin.enabled,
                    'url': getattr(plugin, 'url', ''),
                    'endpoint': f"{plugin.name}.index",
                })
            except Exception as e:
                print(
                    f"[PluginLoader] Info error for "
                    f"{name}: {e}"
                )

        return plugin_list

    def shutdown_all(self):
        """Gracefully shutdown all loaded plugins."""
        print("[PluginLoader] Shutting down all plugins...")
        for name, plugin in list(self.plugins.items()):
            try:
                plugin.shutdown()
                print(f"[PluginLoader] Shutdown: {name}")
            except Exception as e:
                print(
                    f"[PluginLoader] Shutdown error "
                    f"{name}: {e}"
                )
