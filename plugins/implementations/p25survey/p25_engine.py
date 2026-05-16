"""
P25 Survey Engine
==================
Core P25 signal detection, decoding, and survey engine.

Implements the survey methodology from:
    https://github.com/blantonl/p25-survey

Survey Process:
    1. Step through a list of frequencies
    2. At each frequency, sample the RF signal
    3. Detect P25 sync word (0x5575F5FF77FF)
    4. If P25 detected, decode NAC, RFSS, Site ID
    5. Attempt to identify trunking control channel
    6. Record all discovered systems and parameters
    7. Monitor active talkgroups and unit IDs

Receive Modes:
    Conventional:
        Lock to a single frequency and decode.
        Reports: NAC, encryption, talkgroup, unit ID

    Survey/Scan:
        Cycle through frequency list.
        Records all P25 systems found.
        Reports: frequency, NAC, system type, RSSI

    Trunked:
        Lock to control channel.
        Follow voice grants to voice channels.
        Reports: all group calls, unit registrations

Decoder Integration:
    Uses OP25 (https://github.com/boatbod/op25) as the
    primary backend. Falls back to DSD for Phase 1.
    Mock mode available for testing without hardware.
"""

import os
import json
import math
import shutil
import subprocess
import threading
import time
from datetime import datetime
from collections import deque

from plugins.implementations.p25survey.p25_constants import (
    P25_DUID,
    TSBK_OPCODES,
    TRUNKING_TYPES,
    ENCRYPTION_ALGOS,
    NAC_SPECIAL,
    NAC_DEFAULT,          # ← ADD THIS
    P25_SYNC_WORD,
    SCAN_STATES,
)


class P25Frame:
    """
    Represents a decoded P25 frame/data unit.

    Contains all parameters decoded from a single
    P25 transmission including NAC, DUID, talkgroup,
    source unit ID, and optional trunking data.
    """

    def __init__(self):
        """Initialise empty P25 frame."""
        self.timestamp = datetime.utcnow().isoformat()
        self.frequency = 0.0         # MHz
        self.duid = None             # Data Unit ID
        self.duid_name = ''          # Human-readable DUID
        self.nac = 0                 # Network Access Code
        self.mfid = 0x00             # Manufacturer ID
        self.talkgroup = 0           # Talkgroup ID
        self.source_unit = 0         # Source radio unit ID
        self.rfss_id = 0             # RF Subsystem ID
        self.site_id = 0             # Site ID
        self.system_id = 0           # System ID
        self.is_encrypted = False    # Encryption flag
        self.encryption_algo = 0x00  # Algorithm ID
        self.key_id = 0              # Encryption key ID
        self.emergency = False       # Emergency flag
        self.is_voice = False        # Voice frame flag
        self.is_data = False         # Data frame flag
        self.is_tsbk = False         # Trunking block flag
        self.tsbk_opcode = None      # TSBK opcode
        self.channel = 0             # Voice channel number
        self.phase = 1               # P25 Phase (1 or 2)
        self.rssi = None             # Signal strength dBm
        self.ber = None              # Bit error rate %
        self.snr = None              # Signal-to-noise dB
        # TSBK-specific fields
        self.granted_tg = 0          # Granted talkgroup
        self.granted_channel = 0     # Granted channel
        self.adjacent_sites = []     # Adjacent site list

    def to_dict(self):
        """Serialise frame to dictionary."""
        nac_name = NAC_SPECIAL.get(self.nac, '')
        enc_name = ENCRYPTION_ALGOS.get(
            self.encryption_algo, 'Unknown'
        )
        tsbk_name = TSBK_OPCODES.get(
            self.tsbk_opcode, ''
        )

        return {
            'timestamp': self.timestamp,
            'frequency': self.frequency,
            'duid': self.duid,
            'duid_name': self.duid_name,
            'nac': f'0x{self.nac:03X}',
            'nac_int': self.nac,
            'nac_name': nac_name,
            'mfid': f'0x{self.mfid:02X}',
            'talkgroup': self.talkgroup,
            'talkgroup_hex': f'{self.talkgroup:04X}',
            'source_unit': self.source_unit,
            'rfss_id': self.rfss_id,
            'site_id': self.site_id,
            'system_id': self.system_id,
            'is_encrypted': self.is_encrypted,
            'encryption_algo': enc_name,
            'emergency': self.emergency,
            'is_voice': self.is_voice,
            'is_data': self.is_data,
            'is_tsbk': self.is_tsbk,
            'tsbk_opcode': tsbk_name,
            'channel': self.channel,
            'phase': self.phase,
            'rssi': self.rssi,
            'ber': self.ber,
            'snr': self.snr,
            'granted_tg': self.granted_tg,
            'granted_channel': self.granted_channel,
        }


