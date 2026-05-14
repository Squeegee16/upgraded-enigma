"""
Maidenhead Grid Square Calculator
===================================
Calculates the Maidenhead Locator grid square from
WGS84 latitude and longitude coordinates entirely
offline — no internet connection required.

The Maidenhead Locator System divides the Earth into
a hierarchy of rectangles:

    Field (2 letters):
        Longitude divided into 20 fields of 18° each.
        Latitude divided into 20 fields of 10° each.
        Letters A-R (e.g. FN, EM, IO)

    Square (2 digits):
        Each field divided into 10x10 squares.
        Digits 0-9 (e.g. FN20, EM72)

    Subsquare (2 letters, lowercase):
        Each square divided into 24x24 subsquares.
        Letters a-x (e.g. FN20cr, EM72ab)

    Extended square (2 digits, optional):
        Each subsquare divided into 10x10.
        (e.g. FN20cr22)

Standard precision for ham radio use is 4 or 6
characters. This module supports up to 8 characters
(extended square).

Reference:
    QTH Locator / Maidenhead Grid Square Locator
    IARU Region 1 Technical Recommendation T/R 23-01

Usage:
    from devices.grid_square import GridSquareCalculator

    calc = GridSquareCalculator()
    grid = calc.from_latlon(45.5017, -73.5673)
    # Returns: 'FN35pm' (Montreal, QC)

    lat, lon = calc.to_latlon('FN20')
    # Returns: (40.0, -74.0)  (centre of FN20)
"""


