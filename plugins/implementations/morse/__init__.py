"""
Morse Code Plugin Package
==========================
Morse code decoder, player, and transmitter for the
Ham Radio Web Application.

Features:
    - Real-time CW decode from RTL-SDR or configured radio
    - On-screen morse key (free-run and text modes)
    - Audio sidetone via browser Web Audio API
    - Logbook integration for logged QSOs
    - Adjustable timing (WPM, Farnsworth spacing)
    - Tone frequency 400-1200 Hz
    - Morse code reference chart

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.morse.plugin import MorsePlugin

__all__ = ['MorsePlugin']
