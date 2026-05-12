#!/usr/bin/env python3
"""
Plugin Discovery Diagnostic Script
=====================================
Run this to diagnose plugin loading issues.
Usage: python check_plugins.py
"""

import os
import sys
import importlib
import inspect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugins.base import BasePlugin


def check_plugins(plugins_dir='plugins/implementations'):
    """
    Scan and verify plugin directory.

    Args:
        plugins_dir: Path to implementations directory
    """
    print(f"\nPlugin Diagnostic Report")
    print(f"=" * 50)
    print(f"Scanning: {os.path.abspath(plugins_dir)}\n")

    if not os.path.exists(plugins_dir):
        print(f"ERROR: Directory not found: {plugins_dir}")
        return

    entries = sorted(os.listdir(plugins_dir))
    print(f"Directory contents: {entries}\n")

    for entry in entries:
        if entry.startswith('_') or entry.startswith('.'):
            continue

        entry_path = os.path.join(plugins_dir, entry)
        print(f"--- Checking: {entry} ---")

        if os.path.isdir(entry_path):
            init_file = os.path.join(entry_path, '__init__.py')
            plugin_file = os.path.join(entry_path, 'plugin.py')

            print(f"  Type: Package")
            print(f"  __init__.py: {'EXISTS' if os.path.exists(init_file) else 'MISSING'}")
            print(f"  plugin.py: {'EXISTS' if os.path.exists(plugin_file) else 'MISSING'}")

            # Try importing
            try:
                module_path = f"plugins.implementations.{entry}"
                module = importlib.import_module(module_path)

                # Find BasePlugin subclass
                found = False
                for name, obj in inspect.getmembers(
                    module, inspect.isclass
                ):
                    if (issubclass(obj, BasePlugin) and
                            obj is not BasePlugin):
                        print(f"  Plugin class: {name}")
                        print(f"  Name: {obj.name}")
                        print(f"  Description: {obj.description}")
                        print(f"  Version: {obj.version}")
                        print(f"  Status: OK ✓")
                        found = True
                        break

                if not found:
                    print(f"  Status: No BasePlugin subclass found!")

            except ImportError as e:
                print(f"  Status: Import Error - {e}")
            except Exception as e:
                print(f"  Status: Error - {e}")

        elif entry.endswith('.py'):
            print(f"  Type: Single file")
            try:
                module_path = f"plugins.implementations.{entry[:-3]}"
                spec = importlib.util.spec_from_file_location(
                    module_path, entry_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                found = False
                for name, obj in inspect.getmembers(
                    module, inspect.isclass
                ):
                    if (issubclass(obj, BasePlugin) and
                            obj is not BasePlugin):
                        print(f"  Plugin class: {name}")
                        print(f"  Status: OK ✓")
                        found = True
                        break

                if not found:
                    print(f"  Status: No BasePlugin subclass!")

            except Exception as e:
                print(f"  Status: Error - {e}")

        print()

    print("=" * 50)
    print("Diagnostic complete\n")


if __name__ == '__main__':
    check_plugins()
