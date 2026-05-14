"""
Morse Code Engine
==================
Handles all morse code encode/decode/timing logic.

Encoding:
    Converts text to morse code sequences using the
    international morse code standard. Produces timing
    data for the web audio API sidetone generator.

Decoding:
    Goertzel algorithm detects a specific tone frequency
    in audio samples. Timing analysis converts on/off
    durations to dots, dashes, and word spaces.

Timing:
    All timing is relative to the dot duration.
    At 20 WPM: dot = 60ms
        dash       = 3 dots (180ms)
        intra-char = 1 dot  (60ms)
        inter-char = 3 dots (180ms)
        word space = 7 dots (420ms)

    Farnsworth spacing increases inter-character and
    word spacing while keeping character timing at the
    set WPM, improving readability for learners.

Reference:
    ITU-R M.1677-1 International Morse Code
"""

import time
import threading
import queue
import math
from datetime import datetime
from collections import deque


# International Morse Code table
# Maps character -> morse string ('.' dot, '-' dash)
MORSE_CODE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',
    'D': '-..',   'E': '.',     'F': '..-.',
    'G': '--.',   'H': '....',  'I': '..',
    'J': '.---',  'K': '-.-',   'L': '.-..',
    'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',
    'S': '...',   'T': '-',     'U': '..-',
    'V': '...-',  'W': '.--',   'X': '-..-',
    'Y': '-.--',  'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---',
    '3': '...--', '4': '....-', '5': '.....',
    '6': '-....', '7': '--...', '8': '---..',
    '9': '----.',
    '.': '.-.-.-', ',': '--..--', '?': '..--..',
    "'": '.----.', '!': '-.-.--', '/': '-..-.',
    '(': '-.--.',  ')': '-.--.-', '&': '.-...',
    ':': '---...', ';': '-.-.-.', '=': '-...-',
    '+': '.-.-.',  '-': '-....-', '_': '..--.-',
    '"': '.-..-.', '$': '...-..-','@': '.--.-.',
    ' ': ' ',       # Word space marker
}

# Reverse lookup: morse string -> character
MORSE_REVERSE = {v: k for k, v in MORSE_CODE.items()
                 if k != ' '}


