"""
P25 Protocol Constants and Reference Data
==========================================
Constants, lookup tables, and data structures for
P25 (Project 25) digital radio implementation.

References:
    TIA-102.BAAA - Project 25 FDMA Common Air Interface
    TIA-102.AABF - Trunking Control Channel Messages
    TIA-102.AABE - Trunking Control Channel Formats
    https://github.com/blantonl/p25-survey
    https://github.com/boatbod/op25
"""

# ---------------------------------------------------------------
# P25 Phase definitions
# ---------------------------------------------------------------
P25_PHASES = {
    1: {
        'name': 'Phase 1',
        'modulation': 'C4FM / CQPSK',
        'channel_bw_khz': 12.5,
        'access': 'FDMA',
        'symbol_rate': 4800,
        'voice_codec': 'IMBE',
        'voice_bps': 4400,
        'description': 'Original P25 FDMA standard',
    },
    2: {
        'name': 'Phase 2',
        'modulation': 'HDQPSK',
        'channel_bw_khz': 12.5,
        'access': 'TDMA (2-slot)',
        'symbol_rate': 6000,
        'voice_codec': 'AMBE+2',
        'voice_bps': 2450,
        'description': 'TDMA standard for trunked systems',
    },
}

# ---------------------------------------------------------------
# P25 Data Unit ID codes (DUID)
# These identify the type of each P25 frame
# ---------------------------------------------------------------
P25_DUID = {
    0x0: 'HDU',     # Header Data Unit
    0x3: 'TDU',     # Terminator Data Unit (no LC)
    0x5: 'LDU1',    # Logical Link Data Unit 1 (voice)
    0x7: 'TSBK',    # Trunking Signaling Block
    0xA: 'LDU2',    # Logical Link Data Unit 2 (voice)
    0xC: 'PDU',     # Packet Data Unit
    0xF: 'TDULC',   # Terminator DU with Link Control
}

# ---------------------------------------------------------------
# Network Access Code (NAC) — 12-bit value
# Identifies P25 network/system. Default = 0x293 (F)
# Special values:
#   0x000 = Receive-all (wildcard)
#   0xF7B = Emergency
#   0xF7D = Digital P25 encryption
#   0xF7F = Analog clear
# ---------------------------------------------------------------
NAC_SPECIAL = {
    0x000: 'Receive All (wildcard)',
    0xF7B: 'Emergency',
    0xF7D: 'Encrypted',
    0xF7F: 'Analog Clear',
}
NAC_DEFAULT = 0x293  # Common default

# ---------------------------------------------------------------
# Manufacturer IDs (MFID)
# ---------------------------------------------------------------
MFID = {
    0x00: 'Standard (APCO-25)',
    0x01: 'Standard (reserved)',
    0x09: 'Kenwood',
    0x10: 'Relm / BK Radio',
    0x18: 'Motorola Solutions',
    0x20: 'Harris Corporation',
    0x28: 'EF Johnson',
    0x32: 'Dantel',
    0x40: 'Daniels Electronics',
    0x48: 'Transcrypt',
    0x55: 'Tait Radio',
    0x5C: 'Uniden',
    0x60: 'Vertex Standard',
    0x69: 'Icom',
    0x77: 'Kenwood',
    0x90: 'Tyco/Exar',
    0xA4: 'Nokia',
}

# ---------------------------------------------------------------
# Trunking system types
# ---------------------------------------------------------------
TRUNKING_TYPES = {
    'P25_PHASE1': {
        'name': 'P25 Phase 1 Trunking',
        'description': 'APCO P25 Phase 1 trunked system',
        'protocol': 'TIA-102.BAAA',
        'color': 'primary',
    },
    'P25_PHASE2': {
        'name': 'P25 Phase 2 Trunking',
        'description': 'APCO P25 Phase 2 TDMA trunked',
        'protocol': 'TIA-102.BACA',
        'color': 'info',
    },
    'SMARTNET': {
        'name': 'Motorola SmartNet/SmartZone',
        'description': 'Motorola Type II trunking',
        'protocol': 'Proprietary',
        'color': 'warning',
    },
    'EDACS': {
        'name': 'EDACS (Enhanced Digital Access)',
        'description': 'EF Johnson/Harris trunking',
        'protocol': 'Proprietary',
        'color': 'success',
    },
    'ANALOG': {
        'name': 'Analog FM',
        'description': 'Conventional analog FM',
        'protocol': 'None',
        'color': 'secondary',
    },
    'UNKNOWN': {
        'name': 'Unknown/Unidentified',
        'description': 'Signal detected but not decoded',
        'protocol': 'Unknown',
        'color': 'dark',
    },
}

