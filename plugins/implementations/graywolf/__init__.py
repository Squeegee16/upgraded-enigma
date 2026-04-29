"""
GrayWolf Plugin Package
=======================
Winlink gateway client integration for the Ham Radio Application.

GrayWolf provides email over radio via the Winlink network.
Source: https://github.com/chrissnell/graywolf

Installation:
    Copy the graywolf directory to plugins/implementations/
    The plugin will install required dependencies on first run.

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.graywolf.plugin import GrayWolfPlugin

# Export the plugin class for automatic discovery by the plugin loader
__all__ = ['GrayWolfPlugin']