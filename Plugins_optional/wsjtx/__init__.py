"""
WSJT-X Plugin Package
======================
WSJT-X weak signal digital modes integration for the
Ham Radio Web Application.

WSJT-X supports digital modes optimized for weak signal
communication including:
    - FT8  (Franke-Taylor 8-tone, most popular)
    - FT4  (Franke-Taylor 4-tone, faster than FT8)
    - JT65 (Joe Taylor 65-tone, moonbounce/EME)
    - JT9  (Joe Taylor 9-tone, HF DXing)
    - WSPR (Weak Signal Propagation Reporter)
    - Q65  (Q-ary 65-tone, for EME and aircraft scatter)
    - MSK144 (Meteor scatter)

WSJT-X communicates with external applications via
UDP multicast on port 2237 (default).

This plugin:
    - Listens to WSJT-X UDP multicast stream
    - Decodes and displays received spots
    - Logs QSOs to the central logbook
    - Controls WSJT-X via UDP command protocol
    - Displays real-time decode activity

Protocol Reference:
    NetworkMessage.hpp in WSJT-X source code
    https://github.com/WSJTX/wsjtx/blob/master/Network/NetworkMessage.hpp

Source: https://github.com/WSJTX/wsjtx
Documentation: https://physics.princeton.edu/pulsar/k1jt/wsjtx-doc/

Installation:
    Copy wsjtx/ directory to plugins/implementations/
    Dependencies installed automatically on first run.

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.wsjtx.plugin import WSJTXPlugin

# Export for automatic plugin discovery
__all__ = ['WSJTXPlugin']