# ---------------------------------------------------------------
# TSBK Opcode values (Trunking Signaling Block)
# These are the control channel messages in P25
# ---------------------------------------------------------------
TSBK_OPCODES = {
    # Group Voice Channel Grant
    0x00: 'GRP_V_CH_GRANT',
    # Reserved
    0x01: 'RSVD_01',
    # Group Voice Channel Grant Update
    0x02: 'GRP_V_CH_GRANT_UPDT',
    # Group Voice Channel Grant Update Explicit
    0x03: 'GRP_V_CH_GRANT_UPDT_EXP',
    # Unit-to-Unit Voice Channel Grant
    0x04: 'UU_V_CH_GRANT',
    # Unit-to-Unit Answer Request
    0x05: 'UU_ANS_REQ',
    # Unit-to-Unit Voice Channel Grant Update
    0x06: 'UU_V_CH_GRANT_UPDT',
    # Telephone Interconnect Voice Channel Grant
    0x08: 'TEL_INT_CH_GRANT',
    # Telephone Interconnect Voice Channel Grant Update
    0x09: 'TEL_INT_CH_GRANT_UPDT',
    # Group Data Channel Grant
    0x14: 'GRP_D_CH_GRANT',
    # Individual Data Channel Grant
    0x15: 'IND_D_CH_GRANT',
    # Group Data Channel Announcement
    0x16: 'GRP_D_CH_ANNCNMT',
    # Group Data Channel Announcement - Explicit
    0x17: 'GRP_D_CH_ANNCNMT_EXP',
    # Acknowledge Response - FNE
    0x20: 'ACK_RSP_FNE',
    # Queued Response
    0x21: 'QUE_RSP',
    # Deny Response
    0x27: 'DENY_RSP',
    # Group Affiliation Response
    0x28: 'GRP_AFF_RSP',
    # Secondary Control Channel Broadcast
    0x29: 'SCCB',
    # Group Affiliation Query
    0x2A: 'GRP_AFF_Q',
    # Location Registration Response
    0x2B: 'LOC_REG_RSP',
    # Unit Registration Response
    0x2C: 'U_REG_RSP',
    # Authentication Command
    0x2D: 'AUTH_CMD',
    # De-Registration Acknowledge
    0x2F: 'DEAUTH_ACK',
    # Unit-to-Unit Registration Command
    0x30: 'U_REG_CMD',
    # Cancel Service Request
    0x33: 'CANCEL_SRQ',
    # Extended Function Command
    0x34: 'EXT_FNCT_CMD',
    # Roaming Address Command
    0x35: 'ROAM_ADDR_CMD',
    # Authentication Response
    0x36: 'AUTH_RSP',
    # Identifier Update - Explicit
    0x39: 'IDEN_UP_TDMA',
    # Identifier Update
    0x3A: 'IDEN_UP',
    # Time and Date Announcement
    0x3B: 'TIME_DATE_ANNCNMT',
    # Status Query
    0x3C: 'STS_Q',
    # Status Update
    0x3D: 'STS_UPDT',
    # Message Update
    0x3E: 'MSG_UPDT',
    # Call Alert
    0x3F: 'CALL_ALRT',
    # Adjacent Status Broadcast
    0x3C: 'ADJ_STS_BCAST',
    # Network Status Broadcast
    0x3D: 'NET_STS_BCAST',
    # RF Subsystem Status Broadcast
    0x3E: 'RFSS_STS_BCAST',
    # Secondary Control Channel Broadcast Explicit
    0x39: 'SCCB_EXP',
}

