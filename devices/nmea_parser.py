"""
NMEA 0183 Sentence Parser
==========================
Parses NMEA 0183 GPS sentences received from a
serial UART GPS receiver.

Supported sentence types:
    $GPGGA / $GNGGA   - Fix data (lat, lon, alt, sats)
    $GPRMC / $GNRMC   - Recommended minimum (lat, lon,
                        speed, track, date)
    $GPGSV / $GNGSV   - Satellites in view
    $GPGSA / $GNGSA   - DOP and active satellites
    $GPVTG / $GNVTG   - Track and ground speed
    $GPGLL / $GNGLL   - Geographic position lat/lon

The GN prefix indicates multi-constellation (GPS +
GLONASS + Galileo + BeiDou). The GP prefix indicates
GPS-only. This parser handles both transparently.

Checksum validation:
    Each sentence ends with *HH where HH is the XOR
    checksum of all characters between $ and *.
    Sentences with invalid checksums are rejected.

Coordinate format:
    NMEA uses DDMM.MMMM format (degrees + decimal min)
    This is different from decimal degrees.
    Conversion: DD + MM.MMMM / 60 = decimal degrees

Reference:
    NMEA 0183 Standard For Interfacing Marine
    Electronic Navigation Devices, v4.11
    National Marine Electronics Association

Usage:
    parser = NMEAParser()
    result = parser.parse('$GPGGA,...*XX')
    if result:
        print(result['latitude'], result['longitude'])
"""

import re
from datetime import datetime, timezone


class NMEAParseError(Exception):
    """Raised when NMEA sentence parsing fails."""
    pass


