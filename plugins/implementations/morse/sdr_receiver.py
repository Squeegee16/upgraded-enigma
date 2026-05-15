"""
SDR Morse Receiver
==================
Receives and decodes CW (morse code) from an RTL-SDR
or the configured radio (via audio interface).

RTL-SDR Dependency Handling:
    pyrtlsdr is an optional dependency. If it is not
    installed or the hardware is not present, the
    receiver automatically falls back to:
        1. Mock receive mode (demo/testing)
        2. Audio input mode (radio mode)

    To install pyrtlsdr:
        pip install pyrtlsdr
        # Also requires librtlsdr system library:
        # apt-get install librtlsdr-dev  (Debian/Ubuntu)
        # yum install rtl-sdr-devel      (Fedora/RHEL)

    Docker:
        Add to requirements.txt: pyrtlsdr
        Ensure /dev/bus/usb is passed through in
        docker-compose.yml with privileged: true

Architecture:
    RTL-SDR mode:
        RTL-SDR -> IQ samples -> AM demodulate ->
        Goertzel tone detect -> MorseEngine decode

    Radio mode:
        Radio audio output -> sound card ->
        sounddevice capture -> Goertzel tone detect ->
        MorseEngine decode

    Mock mode:
        Synthetic CW signal -> MorseEngine decode
        Used when no hardware is available.
"""

import threading
import time
import math
from datetime import datetime

# ---------------------------------------------------------------
# Check for optional dependencies at module load time.
# This prevents import errors from crashing the plugin.
# ---------------------------------------------------------------

# pyrtlsdr (RTL-SDR Python bindings)
try:
    import rtlsdr as _rtlsdr_module
    RTLSDR_AVAILABLE = True
except ImportError:
    RTLSDR_AVAILABLE = False
    _rtlsdr_module = None
    print(
        "[Morse-SDR] pyrtlsdr not installed. "
        "RTL-SDR receive unavailable. "
        "Install: pip install pyrtlsdr"
    )

# numpy (signal processing)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None
    print(
        "[Morse-SDR] numpy not installed. "
        "Install: pip install numpy"
    )

# sounddevice (audio capture for radio mode)
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    sd = None


