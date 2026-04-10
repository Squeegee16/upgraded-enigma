"""
Auto-discovers plugins from plugins folder at runtime.
"""

import importlib
import os

def load_plugins(app):
    plugins = []
    for folder in os.listdir("plugins"):
        if folder == "__init__.py":
            continue
        try:
            module = importlib.import_module(f"plugins.{folder}.plugin")
            plugin = module.Plugin()
            app.register_blueprint(plugin.get_blueprint())
            plugins.append(plugin)
        except Exception as e:
            print("Plugin load failed:", folder, e)
    return plugins