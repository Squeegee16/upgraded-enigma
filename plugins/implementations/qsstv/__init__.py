"""
QSSTV Plugin Package
=====================
QSSTV Slow Scan Television integration for the Ham Radio
Web Application.

QSSTV is a Linux application for receiving and transmitting
Slow Scan Television (SSTV) and Digital Radio Mondiale (DRM)
for amateur radio operators.

Supported SSTV Modes:
    Martin:
        - Martin M1 (114 seconds)
        - Martin M2 (58 seconds)
        - Martin M3 (28 seconds)
        - Martin M4 (14 seconds)
    Scottie:
        - Scottie S1 (110 seconds)
        - Scottie S2 (71 seconds)
        - Scottie S3 (55 seconds)
        - Scottie DX (269 seconds)
    Robot:
        - Robot 8 (8 seconds, B&W)
        - Robot 12 (12 seconds, color)
        - Robot 24 (24 seconds)
        - Robot 36 (36 seconds)
        - Robot 72 (72 seconds)
    Wraase:
        - Wraase SC-2 120 (120 seconds)
        - Wraase SC-2 180 (180 seconds)
    PD modes:
        - PD50, PD90, PD120, PD160, PD180, PD240, PD290
    Pasokon:
        - P3, P5, P7
    FAX modes:
        - FAX480 (weather fax)

Source: https://github.com/ON4QZ/QSSTV
Documentation: https://users.telenet.be/on4qz/qsstv/

Installation:
    Copy qsstv/ directory to plugins/implementations/
    Dependencies are installed automatically on first run.

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.qsstv.plugin import QSStvPlugin

# Export for automatic plugin discovery
__all__ = ['QSStvPlugin']