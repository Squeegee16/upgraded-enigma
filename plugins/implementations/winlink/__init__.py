"""
Winlink Express Plugin Package
================================
Winlink email over radio integration for the Ham Radio Application.

This plugin provides Winlink connectivity via two methods:
    1. Winlink Express via Wine (Windows application on Linux)
    2. Pat Winlink (native Linux client - recommended)
       https://getpat.io/

Winlink is a worldwide radio email system providing:
    - Email over radio
    - Position reporting
    - Emergency communications
    - Multiple connection modes (VHF packet, HF Pactor, VARA, etc.)

Official Site: https://winlink.org/WinlinkExpress
Pat Client: https://getpat.io/

Installation:
    Copy the winlink directory to plugins/implementations/
    Dependencies are installed automatically on first run.

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.winlink.plugin import WinlinkPlugin

# Export for automatic plugin discovery
__all__ = ['WinlinkPlugin']