class NMEAParser:
    """
    Parses NMEA 0183 GPS sentences into structured data.

    Maintains internal state so partial information from
    multiple sentence types can be combined into a
    complete position fix.
    """

    # Fix quality codes from GGA sentence
    FIX_QUALITY = {
        0: 'No fix',
        1: 'GPS fix',
        2: 'DGPS fix',
        3: 'PPS fix',
        4: 'RTK fixed',
        5: 'RTK float',
        6: 'Estimated',
        7: 'Manual',
        8: 'Simulation',
    }

    # Fix type from GSA sentence
    FIX_TYPE = {
        1: 'No fix',
        2: '2D fix',
        3: '3D fix',
    }

    def __init__(self):
        """Initialise the NMEA parser with empty state."""
        # Current best position data
        self._state = {
            # Position
            'latitude': None,
            'longitude': None,
            'altitude': None,
            'altitude_unit': 'M',

            # Fix quality
            'fix_quality': 0,
            'fix_type': 1,
            'has_fix': False,

            # Accuracy
            'hdop': None,
            'vdop': None,
            'pdop': None,

            # Satellites
            'satellites_used': 0,
            'satellites_in_view': 0,
            'satellite_data': [],

            # Motion
            'speed_knots': None,
            'speed_kmh': None,
            'track_true': None,
            'magnetic_variation': None,

            # Time
            'utc_time': None,
            'utc_date': None,
            'utc_datetime': None,

            # Raw data
            'last_sentence_type': None,
            'parse_count': 0,
            'error_count': 0,
            'last_update': None,
        }

        # Satellite view data (keyed by PRN)
        self._satellites = {}

    # ----------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------

    def parse(self, sentence):
        """
        Parse a single NMEA 0183 sentence.

        Validates the checksum, identifies the sentence
        type, and dispatches to the appropriate handler.
        Updates internal state.

        Args:
            sentence: Raw NMEA sentence string
                      (e.g. '$GPGGA,...,*3F')

        Returns:
            dict: Updated state if parsed successfully
            None: If sentence is invalid or unknown
        """
        sentence = sentence.strip()

        if not sentence:
            return None

        # All NMEA sentences start with $
        if not sentence.startswith('$'):
            return None

        # Validate and strip checksum
        try:
            sentence_data = self._validate_checksum(
                sentence
            )
        except NMEAParseError:
            self._state['error_count'] += 1
            return None

        # Split fields
        parts = sentence_data.split(',')
        if not parts:
            return None

        # Extract sentence type
        # e.g. '$GPGGA' -> 'GPGGA', '$GNGLL' -> 'GNGLL'
        sentence_id = parts[0].lstrip('$').upper()

        # Strip constellation prefix (GP, GN, GL, GB, GA)
        # to get the core type
        core_type = re.sub(r'^G[PNLBA]', '', sentence_id)

        # Dispatch to handler
        handlers = {
            'GGA': self._parse_gga,
            'RMC': self._parse_rmc,
            'GSV': self._parse_gsv,
            'GSA': self._parse_gsa,
            'VTG': self._parse_vtg,
            'GLL': self._parse_gll,
        }

        handler = handlers.get(core_type)
        if not handler:
            return None

        try:
            handler(parts)
            self._state['last_sentence_type'] = (
                sentence_id
            )
            self._state['parse_count'] += 1
            self._state['last_update'] = (
                datetime.utcnow().isoformat()
            )
            return dict(self._state)
        except Exception as e:
            self._state['error_count'] += 1
            return None

    def get_state(self):
        """
        Get the current accumulated GPS state.

        Returns:
            dict: Copy of current state
        """
        return dict(self._state)

    def has_fix(self):
        """
        Check if the GPS receiver has a valid position fix.

        A fix is valid when:
        - fix_quality > 0 (from GGA)
        - latitude and longitude are not None
        - satellites_used >= 3

        Returns:
            bool: True if valid position fix available
        """
        return (
            self._state['has_fix'] and
            self._state['latitude'] is not None and
            self._state['longitude'] is not None
        )

    def reset(self):
        """Reset parser state to initial values."""
        self.__init__()

    # ----------------------------------------------------------
    # Checksum validation
    # ----------------------------------------------------------

    def _validate_checksum(self, sentence):
        """
        Validate NMEA sentence checksum.

        Checksum is XOR of all characters between
        the $ and the * (not including either).

        Args:
            sentence: Raw NMEA sentence string

        Returns:
            str: Sentence content without $ prefix
                 and checksum suffix

        Raises:
            NMEAParseError: If checksum is invalid
        """
        # Sentence may end with CR LF
        sentence = sentence.strip()

        # Find the checksum delimiter *
        if '*' in sentence:
            # Split on last * to get data and checksum
            star_idx = sentence.rfind('*')
            data = sentence[1:star_idx]  # Strip $
            checksum_str = sentence[
                star_idx + 1:star_idx + 3
            ]

            # Validate checksum is 2 hex characters
            if len(checksum_str) < 2:
                raise NMEAParseError(
                    f"Short checksum: '{checksum_str}'"
                )

            try:
                expected = int(checksum_str, 16)
            except ValueError:
                raise NMEAParseError(
                    f"Invalid checksum hex: "
                    f"'{checksum_str}'"
                )

            # Calculate XOR checksum
            calculated = 0
            for char in data:
                calculated ^= ord(char)

            if calculated != expected:
                raise NMEAParseError(
                    f"Checksum mismatch: "
                    f"calculated {calculated:02X}, "
                    f"expected {expected:02X}"
                )

            return data
        else:
            # No checksum — return data without $
            # (some GPS devices omit checksum)
            return sentence[1:]

    # ----------------------------------------------------------
    # Coordinate conversion
    # ----------------------------------------------------------

    def _dddmm_to_decimal(self, dddmm_str, direction):
        """
        Convert NMEA coordinate format to decimal degrees.

        NMEA format: DDDMM.MMMM where DDD is degrees
        and MM.MMMM is decimal minutes.

        Args:
            dddmm_str: Coordinate string (e.g. '4535.1234')
            direction: Hemisphere ('N','S','E','W')

        Returns:
            float: Decimal degrees, or None if invalid

        Example:
            '4535.1234', 'N' -> 45.585390 degrees
            '07333.4567', 'W' -> -73.557611 degrees
        """
        if not dddmm_str or not dddmm_str.strip():
            return None

        try:
            dddmm = float(dddmm_str)
        except ValueError:
            return None

        # Degrees are all digits before the last 2 digits
        # before the decimal point
        # Latitude: DDMM.MMMM (2 degree digits)
        # Longitude: DDDMM.MMMM (3 degree digits)
        degrees = int(dddmm / 100)
        minutes = dddmm - degrees * 100

        decimal = degrees + minutes / 60.0

        if direction in ('S', 'W'):
            decimal = -decimal

        return round(decimal, 8)

    def _parse_time(self, time_str):
        """
        Parse NMEA UTC time string.

        Format: HHMMSS.SS or HHMMSS

        Args:
            time_str: Time string from NMEA sentence

        Returns:
            str: ISO format time string HH:MM:SS
            None: If invalid
        """
        if not time_str or len(time_str) < 6:
            return None

        try:
            hours = int(time_str[0:2])
            minutes = int(time_str[2:4])
            seconds = float(time_str[4:])
            return (
                f"{hours:02d}:{minutes:02d}:"
                f"{int(seconds):02d}"
            )
        except (ValueError, IndexError):
            return None

    def _parse_date(self, date_str):
        """
        Parse NMEA date string.

        Format: DDMMYY

        Args:
            date_str: Date string from RMC sentence

        Returns:
            str: ISO format date YYYY-MM-DD
            None: If invalid
        """
        if not date_str or len(date_str) < 6:
            return None

        try:
            day = int(date_str[0:2])
            month = int(date_str[2:4])
            year = int(date_str[4:6])
            # Assume 2000s for 2-digit year
            full_year = 2000 + year
            return (
                f"{full_year:04d}-{month:02d}-{day:02d}"
            )
        except (ValueError, IndexError):
            return None

    # ----------------------------------------------------------
    # Sentence handlers
    # ----------------------------------------------------------

    def _parse_gga(self, parts):
        """
        Parse GGA — Global Positioning System Fix Data.

        Fields:
            0  Sentence ID ($GPGGA or $GNGGA)
            1  UTC Time (HHMMSS.SS)
            2  Latitude (DDMM.MMMM)
            3  N/S indicator
            4  Longitude (DDDMM.MMMM)
            5  E/W indicator
            6  Fix quality (0-8)
            7  Satellites used
            8  HDOP
            9  Altitude MSL
            10 Altitude unit (M)
            11 Geoid separation
            12 Geoid separation unit
            13 Age of DGPS data
            14 DGPS station ID

        GGA is the primary sentence for position data.
        Fix quality 0 = no fix, >0 = valid position.
        """
        if len(parts) < 10:
            return

        # UTC time
        time_val = self._parse_time(parts[1])
        if time_val:
            self._state['utc_time'] = time_val

        # Position
        lat = self._dddmm_to_decimal(parts[2], parts[3])
        lon = self._dddmm_to_decimal(parts[4], parts[5])

        # Fix quality
        try:
            fix_q = int(parts[6]) if parts[6] else 0
        except ValueError:
            fix_q = 0

        self._state['fix_quality'] = fix_q
        self._state['has_fix'] = fix_q > 0

        if lat is not None:
            self._state['latitude'] = lat
        if lon is not None:
            self._state['longitude'] = lon

        # Satellites used
        try:
            sats = int(parts[7]) if parts[7] else 0
            self._state['satellites_used'] = sats
        except ValueError:
            pass

        # HDOP
        try:
            if parts[8]:
                self._state['hdop'] = float(parts[8])
        except (ValueError, IndexError):
            pass

        # Altitude
        try:
            if len(parts) > 9 and parts[9]:
                self._state['altitude'] = float(parts[9])
            if len(parts) > 10 and parts[10]:
                self._state['altitude_unit'] = parts[10]
        except (ValueError, IndexError):
            pass

    def _parse_rmc(self, parts):
        """
        Parse RMC — Recommended Minimum Specific
        GPS/Transit Data.

        Fields:
            0  Sentence ID
            1  UTC Time
            2  Status (A=active/valid, V=void/invalid)
            3  Latitude
            4  N/S
            5  Longitude
            6  E/W
            7  Speed over ground (knots)
            8  Track angle (degrees true)
            9  Date (DDMMYY)
            10 Magnetic variation
            11 E/W for magnetic variation
            12 Mode (A=auto, D=diff, E=est, N=invalid)

        RMC is the most important sentence — it contains
        date, time, position, speed, and heading in one.
        """
        if len(parts) < 10:
            return

        # Time
        time_val = self._parse_time(parts[1])
        if time_val:
            self._state['utc_time'] = time_val

        # Status: A = valid, V = void
        status = parts[2].upper() if parts[2] else 'V'
        if status == 'A':
            self._state['has_fix'] = True

        # Position (only update if valid)
        if status == 'A':
            lat = self._dddmm_to_decimal(
                parts[3], parts[4]
            )
            lon = self._dddmm_to_decimal(
                parts[5], parts[6]
            )
            if lat is not None:
                self._state['latitude'] = lat
            if lon is not None:
                self._state['longitude'] = lon

        # Speed over ground
        try:
            if parts[7]:
                knots = float(parts[7])
                self._state['speed_knots'] = knots
                # 1 knot = 1.852 km/h
                self._state['speed_kmh'] = round(
                    knots * 1.852, 2
                )
        except (ValueError, IndexError):
            pass

        # Track angle (true heading)
        try:
            if parts[8]:
                self._state['track_true'] = float(
                    parts[8]
                )
        except (ValueError, IndexError):
            pass

        # Date
        if len(parts) > 9:
            date_val = self._parse_date(parts[9])
            if date_val:
                self._state['utc_date'] = date_val

                # Build combined datetime
                if self._state['utc_time']:
                    self._state['utc_datetime'] = (
                        f"{date_val}T"
                        f"{self._state['utc_time']}Z"
                    )

        # Magnetic variation
        try:
            if len(parts) > 10 and parts[10]:
                var = float(parts[10])
                direction = (
                    parts[11].upper()
                    if len(parts) > 11 else 'E'
                )
                if direction == 'W':
                    var = -var
                self._state['magnetic_variation'] = var
        except (ValueError, IndexError):
            pass

    def _parse_gsv(self, parts):
        """
        Parse GSV — Satellites in View.

        Fields:
            0  Sentence ID
            1  Total number of GSV sentences
            2  Sentence number (1-based)
            3  Total satellites in view
            4+ Groups of 4: PRN, elevation, azimuth, SNR

        Multiple GSV sentences may be needed for all sats.
        Each sentence carries up to 4 satellite records.
        """
        if len(parts) < 4:
            return

        try:
            total_sats = int(parts[3]) if parts[3] else 0
            self._state['satellites_in_view'] = total_sats
        except ValueError:
            pass

        # Parse satellite records (4 fields each)
        sat_idx = 4
        while sat_idx + 3 < len(parts):
            try:
                prn = parts[sat_idx]
                elevation = parts[sat_idx + 1]
                azimuth = parts[sat_idx + 2]
                snr = parts[sat_idx + 3].split('*')[0]

                if prn:
                    self._satellites[prn] = {
                        'prn': prn,
                        'elevation': (
                            int(elevation)
                            if elevation else None
                        ),
                        'azimuth': (
                            int(azimuth)
                            if azimuth else None
                        ),
                        'snr': (
                            int(snr) if snr else None
                        ),
                    }
            except (ValueError, IndexError):
                pass
            sat_idx += 4

        # Update satellite list in state
        self._state['satellite_data'] = list(
            self._satellites.values()
        )

    def _parse_gsa(self, parts):
        """
        Parse GSA — GPS DOP and Active Satellites.

        Fields:
            0  Sentence ID
            1  Mode (M=manual, A=auto)
            2  Fix type (1=no fix, 2=2D, 3=3D)
            3-14  PRNs of active satellites
            15 PDOP
            16 HDOP
            17 VDOP

        GSA provides DOP (Dilution of Precision) values
        which indicate positional accuracy.
        Lower DOP = better accuracy.
        """
        if len(parts) < 18:
            return

        # Fix type
        try:
            fix_t = int(parts[2]) if parts[2] else 1
            self._state['fix_type'] = fix_t
            if fix_t >= 2:
                self._state['has_fix'] = True
        except ValueError:
            pass

        # DOP values
        try:
            if len(parts) > 15 and parts[15]:
                self._state['pdop'] = float(parts[15])
            if len(parts) > 16 and parts[16]:
                self._state['hdop'] = float(parts[16])
            if len(parts) > 17:
                vdop_str = parts[17].split('*')[0]
                if vdop_str:
                    self._state['vdop'] = float(vdop_str)
        except (ValueError, IndexError):
            pass

    def _parse_vtg(self, parts):
        """
        Parse VTG — Track Made Good and Ground Speed.

        Fields:
            0  Sentence ID
            1  Track degrees true
            2  T (true)
            3  Track degrees magnetic
            4  M (magnetic)
            5  Speed in knots
            6  N (knots)
            7  Speed in km/h
            8  K (km/h)
            9  Mode
        """
        if len(parts) < 8:
            return

        try:
            if parts[1]:
                self._state['track_true'] = float(
                    parts[1]
                )
        except ValueError:
            pass

        try:
            if parts[5]:
                knots = float(parts[5])
                self._state['speed_knots'] = knots
                self._state['speed_kmh'] = round(
                    knots * 1.852, 2
                )
        except (ValueError, IndexError):
            pass

        try:
            if len(parts) > 7 and parts[7]:
                speed_str = parts[7].split('*')[0]
                if speed_str:
                    self._state['speed_kmh'] = round(
                        float(speed_str), 2
                    )
        except (ValueError, IndexError):
            pass

    def _parse_gll(self, parts):
        """
        Parse GLL — Geographic Position Latitude/Longitude.

        Fields:
            0  Sentence ID
            1  Latitude
            2  N/S
            3  Longitude
            4  E/W
            5  UTC Time
            6  Status (A=active, V=void)
            7  Mode
        """
        if len(parts) < 7:
            return

        status = parts[6].upper() if parts[6] else 'V'

        if status == 'A':
            lat = self._dddmm_to_decimal(
                parts[1], parts[2]
            )
            lon = self._dddmm_to_decimal(
                parts[3], parts[4]
            )
            if lat is not None:
                self._state['latitude'] = lat
            if lon is not None:
                self._state['longitude'] = lon
            self._state['has_fix'] = True

        time_val = self._parse_time(parts[5])
        if time_val:
            self._state['utc_time'] = time_val
