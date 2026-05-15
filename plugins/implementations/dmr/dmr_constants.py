"""
DMR Protocol Constants and Reference Data
==========================================
Constants, lookup tables, and reference data
for DMR (Digital Mobile Radio) implementation.

Reference:
    ETSI TS 102 361-1: DMR Air Interface Protocol
    ETSI TS 102 361-2: DMR Voice and Generic Services
    ETSI TS 102 361-3: DMR Data Protocol
    ETSI TS 102 361-4: DMR Trunking Protocol (Tier III)
    https://qradiolink.org/open-source-DMR-transceiver-implementation.html
"""

# ---------------------------------------------------------------
# DMR Tier definitions
# ---------------------------------------------------------------
DMR_TIERS = {
    1: {
        'name': 'Tier I',
        'description': 'Unlicensed simplex',
        'example': 'PMR446, MURS',
        'max_power_w': 0.5,
        'features': ['simplex', 'no_repeater'],
    },
    2: {
        'name': 'Tier II',
        'description': 'Licensed conventional',
        'example': 'Amateur DMR, commercial',
        'max_power_w': 100,
        'features': [
            'simplex', 'repeater', 'roaming',
            'private_call', 'group_call',
        ],
    },
    3: {
        'name': 'Tier III',
        'description': 'Licensed trunked system',
        'example': 'MOTOTRBO Connect Plus',
        'max_power_w': 100,
        'features': [
            'trunking', 'dynamic_channel',
            'site_roaming', 'interconnect',
        ],
    },
}

# ---------------------------------------------------------------
# TDMA Frame structure
# ---------------------------------------------------------------
# One superframe = 6 frames = 360ms
# One frame = 2 timeslots = 60ms
# One timeslot = 30ms = 144 bits
FRAME_DURATION_MS = 60
TIMESLOT_DURATION_MS = 30
SUPERFRAME_DURATION_MS = 360
BITS_PER_TIMESLOT = 144
SYMBOL_RATE = 4800         # symbols/second
CHANNEL_BW_KHZ = 12.5     # kHz
DEVIATION_KHZ = 1.944      # kHz (4FSK deviation)

# ---------------------------------------------------------------
# Burst types (slot types in DMR frame)
# ---------------------------------------------------------------
BURST_TYPES = {
    0: 'PI Header',
    1: 'Voice Header (VH)',
    2: 'Terminator with Link Control (TLC)',
    3: 'CSBK (Control Signalling Block)',
    4: 'MBC Header',
    5: 'MBC Continuation',
    6: 'Data Header',
    7: 'Rate ½ Data (D½)',
    8: 'Rate ¾ Data (D¾)',
    9: 'Idle',
    10: 'Rate 1 Data (D1)',
    11: 'Rate 1 Data (D1 — Last)',
    12: 'Unknown',
}

# ---------------------------------------------------------------
# FLCO (Full Link Control Opcode) values
# ---------------------------------------------------------------
FLCO = {
    0x00: 'Group voice channel user',
    0x03: 'Unit-to-unit voice channel user',
    0x04: 'Unit-to-unit answer request',
    0x10: 'Talker alias header',
    0x11: 'Talker alias block 1',
    0x12: 'Talker alias block 2',
    0x13: 'Talker alias block 3',
    0x20: 'GPS info',
}

# ---------------------------------------------------------------
# CSBK opcodes
# ---------------------------------------------------------------
CSBKO = {
    0x00: 'BS Outbound Activation',
    0x01: 'Unit-to-Unit Service Request',
    0x02: 'Unit-to-Unit Service Answer Response',
    0x03: 'Channel Timing Opcode',
    0x04: 'TS I/F Opcode',
    0x0F: 'Preamble CSBK',
    0x1D: 'Unit to Unit Voice Service Request',
    0x1E: 'Unit to Unit Voice Service Answer Response',
    0x1F: 'Channel Grant',
    0x20: 'Negative Acknowledgement Response',
    0x27: 'Radio Check',
    0x28: 'Radio Check Acknowledgement',
    0x2A: 'Call Alert',
    0x2B: 'Call Alert Ack',
    0x2C: 'Group Call Cancel',
    0x2D: 'Get/Set Radio ID',
    0x3F: 'Random Access',
}

# ---------------------------------------------------------------
# Color Codes (0-15, used to identify repeaters/cells)
# ---------------------------------------------------------------
COLOR_CODES = list(range(16))  # 0-15

