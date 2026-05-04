"""
FLdigi Plugin Package
======================
FLdigi digital modem integration for the Ham Radio Application.

FLdigi is a modem program supporting many digital modes including:
    - PSK31/63/125/250/500/1000
    - RTTY (various speeds and shifts)
    - MFSK (multiple variants)
    - Olivia (multiple variants)
    - Thor (multiple variants)
    - Contestia
    - Wefax
    - MT63
    - Domino
    - Throb
    - WSPR
    - CW (Morse code)
    - And many more

FLdigi exposes an XML-RPC API on port 7362 by default,
which this plugin uses for full integration.

Source: https://github.com/w1hkj/fldigi/
Documentation: http://www.w1hkj.com/FldigiHelp/

Installation:
    Copy the fldigi directory to plugins/implementations/
    Dependencies are installed automatically on first run.

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.fldigi.plugin import FldigiPlugin

# Export for automatic plugin discovery by PluginLoader
__all__ = ['FldigiPlugin']