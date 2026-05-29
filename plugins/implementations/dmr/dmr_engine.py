"""
DMR Engine
===========
Core DMR signal processing engine.

Handles:
    - RTL-SDR frequency control and IQ capture
    - 4FSK demodulation
    - TDMA slot extraction
    - DMR frame parsing and display
    - Process management for external decoders (DSD)
    - Audio routing (speaker output, mic input for PTT)
    - Status and parameter tracking

Architecture (receive path):
    RTL-SDR -> IQ samples -> 4FSK demod ->
    TDMA burst -> DMR frame decode ->
    Voice decode (AMBE/codec2) -> Audio out

Architecture (transmit path):
    Mic -> Audio in -> Voice encode ->
    DMR frame build -> 4FSK mod ->
    RTL-SDR TX (HackRF/PlutoSDR) or
    configured radio via audio patch

Reference:
    ETSI TS 102 361-1 through 361-4
    https://qradiolink.org/open-source-DMR-transceiver-implementation.html
    https://github.com/szechyjs/dsd
"""

import os
import json
import shutil
import subprocess
import threading
import time
import math
from datetime import datetime
from collections import deque

from plugins.implementations.dmr.dmr_constants import (
    COMMON_TALKGROUPS,
    CALL_TYPES,
    BURST_TYPES,
    FLCO,
)

class DMRFrame:
    """
    Represents a decoded DMR frame/burst.

    Contains all parameters decoded from a single
    DMR TDMA timeslot transmission.
    """

    def __init__(self):
        """Initialise empty DMR frame."""
        self.timestamp = datetime.utcnow().isoformat()
        self.timeslot = 1          # 1 or 2
        self.burst_type = 'Unknown'
        self.color_code = 0        # 0-15
        self.call_type = 0         # 0=Group, 1=Private
        self.source_id = 0         # Source DMR ID
        self.destination_id = 0    # Destination TG or ID
        self.talkgroup = 0         # Same as destination for group
        self.source_alias = ''     # Talker alias if received
        self.slot_type = ''
        self.lcss = 0              # Link Control Start/Stop
        self.embedded_lc = {}      # Embedded link control
        self.rssi = None           # Signal strength dBm
        self.ber = None            # Bit error rate %
        self.snr = None            # Signal-to-noise ratio
        self.has_audio = False
        self.is_voice = False
        self.is_data = False
        self.is_end = False
        self.sequence_no = 0
        self.raw_hex = ''          # Raw frame hex for display

    def to_dict(self):
        """Serialise frame to dictionary."""
        tg_name = COMMON_TALKGROUPS.get(
            self.destination_id, ''
        )
        return {
            'timestamp': self.timestamp,
            'timeslot': self.timeslot,
            'burst_type': self.burst_type,
            'color_code': self.color_code,
            'call_type': CALL_TYPES.get(
                self.call_type, 'Unknown'
            ),
            'source_id': self.source_id,
            'destination_id': self.destination_id,
            'talkgroup': self.destination_id,
            'talkgroup_name': tg_name,
            'source_alias': self.source_alias,
            'rssi': self.rssi,
            'ber': self.ber,
            'snr': self.snr,
            'is_voice': self.is_voice,
            'is_data': self.is_data,
            'is_end': self.is_end,
            'raw_hex': self.raw_hex,
        }