class P25System:
    """
    Represents a discovered P25 system.

    Aggregates information about a P25 system
    discovered during the survey scan, including
    all decoded parameters over time.
    """

    def __init__(self, nac, frequency):
        """
        Initialise discovered P25 system.

        Args:
            nac: Network Access Code (0-4095)
            frequency: Control channel frequency (MHz)
        """
        self.nac = nac
        self.control_channel = frequency
        self.voice_channels = set()
        self.talkgroups = {}      # {tg_id: last_seen}
        self.unit_ids = {}        # {unit_id: last_seen}
        self.rfss_id = 0
        self.site_id = 0
        self.system_id = 0
        self.phase = 1
        self.mfid = 0x00
        self.trunking_type = 'P25_PHASE1'
        self.adjacent_sites = []
        self.first_seen = datetime.utcnow().isoformat()
        self.last_seen = self.first_seen
        self.frame_count = 0
        self.rssi_samples = []
        self.is_encrypted = False
        self.encryption_algos = set()

    @property
    def avg_rssi(self):
        """Average RSSI from all samples."""
        if not self.rssi_samples:
            return None
        return round(
            sum(self.rssi_samples) /
            len(self.rssi_samples), 1
        )

    def update(self, frame):
        """
        Update system data from a new decoded frame.

        Args:
            frame: P25Frame instance
        """
        self.last_seen = frame.timestamp
        self.frame_count += 1

        if frame.rssi is not None:
            self.rssi_samples.append(frame.rssi)
            # Keep last 100 RSSI samples
            if len(self.rssi_samples) > 100:
                self.rssi_samples.pop(0)

        if frame.talkgroup:
            self.talkgroups[frame.talkgroup] = (
                frame.timestamp
            )

        if frame.source_unit:
            self.unit_ids[frame.source_unit] = (
                frame.timestamp
            )

        if frame.rfss_id:
            self.rfss_id = frame.rfss_id
        if frame.site_id:
            self.site_id = frame.site_id
        if frame.system_id:
            self.system_id = frame.system_id
        if frame.phase:
            self.phase = frame.phase
        if frame.mfid:
            self.mfid = frame.mfid

        if frame.is_encrypted:
            self.is_encrypted = True
            if frame.encryption_algo:
                self.encryption_algos.add(
                    frame.encryption_algo
                )

        if frame.granted_channel:
            self.voice_channels.add(
                frame.granted_channel
            )

    def to_dict(self):
        """Serialise to dictionary for API response."""
        from plugins.implementations.p25survey\
            .p25_constants import (
            TRUNKING_TYPES, MFID, ENCRYPTION_ALGOS
        )

        tt = TRUNKING_TYPES.get(
            self.trunking_type, {}
        )
        mfid_name = MFID.get(self.mfid, 'Unknown')

        enc_names = [
            ENCRYPTION_ALGOS.get(a, f'0x{a:02X}')
            for a in self.encryption_algos
        ]

        return {
            'nac': f'0x{self.nac:03X}',
            'nac_int': self.nac,
            'nac_special': NAC_SPECIAL.get(self.nac, ''),
            'control_channel': self.control_channel,
            'voice_channels': sorted(
                list(self.voice_channels)
            ),
            'talkgroup_count': len(self.talkgroups),
            'talkgroups': sorted(self.talkgroups.keys()),
            'unit_count': len(self.unit_ids),
            'rfss_id': self.rfss_id,
            'site_id': self.site_id,
            'system_id': self.system_id,
            'phase': self.phase,
            'mfid': f'0x{self.mfid:02X}',
            'mfid_name': mfid_name,
            'trunking_type': self.trunking_type,
            'trunking_name': tt.get('name', ''),
            'trunking_color': tt.get('color', 'secondary'),
            'adjacent_sites': self.adjacent_sites,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'frame_count': self.frame_count,
            'avg_rssi': self.avg_rssi,
            'is_encrypted': self.is_encrypted,
            'encryption_algos': enc_names,
        }