class MorseEngine:
    """
    Core Morse code encoding, decoding, and timing engine.

    Provides:
        - Text to morse timing sequences for Web Audio
        - Goertzel tone detection from SDR audio
        - Timing analysis for decode
        - Real-time decode buffer management
    """

    def __init__(self, wpm=20, tone_hz=700,
                 farnsworth_wpm=None):
        """
        Initialise morse engine.

        Args:
            wpm: Words per minute (character rate)
            tone_hz: Sidetone frequency in Hz (400-1200)
            farnsworth_wpm: Farnsworth spacing WPM
                           (slower inter-char than char rate)
        """
        self.wpm = wpm
        self.tone_hz = max(400, min(1200, tone_hz))
        self.farnsworth_wpm = farnsworth_wpm

        # Decode state
        self._decode_buffer = deque(maxlen=500)
        self._decoded_text = []
        self._decode_lock = threading.Lock()

        # Current symbol being decoded
        self._current_symbol = ''
        self._last_tone_time = None
        self._tone_on = False
        self._tone_start = None

        # Decode queue for background processing
        self._symbol_queue = queue.Queue()

        # Callbacks
        self._decode_callbacks = []

    # ----------------------------------------------------------
    # Timing calculations
    # ----------------------------------------------------------

    @property
    def dot_ms(self):
        """Dot duration in milliseconds at current WPM."""
        return 1200 / self.wpm

    @property
    def dash_ms(self):
        """Dash duration = 3 dots."""
        return self.dot_ms * 3

    @property
    def intra_char_ms(self):
        """Gap between elements within a character = 1 dot."""
        return self.dot_ms

    @property
    def inter_char_ms(self):
        """
        Gap between characters.

        Uses Farnsworth spacing if configured.
        Standard: 3 dots.
        """
        if self.farnsworth_wpm and \
                self.farnsworth_wpm < self.wpm:
            return 1200 / self.farnsworth_wpm * 3
        return self.dot_ms * 3

    @property
    def word_space_ms(self):
        """
        Gap between words.

        Uses Farnsworth spacing if configured.
        Standard: 7 dots.
        """
        if self.farnsworth_wpm and \
                self.farnsworth_wpm < self.wpm:
            return 1200 / self.farnsworth_wpm * 7
        return self.dot_ms * 7

    def set_wpm(self, wpm):
        """
        Update words per minute.

        Args:
            wpm: New WPM value (1-60)
        """
        self.wpm = max(1, min(60, int(wpm)))

    def set_tone(self, hz):
        """
        Update sidetone frequency.

        Args:
            hz: Frequency in Hz (400-1200)
        """
        self.tone_hz = max(400, min(1200, int(hz)))

    # ----------------------------------------------------------
    # Encoding: text to morse timing
    # ----------------------------------------------------------

    def text_to_morse(self, text):
        """
        Convert text to morse code string.

        Args:
            text: Plain text to encode

        Returns:
            str: Morse string (e.g. ".- -... -.-.")
        """
        text = text.upper().strip()
        words = text.split()
        morse_words = []

        for word in words:
            chars = []
            for char in word:
                if char in MORSE_CODE:
                    chars.append(MORSE_CODE[char])
            if chars:
                morse_words.append(' '.join(chars))

        return '  '.join(morse_words)

    def text_to_timing(self, text):
        """
        Convert text to a list of tone timing events.

        Each event is a dict with:
            type: 'tone_on' | 'tone_off' | 'done'
            duration_ms: Duration in milliseconds
            char: Character being sent (for display)
            morse: Morse symbols for the char

        This timing sequence is sent to the browser
        where the Web Audio API generates the actual tones.

        Args:
            text: Plain text to encode

        Returns:
            list: Timing event dicts
        """
        events = []
        text = text.upper().strip()
        words = text.split()

        for word_idx, word in enumerate(words):
            for char_idx, char in enumerate(word):
                if char not in MORSE_CODE:
                    continue

                symbols = MORSE_CODE[char]
                morse_str = symbols

                for sym_idx, symbol in enumerate(symbols):
                    # Tone ON
                    if symbol == '.':
                        duration = self.dot_ms
                    else:
                        duration = self.dash_ms

                    events.append({
                        'type': 'tone_on',
                        'duration_ms': duration,
                        'char': char,
                        'morse': morse_str,
                    })

                    # Intra-character gap (not after last symbol)
                    if sym_idx < len(symbols) - 1:
                        events.append({
                            'type': 'tone_off',
                            'duration_ms': self.intra_char_ms,
                            'char': char,
                            'morse': morse_str,
                        })

                # Inter-character gap (not after last char in word)
                if char_idx < len(word) - 1:
                    events.append({
                        'type': 'tone_off',
                        'duration_ms': self.inter_char_ms,
                        'char': char,
                        'morse': morse_str,
                    })

            # Word gap (not after last word)
            if word_idx < len(words) - 1:
                events.append({
                    'type': 'tone_off',
                    'duration_ms': self.word_space_ms,
                    'char': ' ',
                    'morse': ' ',
                })

        events.append({'type': 'done', 'duration_ms': 0})
        return events

    # ----------------------------------------------------------
    # Decoding: audio signal to text
    # ----------------------------------------------------------

    def process_tone_event(self, tone_on, timestamp_ms=None):
        """
        Process a tone on/off event from the SDR decoder.

        Called by the SDR receiver when it detects the
        morse tone appearing or disappearing.

        Args:
            tone_on: True when tone starts, False when stops
            timestamp_ms: Event timestamp in milliseconds
                         (uses current time if None)
        """
        if timestamp_ms is None:
            timestamp_ms = time.time() * 1000

        if tone_on:
            # Tone started — record start time
            self._tone_on = True
            self._tone_start = timestamp_ms

        else:
            # Tone ended — classify as dot or dash
            if self._tone_start is not None:
                duration = timestamp_ms - self._tone_start
                self._tone_on = False

                # Classify element
                if duration < self.dot_ms * 2:
                    self._current_symbol += '.'
                else:
                    self._current_symbol += '-'

                self._last_tone_time = timestamp_ms

    def process_silence(self, duration_ms):
        """
        Process a silence period after a tone sequence.

        Called periodically to check if enough silence
        has elapsed to complete a character or word.

        Args:
            duration_ms: Duration of current silence
        """
        if not self._current_symbol:
            # No symbol being decoded
            if duration_ms > self.word_space_ms * 0.8:
                # Word space
                with self._decode_lock:
                    self._decoded_text.append(' ')
            return

        if duration_ms > self.inter_char_ms * 0.7:
            # Inter-character silence — decode the symbol
            symbol = self._current_symbol
            self._current_symbol = ''

            char = MORSE_REVERSE.get(symbol, '?')

            with self._decode_lock:
                self._decoded_text.append(char)
                self._decode_buffer.appendleft({
                    'timestamp': (
                        datetime.utcnow().isoformat()
                    ),
                    'symbol': symbol,
                    'char': char,
                })

            # Notify callbacks
            for cb in self._decode_callbacks:
                try:
                    cb(char, symbol)
                except Exception:
                    pass

    def get_decoded_text(self, limit=200):
        """
        Get recently decoded text.

        Args:
            limit: Maximum characters to return

        Returns:
            str: Decoded text string
        """
        with self._decode_lock:
            text = ''.join(self._decoded_text)
            return text[-limit:] if len(text) > limit \
                else text

    def get_decode_buffer(self, limit=50):
        """
        Get decoded symbol history.

        Returns:
            list: Recent decode events
        """
        with self._decode_lock:
            return list(self._decode_buffer)[:limit]

    def clear_decode_buffer(self):
        """Clear the decoded text and symbol buffer."""
        with self._decode_lock:
            self._decoded_text.clear()
            self._decode_buffer.clear()
            self._current_symbol = ''

    def register_decode_callback(self, callback):
        """
        Register callback for decoded characters.

        Args:
            callback: Function(char, symbol) called on decode
        """
        self._decode_callbacks.append(callback)

    # ----------------------------------------------------------
    # Goertzel tone detection
    # ----------------------------------------------------------

    @staticmethod
    def goertzel(samples, target_freq, sample_rate):
        """
        Goertzel algorithm for efficient single-frequency
        tone detection in audio samples.

        More efficient than FFT when only one frequency
        needs to be detected, as is the case for CW decode.

        Args:
            samples: Array of audio samples (float -1 to 1)
            target_freq: Tone frequency to detect (Hz)
            sample_rate: Audio sample rate (Hz)

        Returns:
            float: Power at the target frequency (0.0 to 1.0)
        """
        try:
            import numpy as np

            n = len(samples)
            if n == 0:
                return 0.0

            k = int(0.5 + n * target_freq / sample_rate)
            omega = 2.0 * math.pi * k / n
            coeff = 2.0 * math.cos(omega)

            s_prev = 0.0
            s_prev2 = 0.0

            for sample in samples:
                s = float(sample) + coeff * s_prev - s_prev2
                s_prev2 = s_prev
                s_prev = s

            power = (
                s_prev2 * s_prev2 +
                s_prev * s_prev -
                coeff * s_prev * s_prev2
            )

            # Normalise by number of samples
            return power / (n * n)

        except ImportError:
            return 0.0

    def detect_tone_in_samples(self, samples, sample_rate,
                                threshold=0.01):
        """
        Detect whether the morse tone is present in samples.

        Uses the Goertzel algorithm for efficient single-
        frequency detection.

        Args:
            samples: Audio sample array
            sample_rate: Sample rate in Hz
            threshold: Power threshold for tone detection

        Returns:
            bool: True if tone is detected above threshold
        """
        power = self.goertzel(
            samples, self.tone_hz, sample_rate
        )
        return power > threshold

    # ----------------------------------------------------------
    # Timing summary for display
    # ----------------------------------------------------------

    def get_timing_summary(self):
        """
        Get current timing parameters as a display dict.

        Returns:
            dict: Timing values in milliseconds
        """
        return {
            'wpm': self.wpm,
            'tone_hz': self.tone_hz,
            'dot_ms': round(self.dot_ms, 1),
            'dash_ms': round(self.dash_ms, 1),
            'intra_char_ms': round(self.intra_char_ms, 1),
            'inter_char_ms': round(self.inter_char_ms, 1),
            'word_space_ms': round(self.word_space_ms, 1),
            'farnsworth_wpm': self.farnsworth_wpm,
        }
