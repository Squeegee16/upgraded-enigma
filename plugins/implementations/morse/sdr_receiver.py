"""
SDR Morse Receiver
==================
Receives and decodes CW (morse code) from an RTL-SDR
or the configured radio (via audio interface).

Architecture:
    RTL-SDR mode:
        RTL-SDR -> IQ samples -> AM demodulate ->
        Goertzel tone detect -> MorseEngine decode

    Radio mode:
        Radio audio output -> sound card ->
        sounddevice capture -> Goertzel tone detect ->
        MorseEngine decode

The SDR receiver runs in a background thread and
pushes tone on/off events to the MorseEngine which
performs the timing analysis and character decode.

Frequency:
    RTL-SDR mode: center frequency set by user.
    The morse tone is assumed to be at or near the
    center frequency (within +/- 500 Hz).

    Radio mode: audio from the radio contains the
    CW tone at the sidetone frequency (400-1200 Hz).
"""

import threading
import time
from datetime import datetime


class SDRMorseReceiver:
    """
    Background SDR/audio receiver for CW decode.

    Manages the receive thread and coordinates between
    the SDR/audio source and the MorseEngine decoder.
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
        self._source = 'sdr'  # 'sdr' or 'radio'

        # SDR settings
        self._center_freq = config.get(
            'center_frequency', 7030000
        )  # 7.030 MHz (40m CW)
        self._sample_rate = 250000  # 250 kHz
        self._sdr_device = None

        # Audio settings (radio mode)
        self._audio_device = config.get(
            'audio_input_device', None
        )
        self._audio_sample_rate = 44100

        # Status
        self._status = {
            'running': False,
            'source': 'sdr',
            'frequency': self._center_freq,
            'signal_level': 0.0,
            'tone_detected': False,
            'error': None,
            'samples_processed': 0,
        }

        # Signal level history for display
        self._signal_history = []
        self._signal_lock = threading.Lock()

    def set_frequency(self, freq_hz):
        """
        Set the receive center frequency.

        Args:
            freq_hz: Center frequency in Hz
        """
        self._center_freq = freq_hz
        self._status['frequency'] = freq_hz

        # Update SDR if running
        if self._sdr_device and self._source == 'sdr':
            try:
                self._sdr_device.center_freq = freq_hz
            except Exception as e:
                print(f"[Morse-SDR] Freq update error: {e}")

    def set_source(self, source):
        """
        Switch between SDR and radio audio input.

        Args:
            source: 'sdr' or 'radio'
        """
        if source not in ('sdr', 'radio'):
            return

        was_running = self._running
        if was_running:
            self.stop()

        self._source = source
        self._status['source'] = source

        if was_running:
            self.start()

    def start(self):
        """
        Start the receive thread.

        Returns:
            tuple: (success: bool, message: str)
        """
        if self._running:
            return False, "Already running"

        self._running = True
        self._status['running'] = True
        self._status['error'] = None

        if self._source == 'sdr':
            target = self._sdr_receive_loop
        else:
            target = self._audio_receive_loop

        self._thread = threading.Thread(
            target=target,
            daemon=True,
            name='morse-receiver'
        )
        self._thread.start()

        return True, f"Receiver started ({self._source})"

    def stop(self):
        """Stop the receive thread."""
        self._running = False
        self._status['running'] = False
        self._status['tone_detected'] = False

        if self._sdr_device:
            try:
                self._sdr_device.close()
            except Exception:
                pass
            self._sdr_device = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _sdr_receive_loop(self):
        """
        Main SDR receive and decode loop.

        Opens RTL-SDR, reads IQ samples, demodulates AM,
        detects the CW tone using Goertzel, and sends
        tone events to the MorseEngine.
        """
        try:
            import numpy as np

            # Try to open RTL-SDR
            try:
                import rtlsdr
                sdr = rtlsdr.RtlSdr(
                    device_index=self.config.get(
                        'sdr_device_index', 0
                    )
                )
                sdr.center_freq = self._center_freq
                sdr.sample_rate = self._sample_rate
                sdr.gain = self.config.get('sdr_gain', 30)
                self._sdr_device = sdr
                print(
                    f"[Morse-SDR] RTL-SDR opened: "
                    f"{self._center_freq/1e6:.3f} MHz"
                )
            except Exception as e:
                print(
                    f"[Morse-SDR] RTL-SDR not available: "
                    f"{e}"
                )
                print(
                    "[Morse-SDR] Falling back to "
                    "simulated receive"
                )
                self._sdr_receive_loop_mock()
                return

            # Block size for processing
            block_size = 16384
            prev_tone_state = False
            silence_start = None

            while self._running:
                try:
                    # Read IQ samples
                    samples = sdr.read_samples(block_size)

                    # AM demodulate: magnitude of IQ
                    magnitude = np.abs(samples)

                    # Normalise
                    if magnitude.max() > 0:
                        magnitude = (
                            magnitude / magnitude.max()
                        )

                    # Detect morse tone using Goertzel
                    # The audio frequency depends on the
                    # offset from center frequency
                    tone_freq = self.config.get(
                        'tone_hz', 700
                    )
                    audio_rate = 8000  # After decimation

                    # Simple decimation for audio rate
                    decimate = self._sample_rate // audio_rate
                    audio = magnitude[::decimate]

                    tone_detected = (
                        self.engine.detect_tone_in_samples(
                            audio, audio_rate
                        )
                    )

                    # Update signal level
                    level = float(np.mean(magnitude))
                    self._status['signal_level'] = level
                    self._status['tone_detected'] = (
                        tone_detected
                    )

                    # Send tone events to engine
                    ts = time.time() * 1000
                    if tone_detected != prev_tone_state:
                        self.engine.process_tone_event(
                            tone_detected, ts
                        )
                        prev_tone_state = tone_detected

                        if not tone_detected:
                            silence_start = ts
                    elif not tone_detected and \
                            silence_start is not None:
                        silence_duration = ts - silence_start
                        self.engine.process_silence(
                            silence_duration
                        )

                    self._status['samples_processed'] += (
                        block_size
                    )

                except Exception as e:
                    print(
                        f"[Morse-SDR] Receive error: {e}"
                    )
                    time.sleep(0.1)

        except ImportError:
            self._sdr_receive_loop_mock()
        except Exception as e:
            print(f"[Morse-SDR] Fatal error: {e}")
            self._status['error'] = str(e)
            self._status['running'] = False

    def _sdr_receive_loop_mock(self):
        """
        Mock receive loop when RTL-SDR is not available.

        Simulates a CW signal for testing without hardware.
        Sends 'DE W1AW K' in morse at the configured WPM.
        """
        import time

        print("[Morse-SDR] Running in mock mode (no RTL-SDR)")
        self._status['error'] = (
            'RTL-SDR not available — mock mode active'
        )

        # Morse pattern for "DE W1AW K"
        # Each item: (tone_on, duration_factor)
        # duration_factor is multiples of dot_ms
        mock_message = "DE W1AW K"
        timing = self.engine.text_to_timing(mock_message)

        idx = 0
        while self._running:
            if idx >= len(timing):
                idx = 0
                time.sleep(2.0)  # Pause between repeats
                continue

            event = timing[idx]
            idx += 1

            if event['type'] == 'done':
                time.sleep(2.0)
                continue

            tone_on = event['type'] == 'tone_on'
            duration_s = event['duration_ms'] / 1000.0

            ts = time.time() * 1000
            self.engine.process_tone_event(tone_on, ts)
            self._status['tone_detected'] = tone_on

            time.sleep(duration_s)

            if not tone_on:
                self.engine.process_silence(
                    event['duration_ms']
                )

    def _audio_receive_loop(self):
        """
        Audio receive loop for radio mode.

        Captures audio from the configured sound card
        input (connected to radio audio output) and
        detects the CW tone.
        """
        try:
            import sounddevice as sd
            import numpy as np

            rate = self._audio_sample_rate
            block_ms = 50  # 50ms blocks
            block_samples = int(rate * block_ms / 1000)

            prev_tone_state = False
            silence_start = None

            print(
                f"[Morse-Audio] Starting audio capture "
                f"(device: "
                f"{self._audio_device or 'default'})"
            )

            def audio_callback(indata, frames, ts, status):
                if not self._running:
                    return

                samples = indata[:, 0]
                tone_freq = self.config.get('tone_hz', 700)

                nonlocal prev_tone_state, silence_start

                tone_detected = (
                    self.engine.detect_tone_in_samples(
                        samples, rate, threshold=0.005
                    )
                )

                level = float(np.abs(samples).mean())
                self._status['signal_level'] = level
                self._status['tone_detected'] = tone_detected

                event_ts = time.time() * 1000
                if tone_detected != prev_tone_state:
                    self.engine.process_tone_event(
                        tone_detected, event_ts
                    )
                    prev_tone_state = tone_detected
                    if not tone_detected:
                        silence_start = event_ts
                elif not tone_detected and \
                        silence_start is not None:
                    silence_duration = (
                        event_ts - silence_start
                    )
                    self.engine.process_silence(
                        silence_duration
                    )

            with sd.InputStream(
                samplerate=rate,
                channels=1,
                blocksize=block_samples,
                device=self._audio_device,
                callback=audio_callback
            ):
                while self._running:
                    time.sleep(0.1)

        except ImportError:
            print(
                "[Morse-Audio] sounddevice not available"
            )
            self._status['error'] = (
                'sounddevice not installed'
            )
            time.sleep(5)
        except Exception as e:
            print(f"[Morse-Audio] Error: {e}")
            self._status['error'] = str(e)

    def get_status(self):
        """Get current receiver status."""
        return dict(self._status)

    def get_signal_level(self):
        """
        Get current signal level (0.0 to 1.0).

        Returns:
            float: Signal level
        """
        return self._status.get('signal_level', 0.0)
