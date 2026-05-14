"""
GPS Device Interface
=====================
Provides GPS position data from multiple sources:

    1. UART serial GPS receiver
       Physical GPS module connected via serial port.
       Reads NMEA 0183 sentences from the serial port,
       parses them with NMEAParser, and calculates the
       Maidenhead grid square entirely offline using
       GridSquareCalculator.

    2. gpsd daemon
       System GPS daemon. Reads JSON from the gpsd
       socket. Falls back to NMEA serial if gpsd
       is unavailable.

    3. Mock device
       Simulated GPS for development and testing.
       Returns a fixed position (Ottawa, ON) with
       slight random drift.

Architecture:
    All GPS sources provide the same output format:
        {
            'latitude': float,      # Decimal degrees
            'longitude': float,     # Decimal degrees
            'altitude': float,      # Metres
            'grid': str,            # Maidenhead 6-char
            'grid_4': str,          # Maidenhead 4-char
            'time': str,            # ISO 8601 UTC
            'date': str,            # YYYY-MM-DD
            'satellites': int,      # Satellites used
            'satellites_view': int, # Satellites visible
            'hdop': float,          # Horizontal DOP
            'speed_kmh': float,     # Ground speed
            'track_true': float,    # Track degrees true
            'has_fix': bool,        # Valid fix flag
            'fix_quality': int,     # GGA fix quality
            'source': str,          # 'uart'/'gpsd'/'mock'
        }

    The grid square is calculated offline using the
    GridSquareCalculator class — no internet required.

UART GPS usage:
    Typical Raspberry Pi setup:
        GPS module TX -> Pi GPIO 15 (UART RX)
        GPS module RX -> Pi GPIO 14 (UART TX)  [optional]
        GPS module VCC -> 3.3V or 5V
        GPS module GND -> GND

    Common devices: u-blox NEO-6M, NEO-8M, NEO-M9N,
                    PA6H, L80, GT-U7

    Default serial port: /dev/ttyAMA0 (Raspberry Pi UART)
    Alternative:         /dev/ttyUSB0 (USB GPS dongle)
    Baud rate:           9600 (most GPS modules default)
"""

import os
import threading
import time
import random
from datetime import datetime
from abc import ABC, abstractmethod

from devices.nmea_parser import NMEAParser
from devices.grid_square import (
    GridSquareCalculator,
    latlon_to_grid
)


# ------------------------------------------------------------------
# Abstract base
# ------------------------------------------------------------------

class BaseGPSDevice(ABC):
    """Abstract base for all GPS device implementations."""

    def __init__(self):
        self._connected = False
        self._position = None
        self._lock = threading.Lock()

    @abstractmethod
    def connect(self):
        """Establish connection to GPS source."""

    @abstractmethod
    def disconnect(self):
        """Close connection."""

    @abstractmethod
    def is_connected(self):
        """Return True if connected."""

    @abstractmethod
    def get_position(self):
        """
        Return current GPS position dict or None.
        """

    def _empty_position(self, source='unknown'):
        """Return an empty position dict."""
        return {
            'latitude': None,
            'longitude': None,
            'altitude': 0.0,
            'grid': '',
            'grid_4': '',
            'time': datetime.utcnow().isoformat(),
            'date': datetime.utcnow().strftime(
                '%Y-%m-%d'
            ),
            'satellites': 0,
            'satellites_view': 0,
            'hdop': 99.9,
            'speed_kmh': 0.0,
            'track_true': None,
            'has_fix': False,
            'fix_quality': 0,
            'source': source,
        }


# ------------------------------------------------------------------
# UART Serial GPS
# ------------------------------------------------------------------