class P25SurveyEngine:
    """
    P25 Survey and decode engine.

    Manages RTL-SDR/radio interface, OP25/DSD decoder
    process, survey scanning, and frame parsing.
    """

    def __init__(self, config):
        """
        Initialise P25 engine.

        Args:
            config: Plugin configuration dictionary
        """
        self.config = config

        # Process management
        self._sdr_process = None
        self._decoder_process = None
        self._process_lock = threading.Lock()

        # State
        self._running = False
        self._scan_state = 'IDLE'
        self._source = config.get('source', 'sdr')

        # Current channel
        self._channel = {
            'frequency': config.get(
                'center_frequency_mhz', 851.0
            ),
            'nac': config.get('nac', NAC_DEFAULT),
            'phase': config.get('phase', 1),
            'mode': config.get('scan_mode', 'conventional'),
        }

        # Frame history
        self._frames = deque(maxlen=300)
        self._frames_lock = threading.Lock()

        # Discovered systems
        self._systems = {}   # {nac: P25System}
        self._systems_lock = threading.Lock()

        # Active call tracking
        self._active_call = None
        self._active_call_lock = threading.Lock()

        # Survey frequency list
        self._survey_freqs = list(
            config.get('survey_frequencies', [])
        )
        self._survey_index = 0
        self._survey_thread = None

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Statistics
        self._stats = {
            'frames_decoded': 0,
            'voice_frames': 0,
            'tsbk_frames': 0,
            'data_frames': 0,
            'errors': 0,
            'systems_found': 0,
            'talkgroups_heard': set(),
            'units_heard': set(),
            'ber_avg': 0.0,
            'last_rssi': None,
            'active_since': None,
        }

        # Find decoder
        self._decoder_name = None
        self._decoder_path = None
        self._find_decoder()

    def _find_decoder(self):
        """Find available P25 decoder."""
        # Look for OP25 rx.py
        op25_paths = [
            '/usr/local/src/op25/op25/'
            'gr-op25-repeater/apps/rx.py',
            '/opt/op25/op25/gr-op25-repeater/apps/rx.py',
            os.path.expanduser(
                '~/op25/op25/gr-op25-repeater/apps/rx.py'
            ),
        ]
        for path in op25_paths:
            if os.path.exists(path):
                self._decoder_name = 'op25'
                self._decoder_path = path
                self._add_log(
                    f"OP25 decoder found: {path}"
                )
                return

        # Fallback to DSD
        dsd = shutil.which('dsd')
        if dsd:
            self._decoder_name = 'dsd'
            self._decoder_path = dsd
            self._add_log(
                f"DSD decoder found: {dsd}"
            )
            return

        self._add_log(
            "No P25 decoder found — demo mode. "
            "Install OP25: github.com/boatbod/op25",
            'warning'
        )

    def _add_log(self, message, level='info'):
        """Add entry to log buffer."""
        with self._log_lock:
            self._logs.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': str(message)
            })
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]

    def get_logs(self, limit=100):
        """Get recent log entries."""
        with self._log_lock:
            return list(reversed(self._logs[-limit:]))

    # ----------------------------------------------------------
    # Receive / scan control
    # ----------------------------------------------------------

    def start_receive(self):
        """
        Start P25 receive/survey.

        Returns:
            tuple: (success: bool, message: str)
        """
        if self._running:
            return False, "Already running"

        self._running = True
        self._scan_state = 'SCANNING'
        self._stats['active_since'] = (
            datetime.utcnow().isoformat()
        )

        mode = self._channel.get('mode', 'conventional')
        self._add_log(
            f"Starting P25 receive | "
            f"Mode: {mode} | "
            f"Source: {self._source} | "
            f"Freq: "
            f"{self._channel['frequency']:.4f} MHz"
        )

        if self._source == 'sdr':
            success, msg = self._start_sdr_pipeline()
        else:
            success, msg = self._start_radio_receive()

        if success and mode == 'survey':
            self._start_survey_scanner()

        return success, msg

    def _start_sdr_pipeline(self):
        """
        Start RTL-SDR -> OP25/DSD decoder pipeline.

        Returns:
            tuple: (success: bool, message: str)
        """
        with self._process_lock:
            freq_hz = int(
                self._channel['frequency'] * 1e6
            )
            gain = self.config.get('sdr_gain', 40)
            device = self.config.get(
                'sdr_device_index', 0
            )

            rtl_fm = shutil.which('rtl_fm')
            if not rtl_fm:
                self._add_log(
                    "rtl_fm not found — demo mode",
                    'warning'
                )
                self._start_mock_receive()
                return True, "Demo mode (no RTL-SDR)"

            if not self._decoder_name:
                self._add_log(
                    "No P25 decoder — demo mode",
                    'warning'
                )
                self._start_mock_receive()
                return True, "Demo mode (no decoder)"

            try:
                if self._decoder_name == 'op25':
                    # OP25 handles RTL-SDR directly
                    cmd = [
                        'python3',
                        self._decoder_path,
                        '--args',
                        f'rtl={device}',
                        '--gains',
                        f'lna:{gain}',
                        '-f', str(freq_hz),
                        '-q', '-v', '1',
                        '-T', 'trunk.tsv',
                        '-l',
                        f'http:0.0.0.0:'
                        f'{self.config.get("op25_port", 8080)}',
                    ]

                    self._decoder_process = (
                        subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            cwd=os.path.dirname(
                                self._decoder_path
                            )
                        )
                    )

                else:
                    # rtl_fm -> dsd pipeline
                    rtl_cmd = [
                        rtl_fm,
                        '-f', str(freq_hz),
                        '-M', 'fm',
                        '-s', '22050',
                        '-g', str(gain),
                        '-r', '22050',
                        '-d', str(device),
                        '-'
                    ]
                    dsd_cmd = [
                        self._decoder_path,
                        '-f', 'p',    # P25
                        '-i', '-',
                        '-o', '-',
                        '-n', '-q',
                    ]

                    self._sdr_process = subprocess.Popen(
                        rtl_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL
                    )
                    self._decoder_process = (
                        subprocess.Popen(
                            dsd_cmd,
                            stdin=(
                                self._sdr_process.stdout
                            ),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            bufsize=1
                        )
                    )

                self._start_output_parser()
                self._add_log(
                    f"✓ SDR pipeline started: "
                    f"{self._channel['frequency']:.4f} MHz"
                )
                return True, (
                    f"Receiving on "
                    f"{self._channel['frequency']:.4f} MHz"
                )

            except Exception as e:
                self._add_log(
                    f"SDR start error: {e}", 'error'
                )
                self._start_mock_receive()
                return True, f"Error — demo mode"

    def _start_radio_receive(self):
        """
        Start receive via radio audio input.

        Returns:
            tuple: (success: bool, message: str)
        """
        self._add_log("Starting radio audio receive...")

        if not self._decoder_name:
            self._start_mock_receive()
            return True, "Radio receive — demo mode"

        try:
            audio_dev = self.config.get(
                'radio_audio_device', None
            )

            if audio_dev and shutil.which('arecord'):
                arecord_cmd = [
                    'arecord',
                    '-D', audio_dev,
                    '-r', '48000',
                    '-f', 'S16_LE',
                    '-c', '1',
                    '-'
                ]

                dsd_cmd = [
                    self._decoder_path,
                    '-f', 'p',
                    '-i', '-',
                    '-o', '-',
                    '-n', '-q',
                ]

                self._sdr_process = subprocess.Popen(
                    arecord_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                self._decoder_process = subprocess.Popen(
                    dsd_cmd,
                    stdin=self._sdr_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                self._start_output_parser()
                return True, "Radio audio receive started"

            else:
                self._start_mock_receive()
                return True, "Radio receive — demo mode"

        except Exception as e:
            self._add_log(
                f"Radio receive error: {e}", 'error'
            )
            self._start_mock_receive()
            return True, "Error — demo mode"

    def _start_mock_receive(self):
        """
        Start mock P25 receive for demo/testing.

        Generates synthetic P25 frames to demonstrate
        all plugin features without real hardware.
        """
        self._add_log(
            "Demo mode: generating synthetic P25 frames"
        )

        def mock_loop():
            import random

            # Synthetic P25 systems
            mock_systems = [
                {
                    'nac': 0x293,
                    'freq': self._channel['frequency'],
                    'type': 'P25_PHASE1',
                    'rfss': 1, 'site': 1,
                    'system_id': 0x001,
                    'tgs': [1, 2, 100, 200, 9999],
                },
                {
                    'nac': 0x580,
                    'freq': (
                        self._channel['frequency'] + 0.5
                    ),
                    'type': 'P25_PHASE2',
                    'rfss': 2, 'site': 3,
                    'system_id': 0x002,
                    'tgs': [10, 20, 30, 500],
                },
            ]

            unit_counter = 3000000

            while self._running:
                time.sleep(random.uniform(1.5, 4.0))
                if not self._running:
                    break

                sys = random.choice(mock_systems)
                tg = random.choice(sys['tgs'])
                unit = random.randint(3000001, 3999999)

                # TSBK frame (channel grant)
                tsbk = P25Frame()
                tsbk.frequency = sys['freq']
                tsbk.nac = sys['nac']
                tsbk.duid = 0x7
                tsbk.duid_name = 'TSBK'
                tsbk.is_tsbk = True
                tsbk.tsbk_opcode = 0x00
                tsbk.talkgroup = tg
                tsbk.source_unit = unit
                tsbk.rfss_id = sys['rfss']
                tsbk.site_id = sys['site']
                tsbk.system_id = sys['system_id']
                tsbk.granted_tg = tg
                tsbk.granted_channel = random.randint(
                    1, 100
                )
                tsbk.rssi = round(
                    random.uniform(-105, -65), 1
                )
                tsbk.ber = round(
                    random.uniform(0, 3), 2
                )
                tsbk.phase = (
                    1 if sys['type'] == 'P25_PHASE1'
                    else 2
                )
                tsbk.is_encrypted = random.random() < 0.15
                if tsbk.is_encrypted:
                    tsbk.encryption_algo = random.choice(
                        [0x00, 0x01, 0x04, 0x80]
                    )

                self._process_frame(tsbk)

                # Voice frames
                voice_dur = random.uniform(2, 10)
                start = time.time()
                seq = 0

                while (
                    time.time() - start < voice_dur
                    and self._running
                ):
                    vf = P25Frame()
                    vf.frequency = sys['freq']
                    vf.nac = sys['nac']
                    vf.duid = random.choice([0x5, 0xA])
                    vf.duid_name = (
                        'LDU1' if vf.duid == 0x5
                        else 'LDU2'
                    )
                    vf.is_voice = True
                    vf.talkgroup = tg
                    vf.source_unit = unit
                    vf.rssi = tsbk.rssi + random.uniform(
                        -5, 5
                    )
                    vf.ber = max(
                        0,
                        tsbk.ber + random.uniform(
                            -1, 1
                        )
                    )
                    vf.phase = tsbk.phase
                    vf.is_encrypted = tsbk.is_encrypted
                    vf.encryption_algo = (
                        tsbk.encryption_algo
                    )

                    self._process_frame(vf)
                    time.sleep(0.18)  # ~180ms per LDU

                # Terminator
                tdu = P25Frame()
                tdu.frequency = sys['freq']
                tdu.nac = sys['nac']
                tdu.duid = 0xF
                tdu.duid_name = 'TDULC'
                tdu.talkgroup = tg
                tdu.source_unit = unit
                self._process_frame(tdu)

        thread = threading.Thread(
            target=mock_loop,
            daemon=True,
            name='p25-mock'
        )
        thread.start()

    def _start_output_parser(self):
        """Start thread to parse decoder text output."""
        if not self._decoder_process:
            return

        def parse_loop():
            try:
                for line in iter(
                    self._decoder_process.stdout
                    .readline, ''
                ):
                    if not line or not self._running:
                        break
                    line = line.strip()
                    if line:
                        self._parse_decoder_output(line)
            except Exception as e:
                self._add_log(
                    f"Parser error: {e}", 'error'
                )

        thread = threading.Thread(
            target=parse_loop,
            daemon=True,
            name='p25-parser'
        )
        thread.start()

    def _parse_decoder_output(self, line):
        """
        Parse a line of OP25 or DSD decoder output.

        OP25 outputs JSON on its HTTP interface.
        DSD outputs text descriptions.

        Args:
            line: Output line from decoder
        """
        import re
        frame = P25Frame()
        line_upper = line.upper()

        # Try JSON first (OP25 style)
        if line.startswith('{'):
            try:
                data = json.loads(line)
                frame.nac = int(
                    data.get('nac', 0), 16
                ) if isinstance(
                    data.get('nac'), str
                ) else data.get('nac', 0)
                frame.talkgroup = data.get(
                    'tgid', 0
                )
                frame.source_unit = data.get(
                    'srcaddr', 0
                )
                frame.duid_name = data.get(
                    'duid', ''
                )
                frame.is_voice = (
                    frame.duid_name in ('LDU1', 'LDU2')
                )
                frame.is_tsbk = (
                    frame.duid_name == 'TSBK'
                )
                frame.frequency = (
                    self._channel['frequency']
                )
                if frame.talkgroup or frame.nac:
                    self._process_frame(frame)
                return
            except (json.JSONDecodeError, ValueError):
                pass

        # Parse DSD text output
        nac_m = re.search(
            r'NAC[:\s]([0-9A-Fa-f]+)', line
        )
        if nac_m:
            try:
                frame.nac = int(nac_m.group(1), 16)
            except ValueError:
                pass

        tg_m = re.search(r'TG[:\s](\d+)', line)
        if tg_m:
            frame.talkgroup = int(tg_m.group(1))

        src_m = re.search(r'SRC[:\s](\d+)', line)
        if src_m:
            frame.source_unit = int(src_m.group(1))

        frame.frequency = self._channel['frequency']

        ber_m = re.search(r'BER[:\s]([\d.]+)', line)
        if ber_m:
            frame.ber = float(ber_m.group(1))

        rssi_m = re.search(
            r'RSSI[:\s](-?\d+)', line
        )
        if rssi_m:
            frame.rssi = int(rssi_m.group(1))

        if 'LDU1' in line_upper:
            frame.duid = 0x5
            frame.duid_name = 'LDU1'
            frame.is_voice = True
        elif 'LDU2' in line_upper:
            frame.duid = 0xA
            frame.duid_name = 'LDU2'
            frame.is_voice = True
        elif 'TSBK' in line_upper:
            frame.duid = 0x7
            frame.duid_name = 'TSBK'
            frame.is_tsbk = True
        elif 'TDU' in line_upper:
            frame.duid = 0x3
            frame.duid_name = 'TDU'
        elif 'HDU' in line_upper:
            frame.duid = 0x0
            frame.duid_name = 'HDU'

        if 'ENCR' in line_upper or 'ENCRYPTED' in line_upper:
            frame.is_encrypted = True

        if frame.nac or frame.talkgroup or frame.is_voice:
            self._process_frame(frame)
        else:
            self._add_log(f"OP25: {line[:80]}")

    def _process_frame(self, frame):
        """
        Process a decoded P25 frame.

        Updates statistics, system registry,
        active call, and triggers callbacks.

        Args:
            frame: Decoded P25Frame instance
        """
        self._stats['frames_decoded'] += 1

        if frame.is_voice:
            self._stats['voice_frames'] += 1
        if frame.is_tsbk:
            self._stats['tsbk_frames'] += 1
        if frame.is_data:
            self._stats['data_frames'] += 1

        if frame.rssi is not None:
            self._stats['last_rssi'] = frame.rssi

        if frame.ber is not None:
            cur = self._stats['ber_avg'] or 0.0
            self._stats['ber_avg'] = round(
                0.9 * cur + 0.1 * frame.ber, 3
            )

        if frame.talkgroup:
            self._stats['talkgroups_heard'].add(
                frame.talkgroup
            )

        if frame.source_unit:
            self._stats['units_heard'].add(
                frame.source_unit
            )

        # Update or create system record
        if frame.nac:
            with self._systems_lock:
                if frame.nac not in self._systems:
                    sys = P25System(
                        frame.nac, frame.frequency
                    )
                    self._systems[frame.nac] = sys
                    self._stats['systems_found'] = (
                        len(self._systems)
                    )
                    self._add_log(
                        f"New P25 system found: "
                        f"NAC=0x{frame.nac:03X} "
                        f"@ {frame.frequency:.4f} MHz"
                    )

                self._systems[frame.nac].update(frame)

        # Update active call
        with self._active_call_lock:
            if frame.is_voice and frame.talkgroup:
                self._active_call = frame.to_dict()
                self._scan_state = 'DECODING'
            elif frame.duid_name in ('TDU', 'TDULC'):
                self._active_call = None
                self._scan_state = (
                    'SCANNING' if self._running
                    else 'IDLE'
                )

        # Add to frame history
        with self._frames_lock:
            self._frames.appendleft(frame.to_dict())

    def _start_survey_scanner(self):
        """Start the frequency survey scanner thread."""
        if not self._survey_freqs:
            self._add_log(
                "No survey frequencies configured",
                'warning'
            )
            return

        def scan_loop():
            dwell_ms = self.config.get(
                'dwell_time_ms', 1000
            )
            self._add_log(
                f"Survey scan started: "
                f"{len(self._survey_freqs)} frequencies, "
                f"{dwell_ms}ms dwell"
            )

            while self._running:
                freq = self._survey_freqs[
                    self._survey_index % len(
                        self._survey_freqs
                    )
                ]

                self._channel['frequency'] = freq
                self._add_log(
                    f"Survey: tuning to {freq:.4f} MHz"
                )

                # Dwell at this frequency
                time.sleep(dwell_ms / 1000.0)

                self._survey_index += 1

        self._survey_thread = threading.Thread(
            target=scan_loop,
            daemon=True,
            name='p25-survey-scan'
        )
        self._survey_thread.start()

    def stop_receive(self):
        """Stop all receive processes."""
        self._running = False
        self._scan_state = 'IDLE'

        with self._process_lock:
            for proc in [
                self._decoder_process,
                self._sdr_process
            ]:
                if proc:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass

            self._decoder_process = None
            self._sdr_process = None

        with self._active_call_lock:
            self._active_call = None

        self._add_log("P25 receive stopped")

    # ----------------------------------------------------------
    # Channel control
    # ----------------------------------------------------------

    def set_frequency(self, freq_mhz):
        """Set receive frequency."""
        self._channel['frequency'] = float(freq_mhz)
        self._add_log(
            f"Frequency: {freq_mhz:.4f} MHz"
        )
        if self._running:
            self.stop_receive()
            time.sleep(0.5)
            self.start_receive()

    def set_source(self, source):
        """Switch between SDR and radio source."""
        if source not in ('sdr', 'radio'):
            return
        was_running = self._running
        if was_running:
            self.stop_receive()
        self._source = source
        if was_running:
            self.start_receive()

    def set_nac(self, nac):
        """Set Network Access Code filter."""
        try:
            if isinstance(nac, str):
                self._channel['nac'] = int(nac, 16)
            else:
                self._channel['nac'] = int(nac)
            self._add_log(
                f"NAC filter: "
                f"0x{self._channel['nac']:03X}"
            )
        except ValueError:
            pass

    def set_scan_mode(self, mode):
        """Set scan mode (conventional/survey/trunked)."""
        self._channel['mode'] = mode
        self._add_log(f"Scan mode: {mode}")

    def update_survey_frequencies(self, freq_list):
        """Update the survey frequency list."""
        self._survey_freqs = [
            float(f) for f in freq_list
        ]
        self._survey_index = 0
        self._add_log(
            f"Survey list: "
            f"{len(self._survey_freqs)} frequencies"
        )

    def clear_systems(self):
        """Clear discovered systems."""
        with self._systems_lock:
            self._systems.clear()
        self._stats['systems_found'] = 0
        self._add_log("Systems list cleared")

    # ----------------------------------------------------------
    # Status and data retrieval
    # ----------------------------------------------------------

    def get_status(self):
        """Get comprehensive engine status."""
        with self._active_call_lock:
            active = (
                dict(self._active_call)
                if self._active_call else None
            )

        tgs = self._stats['talkgroups_heard']
        units = self._stats['units_heard']

        return {
            'running': self._running,
            'scan_state': self._scan_state,
            'source': self._source,
            'frequency': self._channel['frequency'],
            'nac': f'0x{self._channel["nac"]:03X}',
            'nac_int': self._channel['nac'],
            'phase': self._channel['phase'],
            'scan_mode': self._channel['mode'],
            'active_call': active,
            'rssi': self._stats.get('last_rssi'),
            'ber_avg': self._stats.get('ber_avg', 0),
            'stats': {
                'frames_decoded': (
                    self._stats['frames_decoded']
                ),
                'voice_frames': (
                    self._stats['voice_frames']
                ),
                'tsbk_frames': (
                    self._stats['tsbk_frames']
                ),
                'data_frames': (
                    self._stats['data_frames']
                ),
                'systems_found': (
                    self._stats['systems_found']
                ),
                'talkgroups_heard': len(tgs),
                'units_heard': len(units),
                'ber_avg': self._stats['ber_avg'],
                'active_since': (
                    self._stats['active_since']
                ),
            },
            'decoder': {
                'name': self._decoder_name or 'None',
                'path': self._decoder_path or '',
                'available': (
                    self._decoder_name is not None
                ),
            },
            'survey_freq_count': len(
                self._survey_freqs
            ),
            'survey_index': self._survey_index,
            'last_update': datetime.utcnow().isoformat(),
        }

    def get_frames(self, limit=50, nac_filter=None):
        """Get recent decoded frames."""
        with self._frames_lock:
            frames = list(self._frames)

        if nac_filter is not None:
            frames = [
                f for f in frames
                if f.get('nac_int') == nac_filter
            ]

        return frames[:limit]

    def get_systems(self):
        """Get all discovered P25 systems."""
        with self._systems_lock:
            return [
                s.to_dict()
                for s in self._systems.values()
            ]

    def get_active_call(self):
        """Get current active call."""
        with self._active_call_lock:
            return (
                dict(self._active_call)
                if self._active_call else None
            )