# ---------------------------------------------------------------
# Common amateur DMR talk groups (examples)
# ---------------------------------------------------------------
COMMON_TALKGROUPS = {
    # International
    91: 'Worldwide',
    93: 'North America',
    95: 'Pacific',
    97: 'Australia',
    98: 'South Africa',
    99: 'Global English',
    # North America
    3100: 'North America',
    3101: 'USA - New England',
    3102: 'USA - Atlantic',
    3103: 'USA - Southeast',
    3104: 'USA - Great Lakes',
    3105: 'USA - Central',
    3106: 'USA - Mountain',
    3107: 'USA - Pacific',
    # Canada
    3026: 'Canada - Nationwide',
    302601: 'Canada - Quebec (French)',
    302602: 'Canada - Ontario',
    302603: 'Canada - British Columbia',
    # Special
    9990: 'Parrot / Echo',
    9999: 'APRS',
    310998: 'Interop',
    311: 'TAC 310',
    312: 'TAC 311',
    313: 'TAC 312',
    # Other
    2: 'Local 2',
    3: 'Local 3',
    13: 'Worldwide English',
}

# ---------------------------------------------------------------
# Common DMR radio frequencies (MHz)
# ---------------------------------------------------------------
COMMON_FREQUENCIES = {
    # VHF
    'VHF Digital Calling': 145.5,
    'PMR446 Ch1 (EU)': 446.00625,
    # UHF Amateur
    'UHF Digital 1': 433.450,
    'UHF Digital 2': 438.200,
    # US DMR simplex
    'MURS 1': 151.820,
    'MURS 2': 151.880,
    'MURS 3': 151.940,
    'MURS 4': 154.570,
    'MURS 5': 154.600,
}

# ---------------------------------------------------------------
# Voice codecs used in DMR
# ---------------------------------------------------------------
CODECS = {
    'AMBE+2': {
        'description': 'Advanced Multi-Band Excitation+2',
        'vendor': 'DVSI',
        'bitrate_bps': 2450,
        'note': 'Proprietary — requires hardware dongle '
                'or licensed software',
    },
    'CODEC2': {
        'description': 'Open source vocoder',
        'vendor': 'Open source (David Rowe)',
        'bitrate_bps': 3200,
        'note': 'Free, open source alternative',
    },
    'mbe_lib': {
        'description': 'Multi-Band Excitation library',
        'vendor': 'Open source (reverse engineered)',
        'bitrate_bps': 2450,
        'note': 'Used by DSD/imbe_vocoder',
    },
}

# ---------------------------------------------------------------
# DMR network types
# ---------------------------------------------------------------
NETWORK_TYPES = {
    'BrandMeister': {
        'description': 'Global amateur DMR network',
        'url': 'https://brandmeister.network/',
    },
    'DMR-MARC': {
        'description': 'DMR-MARC network',
        'url': 'https://www.dmr-marc.net/',
    },
    'TGIF': {
        'description': 'TGIF Network',
        'url': 'https://tgif.network/',
    },
    'Standalone': {
        'description': 'Standalone repeater',
        'url': '',
    },
    'None': {
        'description': 'Direct / simplex only',
        'url': '',
    },
}

# ---------------------------------------------------------------
# Call types
# ---------------------------------------------------------------
CALL_TYPES = {
    0: 'Group Call',
    1: 'Private Call',
    2: 'All Call',
    3: 'Emergency',
}

# ---------------------------------------------------------------
# Service options
# ---------------------------------------------------------------
SERVICE_OPTIONS = {
    'emergency': 'Emergency alert',
    'broadcast': 'Broadcast (listen only)',
    'ovcm': 'OVCM (Open Voice Channel Mode)',
    'priority': 'Priority call',
}

# ---------------------------------------------------------------
# Frame sync patterns (hex strings for display)
# ---------------------------------------------------------------
# BS (Base Station) sync patterns
SYNC_BS_DATA = 'DFF57D75DF5D'
SYNC_BS_VOICE = '755FD7DF75F7'

# MS (Mobile Station) sync patterns
SYNC_MS_DATA = 'D5D7F77FD757'
SYNC_MS_VOICE = '7F7D5DD57DFD'

# Direct Mode (Tier I / Tier II simplex)
SYNC_DIRECT_DATA = 'DDDF77B7DBBD'
SYNC_DIRECT_VOICE = 'DB7E8EBEF7E7'

# ---------------------------------------------------------------
# Error correction
# ---------------------------------------------------------------
ERROR_CORRECTION = {
    'BPTC(196,96)': 'Block Product Turbo Code for voice',
    'TRELLIS(3/4)': '3/4 rate trellis for data',
    'RS(12,9)': 'Reed-Solomon for EMB',
    'GOLAY(20,8)': 'Golay for sync',
    'HAMMING(13,9)': 'Hamming for LC header',
    'HAMMING(15,11)': 'Hamming for data header',
}