class UARTGPSDevice(BaseGPSDevice):
    """
    GPS receiver connected via UART serial interface.

    Reads raw NMEA 0183 sentences from a serial port,
    parses them with NMEAParser, and computes the
    Maidenhead grid square offline with
    GridSquareCalculator.

    This is the primary GPS interface for Raspberry Pi
    with a directly-wired GPS module.

    Default pinout (Raspberry Pi):
        UART0 (/dev/ttyAMA0):  GPIO 14 TX, GPIO 15 RX
        UART5 (/dev/ttyAMA5):  GPIO 12 TX, GPIO 13 RX
        USB serial (/dev/ttyUSB0): via USB-to-serial

    Note: On Raspberry Pi OS, you may need to:
        sudo raspi-config -> Interface Options -> Serial
        Disable serial console, enable serial hardware
    """

    # Number of NMEA lines to read per position update
    LINES_PER_UPDATE = 20

    # Maximum seconds to wait for a fix before giving up
    FIX_TIMEOUT = 120

    def __init__(self, port='/dev/ttyAMA0',
                 baudrate=9600, timeout=2.0):
        """
        Initialise the UART GPS device.

        Args:
            port: Serial port path
                  e.g. '/dev/ttyAMA0' (Pi hardware UART)
                       '/dev/ttyUSB0' (USB GPS dongle)
                       '/dev/ttyACM0' (CDC ACM GPS)
            baudrate: Serial baud rate
                      9600  - most GPS modules default
                      38400 - some u-blox modules
                      115200 - high-speed mode
            timeout: Read timeout in seconds
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._serial = None
        self._parser = NMEAParser()
        self._grid_calc = GridSquareCalculator()

        # Background reader thread
        self._reader_thread = None
        self._reading = False

        # Latest parsed state
        self._gps_state = None
        self._state_lock = threading.Lock()

        # Sentence statistics
        self._stats = {
            'sentences_received': 0,
            'sentences_parsed': 0,
            'parse_errors': 0,
            'fix_acquired_at': None,
        }

    def connect(self):
        """
        Open the serial port and start the reader thread.

        Returns:
            bool: True if connected successfully
        """
        try:
            import serial as pyserial

            self._serial = pyserial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=pyserial.EIGHTBITS,
                parity=pyserial.PARITY_NONE,
                stopbits=pyserial.STOPBITS_ONE,
            )

            if not self._serial.is_open:
                self._serial.open()

            self._connected = True
            self._reading = True

            # Start background NMEA reader thread
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
                name='gps-uart-reader'
            )
            self._reader_thread.start()

            print(
                f"[GPS-UART] Connected: {self.port} "
                f"@ {self.baudrate} baud"
            )
            return True

        except ImportError:
            print(
                "[GPS-UART] pyserial not installed. "
                "Add 'pyserial' to requirements.txt"
            )
            return False

        except Exception as e:
            print(
                f"[GPS-UART] Connection error: {e}"
            )
            self._connected = False
            return False

    def disconnect(self):
        """Stop reader thread and close serial port."""
        self._reading = False
        self._connected = False

        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

        print("[GPS-UART] Disconnected")

    def is_connected(self):
        """Return True if serial port is open."""
        if not self._connected:
            return False
        if self._serial is None:
            return False
        try:
            return self._serial.is_open
        except Exception:
            return False

    def get_position(self):
        """
        Get the latest GPS position.

        Returns the most recent valid position from the
        background reader thread. Computes or updates
        the Maidenhead grid square whenever coordinates
        are available, with or without a full fix.

        Returns:
            dict: Position data
            None: If no data available yet
        """
        with self._state_lock:
            if self._gps_state is None:
                return None

            state = dict(self._gps_state)

        # Build standardised position dict
        lat = state.get('latitude')
        lon = state.get('longitude')
        has_fix = state.get('has_fix', False)

        # Calculate grid square if we have coordinates
        # (even partial data is useful for display)
        grid_6 = ''
        grid_4 = ''
        if lat is not None and lon is not None:
            try:
                grid_6 = self._grid_calc.from_latlon(
                    lat, lon, precision=6
                )
                grid_4 = self._grid_calc.from_latlon(
                    lat, lon, precision=4
                )
            except Exception as e:
                print(
                    f"[GPS-UART] Grid calc error: {e}"
                )

        return {
            'latitude': lat,
            'longitude': lon,
            'altitude': state.get('altitude', 0.0),
            'grid': grid_6,
            'grid_4': grid_4,
            'time': state.get('utc_time', ''),
            'date': state.get('utc_date', ''),
            'datetime': state.get('utc_datetime', ''),
            'satellites': state.get(
                'satellites_used', 0
            ),
            'satellites_view': state.get(
                'satellites_in_view', 0
            ),
            'hdop': state.get('hdop'),
            'vdop': state.get('vdop'),
            'pdop': state.get('pdop'),
            'speed_kmh': state.get('speed_kmh'),
            'speed_knots': state.get('speed_knots'),
            'track_true': state.get('track_true'),
            'magnetic_variation': state.get(
                'magnetic_variation'
            ),
            'has_fix': has_fix,
            'fix_quality': state.get('fix_quality', 0),
            'fix_type': state.get('fix_type', 1),
            'satellite_data': state.get(
                'satellite_data', []
            ),
            'source': 'uart',
            'port': self.port,
            'baudrate': self.baudrate,
            'stats': dict(self._stats),
            'last_update': state.get('last_update'),
        }

    def get_raw_sentences(self, count=10):
        """
        Get recently received raw NMEA sentences.

        Useful for the settings page debug display.

        Args:
            count: Maximum sentences to return

        Returns:
            list: Recent raw NMEA sentence strings
        """
        with self._state_lock:
            return list(self._raw_sentences[-count:]) \
                if hasattr(self, '_raw_sentences') else []

    def get_stats(self):
        """
        Get NMEA sentence statistics.

        Returns:
            dict: Parse statistics
        """
        stats = dict(self._stats)
        if self._gps_state:
            stats['has_fix'] = self._gps_state.get(
                'has_fix', False
            )
            stats['fix_quality'] = self._gps_state.get(
                'fix_quality', 0
            )
        return stats

    def _reader_loop(self):
        """
        Background thread: read NMEA sentences
        continuously from the serial port.

        Reads line by line, passes each line to the
        NMEAParser, and updates the state. Grid square
        is calculated here so get_position() is fast.
        """
        # Keep last 50 raw sentences for debug display
        self._raw_sentences = []

        print(
            "[GPS-UART] Reader thread started. "
            "Waiting for NMEA data..."
        )

        consecutive_errors = 0

        while self._reading and self._connected:
            try:
                if not self._serial or \
                        not self._serial.is_open:
                    time.sleep(1)
                    continue

                # Read one line from serial port
                try:
                    raw_bytes = self._serial.readline()
                except Exception as e:
                    print(
                        f"[GPS-UART] Read error: {e}"
                    )
                    consecutive_errors += 1
                    if consecutive_errors > 10:
                        print(
                            "[GPS-UART] Too many errors, "
                            "stopping reader"
                        )
                        self._connected = False
                        break
                    time.sleep(0.1)
                    continue

                consecutive_errors = 0

                if not raw_bytes:
                    time.sleep(0.01)
                    continue

                # Decode bytes to string
                try:
                    sentence = raw_bytes.decode(
                        'ascii', errors='replace'
                    ).strip()
                except Exception:
                    continue

                if not sentence:
                    continue

                # Store raw sentence for debug display
                if sentence.startswith('$'):
                    self._raw_sentences.append(
                        f"{datetime.utcnow().strftime('%H:%M:%S')} "
                        f"{sentence}"
                    )
                    if len(self._raw_sentences) > 50:
                        self._raw_sentences.pop(0)

                self._stats['sentences_received'] += 1

                # Parse the NMEA sentence
                result = self._parser.parse(sentence)

                if result:
                    self._stats['sentences_parsed'] += 1

                    # Record when fix was first acquired
                    if result.get('has_fix') and \
                            self._stats[
                                'fix_acquired_at'
                            ] is None:
                        self._stats[
                            'fix_acquired_at'
                        ] = datetime.utcnow().isoformat()
                        print(
                            "[GPS-UART] ✓ GPS fix acquired!"
                        )

                    # Update shared state
                    with self._state_lock:
                        self._gps_state = result

                else:
                    if sentence.startswith('$'):
                        self._stats['parse_errors'] += 1

            except Exception as e:
                print(
                    f"[GPS-UART] Reader error: {e}"
                )
                time.sleep(0.1)

        print("[GPS-UART] Reader thread stopped")


# ------------------------------------------------------------------
# gpsd-based GPS
# ------------------------------------------------------------------

class GPSDDevice(BaseGPSDevice):
    """
    GPS via the gpsd system daemon.

    gpsd is a Linux GPS multiplexer that reads from the
    GPS hardware and provides a JSON socket interface.
    Multiple applications can share a single GPS device.

    Install: sudo apt-get install gpsd gpsd-clients
    Start:   sudo systemctl start gpsd
    Config:  /etc/default/gpsd (set DEVICES= to port)

    Falls back to UARTGPSDevice if gpsd is unavailable.
    """

    def __init__(self, host='127.0.0.1', port=2947,
                 timeout=5):
        """
        Initialise gpsd client.

        Args:
            host: gpsd host address
            port: gpsd port (default 2947)
            timeout: Connection timeout
        """
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

        self._gpsd = None
        self._grid_calc = GridSquareCalculator()
        self._current_position = None
        self._reader_thread = None
        self._reading = False

    def connect(self):
        """Connect to gpsd and start reader thread."""
        try:
            import gpsd as gpsd_lib
            gpsd_lib.connect(
                host=self.host,
                port=self.port
            )
            self._gpsd = gpsd_lib
            self._connected = True
            self._reading = True

            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
                name='gps-gpsd-reader'
            )
            self._reader_thread.start()

            print(
                f"[GPS-gpsd] Connected to gpsd "
                f"{self.host}:{self.port}"
            )
            return True

        except ImportError:
            print(
                "[GPS-gpsd] gpsd Python library not "
                "installed. Install: pip install gpsd-py3"
            )
            return False
        except Exception as e:
            print(f"[GPS-gpsd] Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from gpsd."""
        self._reading = False
        self._connected = False

    def is_connected(self):
        return self._connected

    def get_position(self):
        """Get current GPS position from gpsd."""
        with self._lock:
            return dict(self._current_position) \
                if self._current_position else None

    def _reader_loop(self):
        """Background gpsd reader."""
        while self._reading and self._connected:
            try:
                packet = self._gpsd.get_current()

                if packet.mode >= 2:
                    lat = packet.lat
                    lon = packet.lon
                    alt = getattr(packet, 'alt', 0.0)

                    grid_6 = ''
                    grid_4 = ''
                    try:
                        grid_6 = (
                            self._grid_calc.from_latlon(
                                lat, lon, precision=6
                            )
                        )
                        grid_4 = (
                            self._grid_calc.from_latlon(
                                lat, lon, precision=4
                            )
                        )
                    except Exception:
                        pass

                    with self._lock:
                        self._current_position = {
                            'latitude': lat,
                            'longitude': lon,
                            'altitude': alt or 0.0,
                            'grid': grid_6,
                            'grid_4': grid_4,
                            'time': datetime.utcnow()
                            .isoformat(),
                            'date': datetime.utcnow()
                            .strftime('%Y-%m-%d'),
                            'satellites': getattr(
                                packet, 'sats_valid', 0
                            ),
                            'satellites_view': getattr(
                                packet, 'sats', 0
                            ),
                            'hdop': getattr(
                                packet, 'hdop', None
                            ),
                            'speed_kmh': getattr(
                                packet, 'hspeed', None
                            ),
                            'track_true': getattr(
                                packet, 'track', None
                            ),
                            'has_fix': packet.mode >= 2,
                            'fix_quality': packet.mode,
                            'source': 'gpsd',
                        }

            except Exception:
                pass

            time.sleep(1)


