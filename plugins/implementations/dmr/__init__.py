"""
DMR (Digital Mobile Radio) Plugin Package
==========================================
Multi-tier DMR transceiver integration for the
Ham Radio Web Application.

Supports all DMR tiers:
    Tier I:   Unlicensed simplex (PMR446, MURS)
    Tier II:  Licensed conventional direct/repeater
    Tier III: Trunked systems (DMR Trunking Protocol)

DMR Technical Parameters:
    RF Bandwidth:    12.5 kHz
    Modulation:      4FSK (4-level Frequency Shift Keying)
    Symbol Rate:     4800 symbols/second
    Channel Access:  TDMA (2 timeslots per 12.5 kHz channel)
    Frame Duration:  30ms (superframe = 6 frames = 180ms)
    Slot Duration:   30ms per timeslot
    Voice Codec:     AMBE+2 (DVSI) or alternative (codec2)
    Data Rate:       9.6 kbps gross / ~3.6 kbps net voice

Backend:
    Uses QRadioLink or DSDPlus or rx_dsd (open source)
    for signal demodulation and vocoding.

    QRadioLink: https://qradiolink.org/
    DSD:        https://github.com/szechyjs/dsd

Source: https://qradiolink.org/open-source-DMR-transceiver-implementation.html

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.dmr.plugin import DMRPlugin

__all__ = ['DMRPlugin']