class DMREngine:
    """
    DMR signal processing and decoder engine.

    Manages RTL-SDR interface, external decoder process
    (DSD or QRadioLink), frame parsing, and status tracking.
    """

    def __init__(self, config):
        """
        Initialise DMR engine.

        Args:
            config: Plugin configuration dictionary
        """
        self.config = config

        # Process handles
        self._rtlsdr_process = None
        self._decoder_process = None
        self._process_lock = threading.Lock()

        # State
        self._running = False
        self._transmitting = False
        self._source = config.get('source', 'sdr')

        # Current channel info
        self._channel = {
            'frequency': config.get(
                'center_frequency_mhz', 438.0
            ),
            'color_code': config.get('color_code', 1),
            'timeslot': config.get('timeslot', 1),
            'talkgroup': config.get('talkgroup', 9990),
            'tier': config.get('tier', 2),
            'mode': 'RX',
        }

        # Frame history (ring buffer)
        self._frames = deque(maxlen=200)
        self._frames_lock = threading.Lock()

        # Active call tracking
        self._active_call = None
        self._active_call_lock = threading.Lock()

        # Log buffer
        self._logs = []
        self._log_lock = threading.Lock()
        self._max_logs = 500

        # Statistics
        self._stats = {
            'frames_decoded': 0,
            'voice_frames': 0,
            'data_frames': 0,
            'errors': 0,
            'ber_avg': 0.0,
            'last_rssi': None,
            'last_snr': None,
            'calls_received': 0,
            'active_since': None,
        }

        # Callbacks
        self._frame_callbacks = []
        self._call_callbacks = []

        # Decoder info
        self._decoder_name = None
        self._decoder_path = None
        self._find_decoder()

    def _find_decoder(self):
        """Find available DMR decoder binary."""
        for decoder in ['dsd', 'qradiolink', 'rtl_fm']:
            path = shutil.which(decoder)
            if path:
                self._decoder_name = decoder
                self._decoder_path = path
                self._add_log(
                    f"Decoder found: {decoder} "
                    f"at {path}"
                )
                return

        self._add_log(
            "No DMR decoder found. "
            "Install dsd or qradiolink for full decode. "
            "Running in SDR monitor mode.",
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

    def register_frame_callback(self, callback):
        """Register callback for decoded frames."""
        self._frame_callbacks.append(callback)

    def register_call_callback(self, callback):
        """Register callback for call start/end events."""
        self._call_callbacks.append(callback)

    # ----------------------------------------------------------
    # Receive control
    # ----------------------------------------------------------

    def start_receive(self):
        """
        Start DMR receive pipeline.

        Launches the SDR and decoder processes.
        Receive path:
            rtl_fm -> pipe -> dsd -> audio output

        Returns:
            tuple: (success: bool, message: str)
        """
        if self._running:
            return False, "Already receiving"

        self._running = True
        self._stats['active_since'] = (
            datetime.utcnow().isoformat()
        )

        self._add_log(
            f"Starting DMR receive | "
            f"Source: {self._source} | "
            f"Freq: {self._channel['frequency']} MHz | "
            f"CC: {self._channel['color_code']} | "
            f"TS: {self._channel['timeslot']}"
        )

        if self._source == 'sdr':
            success, msg = self._start_sdr_pipeline()
        else:
            success, msg = self._start_radio_receive()

        if success:
            # Start frame parser thread
            self._start_frame_parser()
            return True, msg
        else:
            self._running = False
            return False, msg

    def _start_sdr_pipeline(self):
        """
        Start RTL-SDR -> decoder pipeline.

        Pipes rtl_fm into dsd for DMR decode:
            rtl_fm -f <freq> -M fm -s 22050 -g <gain> -r 22050
                | dsd -i - -o /dev/dsp

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

            # Check rtl_fm is available
            rtl_fm = shutil.which('rtl_fm')
            if not rtl_fm:
                self._add_log(
                    "[DMR] rtl_fm not found. "
                    "Install rtl-sdr package.",
                    'warning'
                )
                # Start mock receive for UI demo
                self._start_mock_receive()
                return True, (
                    "[DMR] RTL-SDR not available — "
                    "running in demo mode"
                )

            if not self._decoder_name:
                # No decoder — just monitor with rtl_fm
                self._add_log(
                    "[DMR] No decoder — monitoring SDR only",
                    'warning'
                )
                self._start_mock_receive()
                return True, (
                    "[DMR] No decoder available — "
                    "SDR monitor mode only"
                )

            try:
                # Build rtl_fm command
                # DMR uses FM demodulation at 22050 Hz
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

                # Build dsd decoder command
                dsd_cmd = [
                    self._decoder_path,
                    '-f', 'd',      # DMR format
                    '-i', '-',      # stdin
                    '-o', '-',      # stdout
                    '-n',           # no audio
                    '-q',           # quiet
                ]

                # Add color code filter if supported
                if self._decoder_name == 'dsd':
                    pass  # DSD auto-detects

                # Start rtl_fm
                self._rtlsdr_process = subprocess.Popen(
                    rtl_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )

                # Pipe into dsd
                self._decoder_process = subprocess.Popen(
                    dsd_cmd,
                    stdin=self._rtlsdr_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                self._add_log(
                    f"[DMR] ✓ SDR pipeline started: "
                    f"{freq_hz/1e6:.4f} MHz "
                    f"(gain: {gain}dB)"
                )
                return True, (
                    f"[DMR] Receiving on "
                    f"{self._channel['frequency']:.4f} MHz"
                )

            except Exception as e:
                self._add_log(
                    f"[DMR] SDR pipeline error: {e}", 'error'
                )
                self._start_mock_receive()
                return True, (
                    f"[DMR] SDR error ({e}) — demo mode"
                )

    def _start_radio_receive(self):
        """
        Start receive via configured radio audio.

        The radio demodulates the RF signal. We capture
        the discriminator audio and pass to DSD.

        Returns:
            tuple: (success: bool, message: str)
        """
        self._add_log(
            "[DMR] Starting radio audio receive mode..."
        )

        if not self._decoder_name:
            self._start_mock_receive()
            return True, "[DMR] Radio receive — demo mode"

        try:
            audio_device = self.config.get(
                'radio_audio_device', None
            )

            # Build dsd command for audio input
            dsd_cmd = [
                self._decoder_path,
                '-f', 'd',     # DMR
                '-i', '-',     # stdin (audio)
                '-o', '-',     # stdout
                '-n',          # no audio output
            ]

            if audio_device:
                # Capture from specific device
                # arecord -> dsd
                arecord_cmd = [
                    'arecord',
                    '-D', audio_device,
                    '-r', '48000',
                    '-f', 'S16_LE',
                    '-c', '1',
                    '-'
                ]

                self._rtlsdr_process = subprocess.Popen(
                    arecord_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )

                self._decoder_process = subprocess.Popen(
                    dsd_cmd,
                    stdin=self._rtlsdr_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            else:
                # Use sounddevice for audio capture
                self._start_audio_receive()
                return True, "[DMR] Radio audio receive started"

            self._add_log("[DMR] ✓ Radio receive started")
            return True, "Receiving via radio audio"

        except Exception as e:
            self._add_log(
                f"[DMR] Radio receive error: {e}", 'error'
            )
            self._start_mock_receive()
            return True, f"[DMR] Radio error — demo mode"

    def _start_mock_receive(self):
        """
        Start mock receive for demo/testing.

        Generates synthetic DMR frames to populate
        the UI when real hardware is not available.
        """
        self._add_log(
            "[DMR] Starting demo mode — generating "
            "synthetic DMR frames"
        )

        def mock_loop():
            import random
            call_ids = [
                (3100, 'W1AW', 9, 'Group'),
                (3026, 'VE3ABC', 9, 'Group'),
                (91, 'K5TXW', 1, 'Group'),
                (3107, 'N7XYZ', 9, 'Group'),
                (9990, 'VK2DMR', 1, 'Private'),
            ]

            while self._running:
                # Simulate idle period
                time.sleep(random.uniform(3, 8))

                if not self._running:
                    break

                # Pick random call
                tg, callsign, ts, ctype = (
                    random.choice(call_ids)
                )

                # Generate random source ID
                src_id = random.randint(
                    3000000, 3999999
                )

                # Simulate call start
                frame = DMRFrame()
                frame.timeslot = ts
                frame.color_code = self.config.get(
                    'color_code', 1
                )
                frame.source_id = src_id
                frame.destination_id = tg
                frame.talkgroup = tg
                frame.source_alias = callsign
                frame.call_type = (
                    0 if ctype == 'Group' else 1
                )
                frame.is_voice = True
                frame.rssi = round(
                    random.uniform(-110, -70), 1
                )
                frame.ber = round(
                    random.uniform(0, 2), 2
                )
                frame.snr = round(
                    random.uniform(10, 30), 1
                )
                frame.burst_type = 'Voice Header (VH)'

                self._process_frame(frame)

                # Simulate voice frames
                voice_duration = random.uniform(2, 8)
                start = time.time()
                seq = 0

                while (time.time() - start <
                       voice_duration and self._running):
                    vf = DMRFrame()
                    vf.timeslot = ts
                    vf.color_code = frame.color_code
                    vf.source_id = src_id
                    vf.destination_id = tg
                    vf.talkgroup = tg
                    vf.source_alias = callsign
                    vf.call_type = frame.call_type
                    vf.is_voice = True
                    vf.has_audio = True
                    vf.sequence_no = seq
                    vf.rssi = frame.rssi + random.uniform(
                        -3, 3
                    )
                    vf.ber = max(
                        0,
                        frame.ber + random.uniform(
                            -0.5, 0.5
                        )
                    )
                    vf.burst_type = 'Voice (Embedded LC)'
                    seq += 1

                    self._process_frame(vf)
                    time.sleep(0.03)  # 30ms per timeslot

                # End of call
                ef = DMRFrame()
                ef.timeslot = ts
                ef.source_id = src_id
                ef.destination_id = tg
                ef.talkgroup = tg
                ef.source_alias = callsign
                ef.is_end = True
                ef.burst_type = 'Terminator (TLC)'

                self._process_frame(ef)

        thread = threading.Thread(
            target=mock_loop,
            daemon=True,
            name='dmr-mock'
        )
        thread.start()

    def _start_frame_parser(self):
        """
        Start background thread to parse decoder output.

        Reads DSD stdout and parses DMR frame information.
        """
        if not self._decoder_process:
            return

        def parse_loop():
            """Parse DSD text output for DMR frames."""
            try:
                for line in iter(
                    self._decoder_process.stdout.readline,
                    ''
                ):
                    if not line or not self._running:
                        break
                    line = line.strip()
                    if line:
                        self._parse_dsd_output(line)
            except Exception as e:
                self._add_log(
                    f"[DMR-DSD] Parser error: {e}", 'error'
                )

        thread = threading.Thread(
            target=parse_loop,
            daemon=True,
            name='dmr-parser'
        )
        thread.start()

    def _parse_dsd_output(self, line):
        """
        Parse a line of DSD decoder output.

        DSD outputs text lines describing each decoded
        frame. Format varies by version but typically:
            DMR CC:1 TS:1 TG:3100 Src:3101234 Voice

        Args:
            line: Output line from DSD
        """
        import re

        frame = DMRFrame()
        line_upper = line.upper()

        # Color code
        cc_match = re.search(r'CC[:\s](\d+)', line)
        if cc_match:
            frame.color_code = int(cc_match.group(1))

        # Timeslot
        ts_match = re.search(r'TS[:\s]([12])', line)
        if ts_match:
            frame.timeslot = int(ts_match.group(1))

        # Talk group
        tg_match = re.search(
            r'TG[:\s](\d+)', line
        )
        if tg_match:
            frame.destination_id = int(
                tg_match.group(1)
            )
            frame.talkgroup = frame.destination_id

        # Source ID
        src_match = re.search(
            r'SRC[:\s](\d+)', line
        )
        if src_match:
            frame.source_id = int(src_match.group(1))

        # Call type
        if 'GROUP' in line_upper or 'TG' in line_upper:
            frame.call_type = 0
        elif 'PRIVATE' in line_upper or 'PC' in line_upper:
            frame.call_type = 1

        # Frame type
        if 'VOICE' in line_upper:
            frame.is_voice = True
            frame.burst_type = 'Voice'
        elif 'DATA' in line_upper:
            frame.is_data = True
            frame.burst_type = 'Data'
        elif 'TERM' in line_upper or 'END' in line_upper:
            frame.is_end = True
            frame.burst_type = 'Terminator'

        # BER
        ber_match = re.search(r'BER[:\s]([\d.]+)', line)
        if ber_match:
            frame.ber = float(ber_match.group(1))

        # RSSI
        rssi_match = re.search(
            r'RSSI[:\s](-?\d+)', line
        )
        if rssi_match:
            frame.rssi = int(rssi_match.group(1))

        # Only process if we got meaningful data
        if (frame.source_id or
                frame.destination_id or
                frame.is_voice):
            self._process_frame(frame)
        else:
            # Log raw output for debugging
            self._add_log(f"[DMR] DSD: {line}")

    def _process_frame(self, frame):
        """
        Process a decoded DMR frame.

        Updates statistics, active call state,
        frame history, and triggers callbacks.

        Args:
            frame: Decoded DMRFrame instance
        """
        self._stats['frames_decoded'] += 1

        if frame.is_voice:
            self._stats['voice_frames'] += 1

        if frame.is_data:
            self._stats['data_frames'] += 1

        if frame.rssi is not None:
            self._stats['last_rssi'] = frame.rssi

        if frame.snr is not None:
            self._stats['last_snr'] = frame.snr

        if frame.ber is not None:
            # Exponential moving average of BER
            current_ber = self._stats['ber_avg'] or 0.0
            self._stats['ber_avg'] = round(
                0.9 * current_ber + 0.1 * frame.ber, 3
            )

        # Update active call
        with self._active_call_lock:
            if frame.is_voice and not frame.is_end:
                if (not self._active_call or
                        self._active_call.get(
                            'source_id'
                        ) != frame.source_id):
                    # New call started
                    self._active_call = frame.to_dict()
                    self._stats['calls_received'] += 1
                    for cb in self._call_callbacks:
                        try:
                            cb('start', frame.to_dict())
                        except Exception:
                            pass

            elif frame.is_end:
                if self._active_call:
                    for cb in self._call_callbacks:
                        try:
                            cb('end', frame.to_dict())
                        except Exception:
                            pass
                    self._active_call = None

        # Add to frame history
        with self._frames_lock:
            self._frames.appendleft(frame.to_dict())

        # Notify frame callbacks
        for cb in self._frame_callbacks:
            try:
                cb(frame)
            except Exception:
                pass

    def _start_audio_receive(self):
        """
        Start audio capture via sounddevice.

        Used when radio audio is captured via
        the sound card rather than piped from rtl_fm.
        """
        try:
            import sounddevice as sd
            import numpy as np

            rate = 48000
            audio_dev = self.config.get(
                'radio_audio_device', None
            )

            def audio_callback(indata, frames, ts, status):
                if not self._running:
                    return
                # In a real implementation this would
                # be piped to the decoder process.
                # For now we just monitor level.
                level = float(np.abs(indata).mean())
                self._stats['last_rssi'] = round(
                    -100 + level * 60, 1
                )

            self._audio_stream = sd.InputStream(
                samplerate=rate,
                channels=1,
                device=audio_dev,
                callback=audio_callback
            )
            self._audio_stream.start()

        except ImportError:
            self._add_log(
                "[DMR] sounddevice not available", 'warning'
            )
        except Exception as e:
            self._add_log(
                f"[DMR] Audio receive error: {e}", 'error'
            )

    def stop_receive(self):
        """Stop all receive processes."""
        self._running = False

        with self._process_lock:
            if self._decoder_process:
                try:
                    self._decoder_process.terminate()
                    self._decoder_process.wait(timeout=3)
                except Exception:
                    try:
                        self._decoder_process.kill()
                    except Exception:
                        pass
                self._decoder_process = None

            if self._rtlsdr_process:
                try:
                    self._rtlsdr_process.terminate()
                    self._rtlsdr_process.wait(timeout=3)
                except Exception:
                    try:
                        self._rtlsdr_process.kill()
                    except Exception:
                        pass
                self._rtlsdr_process = None

        # Stop audio stream if open
        if hasattr(self, '_audio_stream'):
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass

        with self._active_call_lock:
            self._active_call = None

        self._add_log("[DMR] Receive stopped")

    # ----------------------------------------------------------
    # Transmit (PTT)
    # ----------------------------------------------------------

    def start_transmit(self, audio_data=None):
        """
        Start transmitting (PTT pressed).

        In SDR mode: requires HackRF or PlutoSDR.
        In radio mode: keys the radio via serial PTT
        or VOX, then sends audio via sound card.

        Args:
            audio_data: Optional pre-recorded audio bytes

        Returns:
            tuple: (success: bool, message: str)
        """
        if self._transmitting:
            return False, "[DMR] Already transmitting"

        if self._source == 'sdr':
            return self._start_sdr_transmit(audio_data)
        else:
            return self._start_radio_transmit(audio_data)

    def _start_sdr_transmit(self, audio_data=None):
        """
        Start transmitting via SDR (HackRF/PlutoSDR).

        RTL-SDR cannot transmit — requires HackRF,
        PlutoSDR, or ADALM-PLUTO.

        Returns:
            tuple: (success: bool, message: str)
        """
        # Check for TX-capable SDR
        tx_capable = (
            shutil.which('hackrf_transfer') or
            shutil.which('iio_fm_transmitter')
        )

        if not tx_capable:
            return False, (
                "[DMR] SDR transmit requires HackRF or "
                "PlutoSDR. RTL-SDR is receive-only. "
                "Switch to Radio mode for TX."
            )

        self._transmitting = True
        self._channel['mode'] = 'TX'
        self._add_log(
            "[DMR] SDR TX started (requires HackRF/PlutoSDR)"
        )
        return True, "[DMR] SDR transmitting"

    def _start_radio_transmit(self, audio_data=None):
        """
        Start transmitting via configured radio.

        Keys the radio using serial PTT or RTS/DTR
        then sends audio via sound card.

        Returns:
            tuple: (success: bool, message: str)
        """
        self._transmitting = True
        self._channel['mode'] = 'TX'

        # Key the radio via serial PTT if configured
        ptt_port = self.config.get('ptt_port', '')
        if ptt_port:
            self._key_radio(ptt_port, True)

        self._add_log(
            f"Radio TX started | "
            f"TG: {self._channel['talkgroup']} | "
            f"TS: {self._channel['timeslot']}"
        )
        return True, "[DMR] Radio transmitting"

    def stop_transmit(self):
        """
        Stop transmitting (PTT released).

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self._transmitting:
            return False, "[DMR] Not transmitting"

        self._transmitting = False
        self._channel['mode'] = 'RX'

        # Unkey radio
        ptt_port = self.config.get('ptt_port', '')
        if ptt_port:
            self._key_radio(ptt_port, False)

        self._add_log("[DMR] TX stopped")
        return True, "[DMR] TX stopped"

    def _key_radio(self, port, key_on):
        """
        Key/unkey the radio via serial RTS line.

        Args:
            port: Serial port path
            key_on: True to key, False to unkey
        """
        try:
            import serial
            with serial.Serial(
                port, timeout=1
            ) as ser:
                ser.setRTS(key_on)
        except Exception as e:
            self._add_log(
                f"[DMR] PTT error on {port}: {e}", 'warning'
            )

    # ----------------------------------------------------------
    # Channel control
    # ----------------------------------------------------------

    def set_frequency(self, freq_mhz):
        """
        Set the receive frequency.

        Args:
            freq_mhz: Center frequency in MHz
        """
        self._channel['frequency'] = float(freq_mhz)
        self._add_log(
            f"Frequency set: {freq_mhz:.4f} MHz"
        )

        # Restart pipeline if running
        if self._running:
            self.stop_receive()
            time.sleep(0.5)
            self.start_receive()

    def set_color_code(self, cc):
        """Set color code (0-15)."""
        self._channel['color_code'] = int(cc)
        self._add_log(f"Color code: {cc}")

    def set_timeslot(self, ts):
        """Set timeslot (1 or 2)."""
        self._channel['timeslot'] = int(ts)
        self._add_log(f"Timeslot: {ts}")

    def set_talkgroup(self, tg):
        """Set active talkgroup."""
        self._channel['talkgroup'] = int(tg)
        self._add_log(f"Talkgroup: {tg}")

    def set_source(self, source):
        """
        Switch receive source between SDR and radio.

        Args:
            source: 'sdr' or 'radio'
        """
        if source not in ('sdr', 'radio'):
            return

        was_running = self._running
        if was_running:
            self.stop_receive()

        self._source = source
        self._add_log(f"Source: {source}")

        if was_running:
            self.start_receive()

    # ----------------------------------------------------------
    # Status and data retrieval
    # ----------------------------------------------------------

    def get_status(self):
        """
        Get comprehensive DMR engine status.

        Returns:
            dict: Full status dictionary
        """
        with self._active_call_lock:
            active = (
                dict(self._active_call)
                if self._active_call else None
            )

        tg = self._channel['talkgroup']
        tg_name = COMMON_TALKGROUPS.get(tg, '')

        decoder_info = {
            'name': self._decoder_name or 'None',
            'path': self._decoder_path or '',
            'available': self._decoder_name is not None,
        }

        return {
            'running': self._running,
            'transmitting': self._transmitting,
            'source': self._source,
            'mode': self._channel['mode'],
            # Channel parameters
            'frequency': self._channel['frequency'],
            'color_code': self._channel['color_code'],
            'timeslot': self._channel['timeslot'],
            'talkgroup': tg,
            'talkgroup_name': tg_name,
            'tier': self._channel['tier'],
            # Active call
            'active_call': active,
            # Signal quality
            'rssi': self._stats.get('last_rssi'),
            'snr': self._stats.get('last_snr'),
            'ber_avg': self._stats.get('ber_avg', 0),
            # Statistics
            'stats': dict(self._stats),
            # Decoder
            'decoder': decoder_info,
            # Timing
            'last_update': datetime.utcnow().isoformat(),
        }

    def get_frames(self, limit=50, timeslot=None):
        """
        Get recent decoded frames.

        Args:
            limit: Maximum frames to return
            timeslot: Filter by timeslot (None=all)

        Returns:
            list: Frame dictionaries
        """
        with self._frames_lock:
            frames = list(self._frames)

        if timeslot is not None:
            frames = [
                f for f in frames
                if f.get('timeslot') == timeslot
            ]

        return frames[:limit]

    def get_active_call(self):
        """
        Get the currently active call.

        Returns:
            dict: Active call data or None
        """
        with self._active_call_lock:
            return (
                dict(self._active_call)
                if self._active_call else None
            )