# ------------------------------------------------------------------
# Mock GPS
# ------------------------------------------------------------------

class MockGPSDevice(BaseGPSDevice):
    """
    Simulated GPS device for development and testing.

    Returns a position near Ottawa, Ontario, Canada
    with slight random drift to simulate movement.

    Demonstrates all GPS features without hardware.
    """

    # Ottawa, ON - near FN25 grid square
    BASE_LAT = 45.4215
    BASE_LON = -75.6972

    def __init__(self):
        super().__init__()
        self._grid_calc = GridSquareCalculator()
        self._drift_lat = 0.0
        self._drift_lon = 0.0
        self._satellites = 8
        self._fix_quality = 1
        self._start_time = None

    def connect(self):
        """Simulate connection — always succeeds."""
        self._connected = True
        self._start_time = datetime.utcnow()
        print(
            "[GPS-Mock] Connected. Simulating position "
            "near Ottawa, ON (FN25)"
        )
        return True

    def disconnect(self):
        """Simulate disconnection."""
        self._connected = False

    def is_connected(self):
        return self._connected

    def get_position(self):
        """
        Return simulated GPS position with slight drift.

        Simulates realistic GPS behaviour:
        - Fix quality improves over time
        - Small position drift each call
        - Satellite count varies slightly
        """
        if not self._connected:
            return None

        # Simulate gradual position drift
        self._drift_lat += random.uniform(-0.00002, 0.00002)
        self._drift_lon += random.uniform(-0.00002, 0.00002)

        # Clamp drift to reasonable range
        self._drift_lat = max(-0.001,
                              min(0.001, self._drift_lat))
        self._drift_lon = max(-0.001,
                              min(0.001, self._drift_lon))

        lat = self.BASE_LAT + self._drift_lat
        lon = self.BASE_LON + self._drift_lon
        alt = 70.0 + random.uniform(-2, 2)

        # Calculate grid square
        grid_6 = ''
        grid_4 = ''
        try:
            grid_6 = self._grid_calc.from_latlon(
                lat, lon, precision=6
            )
            grid_4 = self._grid_calc.from_latlon(
                lat, lon, precision=4
            )
        except Exception:
            pass

        # Vary satellite count slightly
        self._satellites = max(
            4,
            self._satellites + random.randint(-1, 1)
        )
        self._satellites = min(12, self._satellites)

        now = datetime.utcnow()

        return {
            'latitude': round(lat, 8),
            'longitude': round(lon, 8),
            'altitude': round(alt, 1),
            'grid': grid_6,
            'grid_4': grid_4,
            'time': now.strftime('%H:%M:%S'),
            'date': now.strftime('%Y-%m-%d'),
            'datetime': now.isoformat() + 'Z',
            'satellites': self._satellites,
            'satellites_view': self._satellites + 3,
            'hdop': round(random.uniform(0.8, 1.5), 1),
            'vdop': round(random.uniform(1.0, 2.0), 1),
            'pdop': round(random.uniform(1.2, 2.5), 1),
            'speed_kmh': round(
                random.uniform(0, 0.5), 2
            ),
            'track_true': round(
                random.uniform(0, 360), 1
            ),
            'magnetic_variation': -14.5,  # Ottawa area
            'has_fix': True,
            'fix_quality': 1,
            'fix_type': 3,  # 3D fix
            'satellite_data': [
                {
                    'prn': str(i),
                    'elevation': random.randint(
                        20, 80
                    ),
                    'azimuth': random.randint(0, 359),
                    'snr': random.randint(30, 45),
                }
                for i in range(1, self._satellites + 1)
            ],
            'source': 'mock',
            'port': 'mock',
            'baudrate': 0,
            'stats': {
                'sentences_received': 0,
                'sentences_parsed': 0,
                'parse_errors': 0,
                'has_fix': True,
            },
            'last_update': now.isoformat(),
        }