class SDRMorseReceiver:
    """
    Background SDR/audio receiver for CW decode.

    Manages the receive thread and coordinates between
    the SDR/audio source and the MorseEngine decoder.

    Source selection:
        'sdr'   - RTL-SDR hardware (requires pyrtlsdr)
        'radio' - Radio audio input (requires sounddevice)
        'mock'  - Simulated CW signal (always available)

    Automatic fallback chain:
        sdr -> (if RTL-SDR fails) -> mock
        radio -> (if sounddevice fails) -> mock
    """

    def __init__(self, morse_engine, config):
        """
        Initialise the SDR receiver.

        Args:
            morse_engine: MorseEngine instance for decode
            config: Configuration dictionary
        """
        self.engine = morse_engine
        self.config = config

        # State
        self._running = False
        self._thread = None
        self._source = config.get('source', 'sdr')

        # SDR settings
        self._center_freq = config.get(
            'center_frequency_mhz', 7.030
        ) * 1e6  # Convert to Hz
        self._sample_rate = 250000
        self._sdr_device = None

        # Audio settings (radio mode)
        self._audio_device = config.get(
            'audio_input_device', None
        )
        self._audio_sample_rate = 44100

        # Status
        self._status = {
            'running': False,
            'source': self._source,
            'frequency': config.get(
                'center_frequency_mhz', 7.030
            ),
            'signal_level': 0.0,
            'tone_detected': False,
            'error': None,
            'samples_processed': 0,
            'rtlsdr_available': RTLSDR_AVAILABLE,
            'numpy_available': NUMPY_AVAILABLE,
            'sounddevice_available': SOUNDDEVICE_AVAILABLE,
            'fallback_reason': None,
        }

        # Signal level history
        self._signal_history = []
        self._signal_lock = threading.Lock()

        # Log the dependency status on init
        self._log_dependency_status()

    def _log_dependency_status(self):
        """
        Log the status of optional dependencies.
        Provides clear guidance if anything is missing.
        """
        print(
            f"[Morse-SDR] Dependency status:\n"
            f"  pyrtlsdr:    "
            f"{'✓ Available' if RTLSDR_AVAILABLE else '✗ Not installed'}\n"
            f"  numpy:       "
            f"{'✓ Available' if NUMPY_AVAILABLE else '✗ Not installed'}\n"
            f"  sounddevice: "
            f"{'✓ Available' if SOUNDDEVICE_AVAILABLE else '✗ Not installed'}"
        )

        if not RTLSDR_AVAILABLE:
            print(
                "[Morse-SDR] To enable RTL-SDR receive:\n"
                "  1. Install library: "
                "apt-get install librtlsdr-dev\n"
                "  2. Install Python: pip install pyrtlsdr\n"
                "  3. In Docker: add pyrtlsdr to "
                "requirements.txt and rebuild\n"
                "  4. Ensure /dev/bus/usb is passed "
                "through in docker-compose.yml"
            )

    def set_frequency(self, freq_mhz):
        """
        Set the receive center frequency.

        Args:
            freq_mhz: Center frequency in MHz
        """
        self._center_freq = float(freq_mhz) * 1e6
        self._status['frequency'] = float(freq_mhz)

        # Update SDR if running
        if self._sdr_device is not None:
            try:
                self._sdr_device.center_freq = (
                    int(self._center_freq)
                )
                print(
                    f"[Morse-SDR] Frequency updated: "
                    f"{freq_mhz:.4f} MHz"
                )
            except Exception as e:
                print(
                    f"[Morse-SDR] Frequency update error: "
                    f"{e}"
                )

    def set_source(self, source):
        """
        Switch between SDR and radio audio input.

        If the requested source is unavailable (e.g.
        RTL-SDR not installed), falls back to mock mode.

        Args:
            source: 'sdr', 'radio', or 'mock'
        """
        if source not in ('sdr', 'radio', 'mock'):
            return

        was_running = self._running
        if was_running:
            self.stop()

        self._source = source
        self._status['source'] = source
        self._status['fallback_reason'] = None

        if was_running:
            self.start()

    def start(self):
        """
        Start the receive thread.

        Selects the best available receive method:
            - If source='sdr' and RTL-SDR available: SDR
            - If source='sdr' and no RTL-SDR: mock
            - If source='radio' and sounddevice available: audio
            - If source='radio' and no sounddevice: mock
            - If source='mock': mock always

        Returns:
            tuple: (success: bool, message: str)
        """
        if self._running:
            return False, "Already running"

        self._running = True
        self._status['running'] = True
        self._status['error'] = None

        # Determine actual receive method
        if self._source == 'sdr':
            if RTLSDR_AVAILABLE and NUMPY_AVAILABLE:
                target = self._sdr_receive_loop
                method = 'RTL-SDR'
            else:
                # Fall back to mock
                reason = []
                if not RTLSDR_AVAILABLE:
                    reason.append('pyrtlsdr not installed')
                if not NUMPY_AVAILABLE:
                    reason.append('numpy not installed')
                fallback_msg = ', '.join(reason)

                print(
                    f"[Morse-SDR] SDR fallback to mock: "
                    f"{fallback_msg}"
                )
                self._status['fallback_reason'] = fallback_msg
                self._status['error'] = (
                    f"RTL-SDR unavailable ({fallback_msg}). "
                    f"Running in demo mode. "
                    f"Install: pip install pyrtlsdr numpy"
                )
                target = self._mock_receive_loop
                method = 'Mock (RTL-SDR unavailable)'

        elif self._source == 'radio':
            if SOUNDDEVICE_AVAILABLE:
                target = self._audio_receive_loop
                method = 'Radio audio'
            else:
                print(
                    "[Morse-SDR] sounddevice not available,"
                    " falling back to mock"
                )
                self._status['fallback_reason'] = (
                    'sounddevice not installed'
                )
                target = self._mock_receive_loop
                method = 'Mock (sounddevice unavailable)'

        else:
            # Explicit mock mode
            target = self._mock_receive_loop
            method = 'Mock'

        print(f"[Morse-SDR] Starting receiver: {method}")

        self._thread = threading.Thread(
            target=target,
            daemon=True,
            name='morse-receiver'
        )
        self._thread.start()

        return True, f"Receiver started ({method})"

    def stop(self):
        """Stop the receive thread."""
        self._running = False
        self._status['running'] = False
        self._status['tone_detected'] = False

        # Close RTL-SDR device
        if self._sdr_device is not None:
            try:
                self._sdr_device.close()
            except Exception:
                pass
            self._sdr_device = None

        # Wait for thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

        print("[Morse-SDR] Receiver stopped")

    def get_status(self):
        """
        Get current receiver status.

        Returns:
            dict: Status including fallback information
        """
        return dict(self._status)

    def get_signal_level(self):
        """
        Get current signal level (0.0 to 1.0).

        Returns:
            float: Signal level
        """
        return self._status.get('signal_level', 0.0)

    # ----------------------------------------------------------
    # RTL-SDR receive loop
    # ----------------------------------------------------------

    def _sdr_receive_loop(self):
        """
        RTL-SDR receive and CW decode loop.

        Reads IQ samples from RTL-SDR, demodulates AM,
        applies Goertzel tone detection, and sends
        tone events to the MorseEngine.

        Falls back to mock mode if RTL-SDR cannot be
        opened (e.g. device not plugged in, permission
        error, or device in use by another app).
        """
        # Double-check that pyrtlsdr is available
        # (may have been imported but device may fail)
        if not RTLSDR_AVAILABLE:
            print(
                "[Morse-SDR] pyrtlsdr not available, "
                "using mock mode"
            )
            self._mock_receive_loop()
            return

        if not NUMPY_AVAILABLE:
            print(
                "[Morse-SDR] numpy not available, "
                "using mock mode"
            )
            self._mock_receive_loop()
            return

        try:
            # Try to open the RTL-SDR device
            device_index = self.config.get(
                'sdr_device_index', 0
            )

            print(
                f"[Morse-SDR] Opening RTL-SDR device "
                f"{device_index}..."
            )

            try:
                sdr = _rtlsdr_module.RtlSdr(
                    device_index=device_index
                )
            except Exception as e:
                error_msg = str(e)
                print(
                    f"[Morse-SDR] RTL-SDR open failed: "
                    f"{error_msg}"
                )

                # Provide helpful error messages
                if 'no supported' in error_msg.lower() or \
                        'device' in error_msg.lower():
                    self._status['error'] = (
                        "RTL-SDR device not found. "
                        "Check USB connection and "
                        "docker-compose.yml devices section."
                    )
                elif 'permission' in error_msg.lower():
                    self._status['error'] = (
                        "Permission denied for RTL-SDR. "
                        "Add user to plugdev group or "
                        "run with privileged: true in "
                        "docker-compose.yml"
                    )
                elif 'busy' in error_msg.lower() or \
                        'use' in error_msg.lower():
                    self._status['error'] = (
                        "RTL-SDR device is in use by "
                        "another application. "
                        "Close other SDR programs first."
                    )
                else:
                    self._status['error'] = (
                        f"RTL-SDR error: {error_msg[:100]}"
                    )

                print(
                    "[Morse-SDR] Falling back to mock mode"
                )
                self._mock_receive_loop()
                return

            # Configure SDR
            try:
                sdr.center_freq = int(self._center_freq)
                sdr.sample_rate = self._sample_rate
                sdr.gain = self.config.get(
                    'sdr_gain', 30
                )
                self._sdr_device = sdr
                print(
                    f"[Morse-SDR] RTL-SDR configured: "
                    f"{self._center_freq/1e6:.4f} MHz, "
                    f"{self._sample_rate/1e3:.0f} kHz"
                )
            except Exception as e:
                print(
                    f"[Morse-SDR] SDR config error: {e}"
                )
                try:
                    sdr.close()
                except Exception:
                    pass
                self._mock_receive_loop()
                return

            # --------------------------------------------------
            # Main receive loop
            # --------------------------------------------------
            block_size = 16384
            prev_tone = False
            silence_start = None
            tone_freq = self.config.get('tone_hz', 700)
            threshold = self.config.get(
                'tone_detection_threshold', 0.01
            )

            print("[Morse-SDR] RTL-SDR receive loop started")

            while self._running:
                try:
                    # Read IQ samples
                    samples = sdr.read_samples(block_size)

                    if not NUMPY_AVAILABLE:
                        time.sleep(0.1)
                        continue

                    # AM demodulate: magnitude of IQ
                    magnitude = np.abs(samples)

                    # Normalise to 0-1
                    max_val = magnitude.max()
                    if max_val > 0:
                        magnitude = magnitude / max_val

                    # Decimate to audio rate (~8 kHz)
                    audio_rate = 8000
                    decimate = max(
                        1, self._sample_rate // audio_rate
                    )
                    audio = magnitude[::decimate]

                    # Detect morse tone
                    tone_detected = (
                        self.engine.detect_tone_in_samples(
                            audio, audio_rate,
                            threshold=threshold
                        )
                    )

                    # Update status
                    level = float(np.mean(magnitude))
                    self._status['signal_level'] = level
                    self._status['tone_detected'] = (
                        tone_detected
                    )
                    self._status['samples_processed'] += (
                        block_size
                    )

                    # Send tone events to engine
                    ts = time.time() * 1000
                    if tone_detected != prev_tone:
                        self.engine.process_tone_event(
                            tone_detected, ts
                        )
                        prev_tone = tone_detected
                        if not tone_detected:
                            silence_start = ts
                    elif not tone_detected and \
                            silence_start is not None:
                        silence_ms = ts - silence_start
                        self.engine.process_silence(
                            silence_ms
                        )

                except Exception as e:
                    print(
                        f"[Morse-SDR] Receive error: {e}"
                    )
                    time.sleep(0.1)

        except Exception as e:
            print(
                f"[Morse-SDR] SDR loop fatal error: {e}"
            )
            self._status['error'] = str(e)

        finally:
            # Always clean up the SDR device
            if self._sdr_device is not None:
                try:
                    self._sdr_device.close()
                except Exception:
                    pass
                self._sdr_device = None

            print("[Morse-SDR] RTL-SDR loop ended")

    # ----------------------------------------------------------
    # Audio receive loop (radio mode)
    # ----------------------------------------------------------

    def _audio_receive_loop(self):
        """
        Audio capture receive loop for radio mode.

        Captures audio from the configured sound card
        input device and detects the CW tone.

        Falls back to mock mode if sounddevice fails.
        """
        if not SOUNDDEVICE_AVAILABLE:
            print(
                "[Morse-SDR] sounddevice not available, "
                "using mock mode"
            )
            self._mock_receive_loop()
            return

        rate = self._audio_sample_rate
        block_ms = 50
        block_samples = int(rate * block_ms / 1000)
        tone_freq = self.config.get('tone_hz', 700)
        threshold = self.config.get(
            'tone_detection_threshold', 0.005
        )

        prev_tone = False
        silence_start = None

        print(
            f"[Morse-SDR] Starting audio capture "
            f"(device: "
            f"{self._audio_device or 'default'})"
        )

        def audio_callback(indata, frames, ts, status):
            """Sounddevice callback — called per block."""
            if not self._running:
                return

            nonlocal prev_tone, silence_start

            if NUMPY_AVAILABLE:
                samples = indata[:, 0]
            else:
                # Without numpy, use basic level detection
                samples = list(indata[:, 0])

            tone_detected = (
                self.engine.detect_tone_in_samples(
                    samples, rate,
                    threshold=threshold
                )
            )

            if NUMPY_AVAILABLE:
                import numpy as numpy_local
                level = float(
                    numpy_local.abs(samples).mean()
                )
            else:
                level = sum(
                    abs(s) for s in samples
                ) / len(samples)

            self._status['signal_level'] = level
            self._status['tone_detected'] = tone_detected

            event_ts = time.time() * 1000

            if tone_detected != prev_tone:
                self.engine.process_tone_event(
                    tone_detected, event_ts
                )
                prev_tone = tone_detected
                if not tone_detected:
                    silence_start = event_ts
            elif not tone_detected and \
                    silence_start is not None:
                silence_ms = event_ts - silence_start
                self.engine.process_silence(silence_ms)

        try:
            with sd.InputStream(
                samplerate=rate,
                channels=1,
                blocksize=block_samples,
                device=self._audio_device,
                callback=audio_callback
            ):
                print(
                    "[Morse-SDR] Audio stream opened"
                )
                while self._running:
                    time.sleep(0.1)

        except Exception as e:
            error_msg = str(e)
            print(
                f"[Morse-SDR] Audio error: {error_msg}"
            )
            self._status['error'] = (
                f"Audio input error: {error_msg[:100]}"
            )
            print(
                "[Morse-SDR] Falling back to mock mode"
            )
            self._mock_receive_loop()

    # ----------------------------------------------------------
    # Mock receive loop (always available)
    # ----------------------------------------------------------

    def _mock_receive_loop(self):
        """
        Mock receive loop for testing without hardware.

        Generates a synthetic CW signal spelling out
        a test message repeatedly. This ensures the
        plugin remains functional even when:
            - RTL-SDR hardware is not connected
            - pyrtlsdr is not installed
            - sounddevice is not available

        The message cycles through common ham radio
        CW exchanges at the configured WPM.
        """
        import random

        messages = [
            "DE W1AW K",
            "CQ CQ CQ DE VE3ABC K",
            "RST 599 73",
            "QTH OTTAWA ON",
        ]

        print(
            "[Morse-SDR] Mock CW receive started "
            "(no real hardware)"
        )

        msg_index = 0

        while self._running:
            message = messages[
                msg_index % len(messages)
            ]
            msg_index += 1

            # Get timing from morse engine
            timing = self.engine.text_to_timing(message)

            for event in timing:
                if not self._running:
                    return

                event_type = event.get('type', '')
                duration_s = event.get(
                    'duration_ms', 60
                ) / 1000.0

                # Simulate tone on/off
                tone_on = (event_type == 'tone_on')

                if event_type in ('tone_on', 'tone_off'):
                    ts = time.time() * 1000
                    self.engine.process_tone_event(
                        tone_on, ts
                    )

                    # Update status
                    self._status['tone_detected'] = tone_on
                    self._status['signal_level'] = (
                        random.uniform(0.6, 0.9)
                        if tone_on else
                        random.uniform(0.0, 0.05)
                    )

                    time.sleep(duration_s)

                    if not tone_on:
                        self.engine.process_silence(
                            event.get('duration_ms', 60)
                        )

                elif event_type == 'done':
                    time.sleep(
                        random.uniform(2.0, 4.0)
                    )

            # Pause between messages
            if self._running:
                time.sleep(random.uniform(3.0, 6.0))

        print("[Morse-SDR] Mock receive loop ended")
