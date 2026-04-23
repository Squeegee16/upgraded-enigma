"""
OpenWebRX Plugin Package
========================
Multi-user SDR receiver integration for the Ham Radio Application.

OpenWebRX provides a web-based SDR interface supporting multiple
simultaneous users with demodulation, waterfall display, and
digital mode decoding.

Source: https://fms.komkon.org/OWRX/
GitHub: https://github.com/jketterl/openwebrx

Installation:
    Copy the openwebrx directory to plugins/implementations/
    The plugin will install required dependencies on first run.

Supports:
    - RTL-SDR devices
    - HackRF
    - SDRplay
    - PlutoSDR
    - And many more via SoapySDR

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.openwebrx.plugin import OpenWebRXPlugin

# Export plugin class for automatic discovery by the plugin loader
__all__ = ['OpenWebRXPlugin']