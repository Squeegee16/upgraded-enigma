"""
OpenWebRX Plugin Package
========================
OpenWebRX web-based SDR receiver integration for the
Ham Radio Web Application.

OpenWebRX provides:
    - Multi-user web-based SDR waterfall display
    - Real-time spectrum monitoring
    - Digital mode decoding (FT8, WSPR, APRS, etc.)
    - Multiple SDR hardware support via SoapySDR
    - WebSocket-based real-time communication

This plugin:
    - Embeds the OpenWebRX interface in the app UI
    - Monitors the OpenWebRX API for decoded signals
    - Logs decoded digital mode contacts to the logbook
    - Provides configuration management
    - Syncs frequency with the configured radio

Deployment:
    OpenWebRX runs as a Docker sidecar container.
    The app communicates with it via HTTP at
    http://openwebrx:8073 (internal Docker network).

Source: https://github.com/jketterl/openwebrx
Website: https://openwebrx.de/

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.openwebrx.plugin import (
    OpenWebRXPlugin
)

__all__ = ['OpenWebRXPlugin']
