"""
Plugin Loader
=============
Discovers and loads plugins from the plugins directory.

Supports both:
    - Single file plugins (plugin_name.py)
    - Package plugins (plugin_name/__init__.py + plugin.py)

Author: Ham Radio App Team
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

    Scans the plugins directory for Python modules and
    packages that contain classes inheriting from BasePlugin.
    Registers each plugin's Flask Blueprint automatically.
    """

    def __init__(self, app, plugins_dir, devices):
        """
        Initialize plugin loader.

        Args:
            app: Flask application instance
            plugins_dir: Path to plugins/implementations directory
            devices: Dictionary of device interfaces
        """
        self.app = app
        self.plugins_dir = plugins_dir
        self.devices = devices

        # Loaded plugin instances keyed by plugin name
        self.plugins = {}

        # Track registered blueprint URL prefixes to avoid conflicts
        self._registered_blueprints = set()

    def discover_plugins(self):
        """
        Discover all plugins in the plugins directory.

        Scans for:
        1. Package plugins: subdirectory with __init__.py
           that exports a BasePlugin subclass
        2. Single file plugins: .py files with BasePlugin subclass

        Returns:
            list: List of (plugin_class, module_name) tuples
        """
        discovered = []

        if not os.path.exists(self.plugins_dir):
            print(
                f"[PluginLoader] Plugins directory not found: "
                f"{self.plugins_dir}"
            )
            os.makedirs(self.plugins_dir, exist_ok=True)
            return discovered

        print(
            f"\n[PluginLoader] Scanning: {self.plugins_dir}"
        )

        # Ensure plugins directory is on Python path
        plugins_parent = os.path.dirname(self.plugins_dir)
        if plugins_parent not in sys.path:
            sys.path.insert(0, plugins_parent)

        # Also ensure the implementations dir parent is on path
        impl_parent = os.path.dirname(
            os.path.dirname(self.plugins_dir)
        )
        if impl_parent not in sys.path:
            sys.path.insert(0, impl_parent)

        # Get all entries in plugins directory
        try:
            entries = sorted(os.listdir(self.plugins_dir))
        except OSError as e:
            print(f"[PluginLoader] Cannot list directory: {e}")
            return discovered

        for entry in entries:
            # Skip hidden files/dirs and __pycache__
            if entry.startswith('_') or entry.startswith('.'):
                continue

            entry_path = os.path.join(self.plugins_dir, entry)

            # Check for package plugin (directory with __init__.py)
            if os.path.isdir(entry_path):
                init_file = os.path.join(
                    entry_path, '__init__.py'
                )
                if os.path.exists(init_file):
                    print(
                        f"[PluginLoader] Found package plugin: "
                        f"{entry}"
                    )
                    result = self._discover_package_plugin(
                        entry, entry_path
                    )
                    if result:
                        discovered.append(result)

            # Check for single-file plugin
            elif (entry.endswith('.py') and
                  entry not in ('__init__.py',)):
                module_name = entry[:-3]
                print(
                    f"[PluginLoader] Found file plugin: "
                    f"{module_name}"
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

        Imports the package and finds the BasePlugin subclass.

        Args:
            package_name: Package directory name
            package_path: Full path to package directory

        Returns:
            tuple: (plugin_class, module_name) or None
        """
        try:
            # Build the full module path
            # e.g., plugins.implementations.fldigi
            module_path = (
                f"plugins.implementations.{package_name}"
            )

            # Import the package
            if module_path in sys.modules:
                module = sys.modules[module_path]
                # Force reload to pick up any changes
                importlib.reload(module)
            else:
                module = importlib.import_module(module_path)

            # Find BasePlugin subclass in the module
            plugin_class = self._find_plugin_class(
                module, package_name
            )

            if plugin_class:
                print(
                    f"[PluginLoader] ✓ Found class: "
                    f"{plugin_class.__name__} in {package_name}"
                )
                return (plugin_class, package_name)
            else:
                # Try importing from plugin.py directly
                plugin_module_path = (
                    f"plugins.implementations."
                    f"{package_name}.plugin"
                )
                try:
                    plugin_module = importlib.import_module(
                        plugin_module_path
                    )
                    plugin_class = self._find_plugin_class(
                        plugin_module, package_name
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
                    f"subclass found in {package_name}"
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
            module_name: Module name (filename without .py)
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

            plugin_class = self._find_plugin_class(
                module, module_name
            )

            if plugin_class:
                print(
                    f"[PluginLoader] ✓ Found class: "
                    f"{plugin_class.__name__} in {module_name}"
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

    def _find_plugin_class(self, module, module_name):
        """
        Find BasePlugin subclass in a module.

        Searches module members for classes that:
        1. Are a subclass of BasePlugin
        2. Are not BasePlugin itself
        3. Are defined in or imported into the module

        Args:
            module: Imported Python module
            module_name: Module name for logging

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
        Instantiate and initialize a plugin.

        Args:
            plugin_class: Plugin class to instantiate
            module_name: Source module name

        Returns:
            BasePlugin: Initialized plugin instance or None
        """
        plugin_instance_name = None

        try:
            # Create plugin instance
            plugin = plugin_class(
                app=self.app,
                devices=self.devices
            )

            plugin_instance_name = plugin.name

            print(
                f"[PluginLoader] Loading: {plugin.name} "
                f"v{plugin.version}"
            )

            # Initialize plugin resources
            try:
                init_result = plugin.initialize()
                if init_result is False:
                    print(
                        f"[PluginLoader] Plugin {plugin.name} "
                        f"initialization returned False"
                    )
                    # Still continue - allow UI to load
            except Exception as e:
                print(
                    f"[PluginLoader] Init error for "
                    f"{plugin.name}: {e}"
                )
                traceback.print_exc()
                # Continue despite init error

            # Get and register Flask blueprint
            try:
                blueprint = plugin.get_blueprint()

                if blueprint is not None:
                    # Check for duplicate blueprint names
                    bp_name = blueprint.name
                    bp_url = blueprint.url_prefix

                    if bp_name not in self._registered_blueprints:
                        self.app.register_blueprint(blueprint)
                        self._registered_blueprints.add(bp_name)
                        print(
                            f"[PluginLoader] ✓ Blueprint "
                            f"registered: {bp_name} "
                            f"({bp_url})"
                        )
                    else:
                        print(
                            f"[PluginLoader] WARNING: Blueprint "
                            f"{bp_name} already registered, "
                            f"skipping"
                        )

            except Exception as e:
                print(
                    f"[PluginLoader] Blueprint error for "
                    f"{plugin.name}: {e}"
                )
                traceback.print_exc()

            # Enable and store plugin
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
            dict: Dictionary of loaded plugin instances
                  keyed by plugin name
        """
        print("\n[PluginLoader] ================================")
        print("[PluginLoader] Loading all plugins...")
        print("[PluginLoader] ================================")

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
            f"[PluginLoader] Loaded {len(self.plugins)} "
            f"plugin(s): "
            f"{list(self.plugins.keys())}"
        )
        print(
            f"[PluginLoader] ================================\n"
        )

        return self.plugins

    def get_plugin(self, name):
        """
        Get a loaded plugin by name.

        Args:
            name: Plugin name string

        Returns:
            BasePlugin: Plugin instance or None
        """
        return self.plugins.get(name)

    def get_all_plugins(self):
        """
        Get all loaded plugin instances.

        Returns:
            dict: All plugins keyed by name
        """
        return dict(self.plugins)

    def get_plugin_list(self):
        """
        Get a list of plugin info dictionaries for the UI.

        Returns:
            list: Plugin info dicts with name, description,
                  version, enabled, url_endpoint
        """
        plugin_list = []

        for name, plugin in self.plugins.items():
            # Build the index route URL endpoint name
            # Blueprint name is plugin.name, route is 'index'
            try:
                # Check if blueprint has an index route
                endpoint = f"{plugin.name}.index"

                plugin_list.append({
                    'name': plugin.name,
                    'description': plugin.description,
                    'version': plugin.version,
                    'author': plugin.author,
                    'enabled': plugin.enabled,
                    'url': getattr(plugin, 'url', ''),
                    'endpoint': endpoint,
                })
            except Exception as e:
                print(
                    f"[PluginLoader] Error building info "
                    f"for {name}: {e}"
                )

        return plugin_list

    def reload_plugin(self, name):
        """
        Reload a specific plugin.

        Shuts down the existing instance and loads a fresh one.

        Args:
            name: Plugin name to reload

        Returns:
            bool: True if reloaded successfully
        """
        plugin = self.plugins.get(name)
        if not plugin:
            return False

        print(f"[PluginLoader] Reloading: {name}")

        # Shutdown existing instance
        try:
            plugin.shutdown()
        except Exception as e:
            print(f"[PluginLoader] Shutdown error: {e}")

        # Remove from loaded plugins
        del self.plugins[name]

        # Re-discover and reload
        plugin_classes = self.discover_plugins()
        for plugin_class, module_name in plugin_classes:
            if plugin_class.name == name or \
                    module_name == name.lower():
                self.load_plugin(plugin_class, module_name)
                return True

        return False

    def unload_plugin(self, name):
        """
        Unload a specific plugin gracefully.

        Args:
            name: Plugin name to unload

        Returns:
            bool: True if unloaded successfully
        """
        plugin = self.plugins.get(name)
        if not plugin:
            return False

        try:
            plugin.shutdown()
            plugin.disable()
            del self.plugins[name]
            print(f"[PluginLoader] Unloaded: {name}")
            return True
        except Exception as e:
            print(
                f"[PluginLoader] Error unloading {name}: {e}"
            )
            return False

    def shutdown_all(self):
        """Gracefully shutdown all loaded plugins."""
        print("[PluginLoader] Shutting down all plugins...")

        for name, plugin in list(self.plugins.items()):
            try:
                plugin.shutdown()
                print(f"[PluginLoader] Shutdown: {name}")
            except Exception as e:
                print(
                    f"[PluginLoader] Error shutting down "
                    f"{name}: {e}"
                )