class GridSquareCalculator:
    """
    Converts between WGS84 coordinates and Maidenhead
    grid squares with no external dependencies.

    All calculations are pure Python arithmetic.
    No internet connection required.
    """

    # Character sets for each precision level
    FIELD_CHARS = 'ABCDEFGHIJKLMNOPQR'        # 18 fields
    SQUARE_CHARS = '0123456789'                # 10 squares
    SUBSQUARE_CHARS = 'abcdefghijklmnopqrstuvwx'  # 24 sub
    EXT_CHARS = '0123456789'                   # 10 extended

    def from_latlon(self, latitude, longitude,
                    precision=6):
        """
        Calculate Maidenhead grid square from coordinates.

        Args:
            latitude:  WGS84 latitude  (-90.0 to +90.0)
            longitude: WGS84 longitude (-180.0 to +180.0)
            precision: Grid square length (2, 4, 6, or 8)
                       2 = field only          (e.g. 'FN')
                       4 = field + square      (e.g. 'FN20')
                       6 = + subsquare         (e.g. 'FN20cr')
                       8 = + extended square   (e.g. 'FN20cr22')

        Returns:
            str: Maidenhead grid square string

        Raises:
            ValueError: If coordinates are out of range
                        or precision is invalid
        """
        # Validate inputs
        if not -90.0 <= latitude <= 90.0:
            raise ValueError(
                f"Latitude {latitude} out of range "
                f"(-90 to +90)"
            )
        if not -180.0 <= longitude <= 180.0:
            raise ValueError(
                f"Longitude {longitude} out of range "
                f"(-180 to +180)"
            )
        if precision not in (2, 4, 6, 8):
            raise ValueError(
                f"Precision must be 2, 4, 6, or 8, "
                f"got {precision}"
            )

        # Clamp to valid range (handle exact boundary)
        lat = min(latitude, 89.9999)
        lon = min(longitude, 179.9999)

        # -------------------------------------------------------
        # Normalise: shift origin to (0,0) at (-180, -90)
        # Working range: longitude 0-360, latitude 0-180
        # -------------------------------------------------------
        adj_lon = lon + 180.0   # 0 to 360
        adj_lat = lat + 90.0    # 0 to 180

        # -------------------------------------------------------
        # Field (characters 1-2): A-R
        #   Longitude: 20 fields × 18° = 360°
        #   Latitude:  20 fields × 10° = 200° (but 180° used)
        # -------------------------------------------------------
        field_lon_idx = int(adj_lon / 20.0)
        field_lat_idx = int(adj_lat / 10.0)

        field_lon = self.FIELD_CHARS[field_lon_idx]
        field_lat = self.FIELD_CHARS[field_lat_idx]

        if precision == 2:
            return field_lon + field_lat

        # Remainder within the field
        rem_lon = adj_lon - field_lon_idx * 20.0  # 0-20°
        rem_lat = adj_lat - field_lat_idx * 10.0  # 0-10°

        # -------------------------------------------------------
        # Square (characters 3-4): 0-9
        #   Longitude: 10 squares × 2°  = 20°
        #   Latitude:  10 squares × 1°  = 10°
        # -------------------------------------------------------
        sq_lon_idx = int(rem_lon / 2.0)
        sq_lat_idx = int(rem_lat / 1.0)

        sq_lon = self.SQUARE_CHARS[sq_lon_idx]
        sq_lat = self.SQUARE_CHARS[sq_lat_idx]

        if precision == 4:
            return (
                field_lon + field_lat +
                sq_lon + sq_lat
            )

        # Remainder within the square
        rem_lon2 = rem_lon - sq_lon_idx * 2.0    # 0-2°
        rem_lat2 = rem_lat - sq_lat_idx * 1.0    # 0-1°

        # -------------------------------------------------------
        # Subsquare (characters 5-6): a-x
        #   Longitude: 24 subsquares × (2/24)° = 2°
        #   Latitude:  24 subsquares × (1/24)° = 1°
        # -------------------------------------------------------
        sub_lon_idx = int(rem_lon2 / (2.0 / 24.0))
        sub_lat_idx = int(rem_lat2 / (1.0 / 24.0))

        # Clamp to valid index (handle floating point edge)
        sub_lon_idx = min(sub_lon_idx, 23)
        sub_lat_idx = min(sub_lat_idx, 23)

        sub_lon = self.SUBSQUARE_CHARS[sub_lon_idx]
        sub_lat = self.SUBSQUARE_CHARS[sub_lat_idx]

        if precision == 6:
            return (
                field_lon + field_lat +
                sq_lon + sq_lat +
                sub_lon + sub_lat
            )

        # Remainder within the subsquare
        sub_lon_size = 2.0 / 24.0    # ~0.0833°
        sub_lat_size = 1.0 / 24.0    # ~0.0417°

        rem_lon3 = rem_lon2 - sub_lon_idx * sub_lon_size
        rem_lat3 = rem_lat2 - sub_lat_idx * sub_lat_size

        # -------------------------------------------------------
        # Extended square (characters 7-8): 0-9
        #   Longitude: 10 × (sub_lon_size/10)
        #   Latitude:  10 × (sub_lat_size/10)
        # -------------------------------------------------------
        ext_lon_idx = int(rem_lon3 / (sub_lon_size / 10.0))
        ext_lat_idx = int(rem_lat3 / (sub_lat_size / 10.0))

        ext_lon_idx = min(ext_lon_idx, 9)
        ext_lat_idx = min(ext_lat_idx, 9)

        ext_lon = self.EXT_CHARS[ext_lon_idx]
        ext_lat = self.EXT_CHARS[ext_lat_idx]

        return (
            field_lon + field_lat +
            sq_lon + sq_lat +
            sub_lon + sub_lat +
            ext_lon + ext_lat
        )

    def to_latlon(self, grid, position='center'):
        """
        Convert a Maidenhead grid square to WGS84 coordinates.

        Returns the coordinates of the specified position
        within the grid square.

        Args:
            grid: Maidenhead grid square (2-8 characters)
            position: 'center', 'southwest', 'northeast'

        Returns:
            tuple: (latitude, longitude) in decimal degrees

        Raises:
            ValueError: If grid string is invalid
        """
        grid = grid.strip()
        length = len(grid)

        if length < 2 or length % 2 != 0 or length > 8:
            raise ValueError(
                f"Invalid grid length: {length}. "
                f"Must be 2, 4, 6, or 8 characters."
            )

        grid_upper = grid.upper()

        # -------------------------------------------------------
        # Field (chars 1-2)
        # -------------------------------------------------------
        f_lon = self.FIELD_CHARS.find(grid_upper[0])
        f_lat = self.FIELD_CHARS.find(grid_upper[1])

        if f_lon < 0 or f_lat < 0:
            raise ValueError(
                f"Invalid field characters: "
                f"'{grid[0]}', '{grid[1]}'. "
                f"Expected A-R."
            )

        lon = f_lon * 20.0 - 180.0
        lat = f_lat * 10.0 - 90.0

        if length == 2:
            lon += 10.0  # Centre of field
            lat += 5.0
            if position == 'center':
                return lat, lon
            elif position == 'southwest':
                return lat - 5.0, lon - 10.0
            else:  # northeast
                return lat + 5.0, lon + 10.0

        # -------------------------------------------------------
        # Square (chars 3-4)
        # -------------------------------------------------------
        s_lon = self.SQUARE_CHARS.find(grid_upper[2])
        s_lat = self.SQUARE_CHARS.find(grid_upper[3])

        if s_lon < 0 or s_lat < 0:
            raise ValueError(
                f"Invalid square characters: "
                f"'{grid[2]}', '{grid[3]}'. "
                f"Expected 0-9."
            )

        lon += s_lon * 2.0
        lat += s_lat * 1.0

        if length == 4:
            lon += 1.0   # Centre of square
            lat += 0.5
            if position == 'center':
                return lat, lon
            elif position == 'southwest':
                return lat - 0.5, lon - 1.0
            else:  # northeast
                return lat + 0.5, lon + 1.0

        # -------------------------------------------------------
        # Subsquare (chars 5-6): lowercase a-x
        # -------------------------------------------------------
        sub_lon = self.SUBSQUARE_CHARS.find(
            grid[4].lower()
        )
        sub_lat = self.SUBSQUARE_CHARS.find(
            grid[5].lower()
        )

        if sub_lon < 0 or sub_lat < 0:
            raise ValueError(
                f"Invalid subsquare characters: "
                f"'{grid[4]}', '{grid[5]}'. "
                f"Expected a-x."
            )

        sub_lon_size = 2.0 / 24.0   # ~0.0833°
        sub_lat_size = 1.0 / 24.0   # ~0.0417°

        lon += sub_lon * sub_lon_size
        lat += sub_lat * sub_lat_size

        if length == 6:
            lon += sub_lon_size / 2.0   # Centre
            lat += sub_lat_size / 2.0
            if position == 'center':
                return round(lat, 6), round(lon, 6)
            elif position == 'southwest':
                return (
                    round(lat - sub_lat_size / 2, 6),
                    round(lon - sub_lon_size / 2, 6)
                )
            else:  # northeast
                return (
                    round(lat + sub_lat_size / 2, 6),
                    round(lon + sub_lon_size / 2, 6)
                )

        # -------------------------------------------------------
        # Extended square (chars 7-8)
        # -------------------------------------------------------
        ext_lon = self.EXT_CHARS.find(grid_upper[6])
        ext_lat = self.EXT_CHARS.find(grid_upper[7])

        if ext_lon < 0 or ext_lat < 0:
            raise ValueError(
                f"Invalid extended chars: "
                f"'{grid[6]}', '{grid[7]}'. "
                f"Expected 0-9."
            )

        ext_lon_size = sub_lon_size / 10.0
        ext_lat_size = sub_lat_size / 10.0

        lon += ext_lon * ext_lon_size + ext_lon_size / 2
        lat += ext_lat * ext_lat_size + ext_lat_size / 2

        if position == 'center':
            return round(lat, 8), round(lon, 8)
        elif position == 'southwest':
            return (
                round(lat - ext_lat_size / 2, 8),
                round(lon - ext_lon_size / 2, 8)
            )
        else:  # northeast
            return (
                round(lat + ext_lat_size / 2, 8),
                round(lon + ext_lon_size / 2, 8)
            )

    def distance_km(self, grid1, grid2):
        """
        Calculate the approximate distance between
        two grid squares in kilometres.

        Uses the Haversine formula for accuracy over
        long distances.

        Args:
            grid1: First grid square (4-8 chars)
            grid2: Second grid square (4-8 chars)

        Returns:
            float: Distance in kilometres
        """
        import math

        lat1, lon1 = self.to_latlon(grid1)
        lat2, lon2 = self.to_latlon(grid2)

        # Haversine formula
        R = 6371.0  # Earth radius in km

        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2 +
            math.cos(lat1_r) *
            math.cos(lat2_r) *
            math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a),
                           math.sqrt(1 - a))

        return round(R * c, 1)

    def bearing(self, grid1, grid2):
        """
        Calculate the bearing from grid1 to grid2.

        Args:
            grid1: Origin grid square
            grid2: Destination grid square

        Returns:
            float: Bearing in degrees (0-360, true north)
        """
        import math

        lat1, lon1 = self.to_latlon(grid1)
        lat2, lon2 = self.to_latlon(grid2)

        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlon_r = math.radians(lon2 - lon1)

        x = (math.sin(dlon_r) *
             math.cos(lat2_r))
        y = (math.cos(lat1_r) *
             math.sin(lat2_r) -
             math.sin(lat1_r) *
             math.cos(lat2_r) *
             math.cos(dlon_r))

        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360

    def validate(self, grid):
        """
        Validate a grid square string.

        Args:
            grid: Grid square to validate

        Returns:
            tuple: (valid: bool, error_message: str)
        """
        if not grid:
            return False, "Empty grid square"

        grid = grid.strip()
        length = len(grid)

        if length < 2:
            return False, "Too short (minimum 2 chars)"

        if length % 2 != 0:
            return (
                False,
                f"Odd length ({length}): "
                f"must be even"
            )

        if length > 8:
            return False, "Too long (maximum 8 chars)"

        # Check field (chars 1-2)
        if grid[0].upper() not in self.FIELD_CHARS:
            return (
                False,
                f"Invalid field lon '{grid[0]}' "
                f"(expected A-R)"
            )
        if grid[1].upper() not in self.FIELD_CHARS:
            return (
                False,
                f"Invalid field lat '{grid[1]}' "
                f"(expected A-R)"
            )

        # Check square (chars 3-4)
        if length >= 4:
            if grid[2] not in self.SQUARE_CHARS:
                return (
                    False,
                    f"Invalid square lon '{grid[2]}' "
                    f"(expected 0-9)"
                )
            if grid[3] not in self.SQUARE_CHARS:
                return (
                    False,
                    f"Invalid square lat '{grid[3]}' "
                    f"(expected 0-9)"
                )

        # Check subsquare (chars 5-6)
        if length >= 6:
            if grid[4].lower() not in \
                    self.SUBSQUARE_CHARS:
                return (
                    False,
                    f"Invalid subsquare lon '{grid[4]}'"
                    f" (expected a-x)"
                )
            if grid[5].lower() not in \
                    self.SUBSQUARE_CHARS:
                return (
                    False,
                    f"Invalid subsquare lat '{grid[5]}'"
                    f" (expected a-x)"
                )

        # Check extended (chars 7-8)
        if length == 8:
            if grid[6] not in self.EXT_CHARS:
                return (
                    False,
                    f"Invalid extended lon '{grid[6]}' "
                    f"(expected 0-9)"
                )
            if grid[7] not in self.EXT_CHARS:
                return (
                    False,
                    f"Invalid extended lat '{grid[7]}' "
                    f"(expected 0-9)"
                )

        return True, ""


# Module-level convenience instance
_calculator = GridSquareCalculator()


def latlon_to_grid(latitude, longitude, precision=6):
    """
    Convert latitude/longitude to Maidenhead grid square.

    Module-level convenience function.

    Args:
        latitude: WGS84 latitude in decimal degrees
        longitude: WGS84 longitude in decimal degrees
        precision: Grid precision (2, 4, 6, or 8)

    Returns:
        str: Maidenhead grid square or '' on error
    """
    try:
        return _calculator.from_latlon(
            latitude, longitude, precision
        )
    except Exception as e:
        print(f"[GridSquare] Error: {e}")
        return ''


def grid_to_latlon(grid):
    """
    Convert Maidenhead grid square to lat/lon.

    Module-level convenience function.

    Args:
        grid: Maidenhead grid square string

    Returns:
        tuple: (latitude, longitude) or (None, None)
    """
    try:
        return _calculator.to_latlon(grid)
    except Exception as e:
        print(f"[GridSquare] Error: {e}")
        return None, None
