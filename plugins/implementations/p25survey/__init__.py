"""
P25 Survey Plugin Package
==========================
P25 (Project 25 / APCO-25) digital radio scanner and
survey tool for the Ham Radio Web Application.

Implements the p25-survey project concepts:
    https://github.com/blantonl/p25-survey

P25 Technical Overview:
    P25 is the North American public safety digital
    radio standard. It supports:

    Phase 1 (C4FM / CQPSK):
        - 9600 baud, 4-level FM modulation
        - 12.5 kHz channel spacing
        - IMBE voice codec (1200 bps net)
        - Conventional and trunked operation

    Phase 2 (HDQPSK - TDMA):
        - Two-slot TDMA on 12.5 kHz channels
        - AMBE+2 voice codec
        - Trunked systems only (ISSI/CSSI)

    Trunking Types:
        - SMARTNET / SMARTZONE (Motorola)
        - EDACS (EF-Johnson/Harris)
        - OpenSky
        - P25 Phase 1 Trunking
        - P25 Phase 2 Trunking

    Data Units:
        HDU  - Header Data Unit
        TDU  - Terminator Data Unit (no link control)
        TDULC- Terminator Data Unit with Link Control
        LDU1 - Logical Link Data Unit 1 (voice)
        LDU2 - Logical Link Data Unit 2 (voice + crypto)
        TSDU - Trunking Signalling Data Unit
        PDU  - Packet Data Unit
        VSELP- Enhanced Data Unit

    Survey Function:
        Scans a list of frequencies and records:
        - System type (P25 Phase 1/2, analog, etc.)
        - Signal strength (RSSI)
        - NAC (Network Access Code)
        - System ID
        - RFSS ID / Site ID
        - Active talkgroups
        - Unit IDs heard

Reference:
    APCO Project 25 Standards:
    https://www.apcointl.org/standards/p25/
    TIA-102 standards family

    p25-survey: https://github.com/blantonl/p25-survey
    OP25: https://github.com/boatbod/op25
    DSD+: Digital Speech Decoder Plus

Author: Ham Radio App Team
Version: 1.0.0
"""

from plugins.implementations.p25survey.plugin import (
    P25SurveyPlugin
)

__all__ = ['P25SurveyPlugin']