# ---------------------------------------------------------------
# P25 encryption algorithm IDs
# ---------------------------------------------------------------
ENCRYPTION_ALGOS = {
    0x00: 'Unencrypted',
    0x01: 'DES-OFB (56-bit)',
    0x02: 'DES-OFB (56-bit) R',
    0x03: '3DES-OFB (168-bit)',
    0x04: 'AES-256-OFB',
    0x05: 'AES-128-OFB',
    0x09: 'Motorola Basic Privacy',
    0x21: 'DES-XL (56-bit)',
    0x22: 'DVI-XL (56-bit)',
    0x23: 'DVP-XL (56-bit)',
    0x24: 'ADP (256-bit)',
    0x25: 'AES-256',
    0x26: 'Motorola Type 1',
    0x80: 'Motorola DES-OFB-XL',
    0x81: 'Motorola DES-CFB-XL',
    0x84: 'Motorola AES-256',
    0x9F: 'RC4',
    0xAA: 'Motorola SEA',
    0xFF: 'Vendor Defined',
}

# ---------------------------------------------------------------
# P25 service options
# ---------------------------------------------------------------
SERVICE_OPTIONS = {
    'emergency': 'Emergency call',
    'encrypted': 'Encrypted voice/data',
    'duplex': 'Full duplex',
    'packet': 'Packet data',
    'priority': 'Priority call (0-7)',
}

# ---------------------------------------------------------------
# Survey scan states
# ---------------------------------------------------------------
SCAN_STATES = {
    'IDLE': 'Idle — not scanning',
    'SCANNING': 'Actively scanning frequencies',
    'LOCKED': 'Locked to a frequency',
    'DECODING': 'Decoding P25 signal',
    'TRUNKING': 'Following trunked system',
    'PAUSED': 'Scan paused by user',
}

# ---------------------------------------------------------------
# Common P25 public safety bands (MHz)
# ---------------------------------------------------------------
P25_BANDS = {
    'VHF Low': (25.0, 50.0),
    'VHF High': (136.0, 174.0),
    'UHF': (380.0, 512.0),
    '700 MHz': (763.0, 776.0),
    '800 MHz': (806.0, 870.0),
    '900 MHz': (896.0, 941.0),
}

# ---------------------------------------------------------------
# Common P25 system frequencies by agency type
# (illustrative examples only)
# ---------------------------------------------------------------
COMMON_P25_FREQS = [
    851.0125,  # US 800 MHz P25 band start
    851.5125,
    852.0125,
    769.00625, # 700 MHz public safety
    769.50625,
    155.3400,  # VHF P25
    460.0250,  # UHF P25
    460.5250,
]

# ---------------------------------------------------------------
# P25 frame sync word
# Used to detect P25 signals in SDR samples
# ---------------------------------------------------------------
P25_SYNC_WORD = 0x5575F5FF77FF  # 48-bit sync

# ---------------------------------------------------------------
# Vocoder types
# ---------------------------------------------------------------
VOCODERS = {
    'IMBE': {
        'name': 'IMBE',
        'description': 'Improved Multi-Band Excitation',
        'used_in': 'P25 Phase 1',
        'bitrate': '4400 bps (voice) + FEC',
        'vendor': 'DVSI / DSP Group',
        'open_source': False,
    },
    'AMBE+2': {
        'name': 'AMBE+2',
        'description': 'Advanced Multi-Band Excitation +2',
        'used_in': 'P25 Phase 2, DMR, D-STAR',
        'bitrate': '2450 bps',
        'vendor': 'DVSI',
        'open_source': False,
    },
    'codec2': {
        'name': 'Codec 2',
        'description': 'Open source vocoder',
        'used_in': 'FreeDV, M17',
        'bitrate': '700-3200 bps',
        'vendor': 'David Rowe (open source)',
        'open_source': True,
    },
    'mbe_server': {
        'name': 'mbe_server / imbe_vocoder',
        'description': 'Reverse-engineered IMBE/AMBE',
        'used_in': 'DSD, OP25',
        'bitrate': 'N/A (emulation)',
        'vendor': 'Open source',
        'open_source': True,
    },
}

# ---------------------------------------------------------------
# OP25 decoder modes
# ---------------------------------------------------------------
OP25_MODES = {
    'p25': 'P25 Phase 1 (C4FM/CQPSK)',
    'p25p2': 'P25 Phase 2 (TDMA)',
    'dstar': 'D-STAR',
    'dmr': 'DMR',
    'ysf': 'Yaesu System Fusion',
    'nxdn': 'NXDN',
}