# ------------------------------------------------------------------
# GPS Device Factory
# ------------------------------------------------------------------

def get_gps_device(config):
    """
    Factory function that creates the appropriate GPS
    device based on application configuration.

    Selection priority:
        1. USE_MOCK_DEVICES=true -> MockGPSDevice
        2. GPS_SOURCE=uart       -> UARTGPSDevice
        3. GPS_SOURCE=gpsd       -> GPSDDevice
        4. GPS_SOURCE=mock       -> MockGPSDevice
        5. Default               -> UARTGPSDevice
           (with mock fallback on connection failure)

    Args:
        config: Flask application config dict or
                dict-like object with keys:
                    USE_MOCK_DEVICES  bool
                    GPS_SOURCE        str (uart/gpsd/mock)
                    GPS_SERIAL_PORT   str
                    GPS_BAUD_RATE     int
                    GPSD_HOST         str
                    GPSD_PORT         int

    Returns:
        BaseGPSDevice: Configured GPS device instance
    """
    # Mock mode — for development without hardware
    use_mock = config.get('USE_MOCK_DEVICES', True)
    gps_source = config.get('GPS_SOURCE', 'uart').lower()

    if use_mock or gps_source == 'mock':
        print("[GPS] Using mock GPS device")
        device = MockGPSDevice()
        device.connect()
        return device

    # UART serial GPS (direct hardware connection)
    if gps_source in ('uart', 'serial'):
        port = config.get(
            'GPS_SERIAL_PORT', '/dev/ttyAMA0'
        )
        baudrate = int(
            config.get('GPS_BAUD_RATE', 9600)
        )

        print(
            f"[GPS] Using UART GPS: "
            f"{port} @ {baudrate} baud"
        )

        device = UARTGPSDevice(
            port=port,
            baudrate=baudrate
        )

        if device.connect():
            return device

        # Connection failed — fall back to mock
        print(
            "[GPS] UART connection failed, "
            "falling back to mock GPS"
        )
        mock = MockGPSDevice()
        mock.connect()
        return mock

    # gpsd daemon
    if gps_source == 'gpsd':
        host = config.get('GPSD_HOST', '127.0.0.1')
        port = int(config.get('GPSD_PORT', 2947))

        print(
            f"[GPS] Using gpsd: {host}:{port}"
        )

        device = GPSDDevice(host=host, port=port)

        if device.connect():
            return device

        # gpsd failed — try UART fallback
        print(
            "[GPS] gpsd unavailable, trying UART..."
        )
        uart_port = config.get(
            'GPS_SERIAL_PORT', '/dev/ttyAMA0'
        )
        uart_baud = int(
            config.get('GPS_BAUD_RATE', 9600)
        )
        uart = UARTGPSDevice(
            port=uart_port, baudrate=uart_baud
        )

        if uart.connect():
            return uart

        # Both failed — mock
        print("[GPS] All sources failed, using mock")
        mock = MockGPSDevice()
        mock.connect()
        return mock

    # Unknown source — default to UART
    print(
        f"[GPS] Unknown source '{gps_source}', "
        "defaulting to UART"
    )
    port = config.get(
        'GPS_SERIAL_PORT', '/dev/ttyAMA0'
    )
    baudrate = int(config.get('GPS_BAUD_RATE', 9600))

    device = UARTGPSDevice(port=port, baudrate=baudrate)
    if device.connect():
        return device

    mock = MockGPSDevice()
    mock.connect()
    return mock
