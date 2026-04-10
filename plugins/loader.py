"""
Plugin Loader
=============
Discovers and loads plugins from the plugins directory.
"""

import os
import importlib
import inspect
from plugins.base import BasePlugin

class PluginLoader:
    """
    Plugin discovery and loading system.
    
    Scans the plugins directory for Python modules and loads
    classes that inherit from BasePlugin.
    """
    
    def __init__(self, app, plugins_dir, devices):
        """
        Initialize plugin loader.
        
        Args:
            app: Flask application instance
            plugins_dir: Path to plugins directory
            devices: Dictionary of device interfaces
        """
        self.app = app
        self.plugins_dir = plugins_dir
        self.devices = devices
        self.plugins = {}
    
    def discover_plugins(self):
        """
        Discover all plugins in the plugins directory.
        
        Returns:
            list: List of discovered plugin classes
        """
        discovered = []
        
        if not os.path.exists(self.plugins_dir):
            print(f"Plugins directory not found: {self.plugins_dir}")
            return discovered
        
        # Get all Python files in plugins directory
        for filename in os.listdir(self.plugins_dir):
            if filename.endswith('.py') and not filename.startswith('_'):
                module_name = filename[:-3]
                
                try:
                    # Import the module
                    module_path = f'plugins.implementations.{module_name}'
                    module = importlib.import_module(module_path)
                    
                    # Find all classes that inherit from BasePlugin
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BasePlugin) and obj != BasePlugin:
                            discovered.append(obj)
                            print(f"Discovered plugin: {name} from {module_name}")
                
                except Exception as e:
                    print(f"Error loading plugin {module_name}: {e}")
        
        return discovered
    
    def load_plugin(self, plugin_class):
        """
        Load and initialize a plugin.
        
        Args:
            plugin_class: Plugin class to instantiate
            
        Returns:
            BasePlugin: Initialized plugin instance or None
        """
        try:
            # Instantiate plugin
            plugin = plugin_class(app=self.app, devices=self.devices)
            
            # Initialize plugin
            if plugin.initialize():
                # Register blueprint if available
                blueprint = plugin.get_blueprint()
                if blueprint:
                    self.app.register_blueprint(blueprint)
                
                plugin.enable()
                self.plugins[plugin.name] = plugin
                print(f"Loaded plugin: {plugin.name} v{plugin.version}")
                return plugin
            else:
                print(f"Failed to initialize plugin: {plugin.name}")
                return None
        
        except Exception as e:
            print(f"Error loading plugin {plugin_class.__name__}: {e}")
            return None
    
    def load_all_plugins(self):
        """
        Discover and load all available plugins.
        
        Returns:
            dict: Dictionary of loaded plugins
        """
        plugin_classes = self.discover_plugins()
        
        for plugin_class in plugin_classes:
            self.load_plugin(plugin_class)
        
        print(f"Loaded {len(self.plugins)} plugins")
        return self.plugins
    
    def get_plugin(self, name):
        """
        Get a loaded plugin by name.
        
        Args:
            name: Plugin name
            
        Returns:
            BasePlugin: Plugin instance or None
        """
        return self.plugins.get(name)
    
    def get_all_plugins(self):
        """
        Get all loaded plugins.
        
        Returns:
            dict: Dictionary of all plugins
        """
        return self.plugins
    
    def unload_plugin(self, name):
        """
        Unload a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            bool: True if unloaded successfully
        """
        if name in self.plugins:
            plugin = self.plugins[name]
            plugin.shutdown()
            plugin.disable()
            del self.plugins[name]
            print(f"Unloaded plugin: {name}")
            return True
        return False
    
    def shutdown_all(self):
        """Shutdown all plugins."""
        for name, plugin in self.plugins.items():
            try:
                plugin.shutdown()
                print(f"Shutdown plugin: {name}")
            except Exception as e:
                print(f"Error shutting down plugin {name}: {e}")