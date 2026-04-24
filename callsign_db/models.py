"""
Callsign Database SQLAlchemy Model
====================================
Stores Canadian amateur radio operator records from
the ISED amateur_delim.zip database.

Field Reference (from readme_amat_delim.txt):
    Each record is semicolon-delimited with fields:

    Position  Field
    --------  -----
    0         Callsign
    1         Given Names
    2         Surname
    3         Street Address
    4         City
    5         Province
    6         Postal/ZIP Code
    7         BASIC Qualification         (A) - True/False
    8         5WPM Qualification          (B) - True/False
    9         12WPM Qualification         (C) - True/False
    10        ADVANCED Qualification      (D) - True/False
    11        Basic with Honours          (E) - True/False
    12        Club Name (field 1)
    13        Club Name (field 2)
    14        Club Address
    15        Club City
    16        Club Province
    17        Club Postal/ZIP Code

Qualification Letter Codes (stored in fields 7-11):
    A  =  Basic
    B  =  5 WPM Morse Code
    C  =  12 WPM Morse Code
    D  =  Advanced
    E  =  Basic with Honours

Source: https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip
"""

from datetime import datetime
from models import db


class CanadianOperator(db.Model):
    """
    Canadian amateur radio operator record.

    Reflects the exact structure of the ISED
    amateur_delim.zip semicolon-delimited file.

    Qualification fields store True/False based on
    whether the single letter code (A-E) is present
    in the corresponding field of the source file.
    """

    __tablename__ = 'canadian_operators'

    # -----------------------------------------------------------
    # Primary Key
    # -----------------------------------------------------------
    id = db.Column(db.Integer, primary_key=True)

    # -----------------------------------------------------------
    # Callsign - unique, indexed for fast lookup
    # -----------------------------------------------------------
    callsign = db.Column(
        db.String(20),
        unique=True,
        nullable=False,
        index=True
    )

    # -----------------------------------------------------------
    # Operator Identity
    # Fields 1 and 2 from source file
    # -----------------------------------------------------------
    given_names = db.Column(db.String(150), nullable=True)
    surname = db.Column(db.String(100), nullable=True)

    # -----------------------------------------------------------
    # Address
    # Fields 3-6 from source file
    # -----------------------------------------------------------
    street_address = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    province = db.Column(db.String(5), nullable=True)
    postal_code = db.Column(db.String(10), nullable=True)

    # -----------------------------------------------------------
    # Qualifications
    # Fields 7-11 from source file
    # Each field contains the letter code if held, or is blank
    #
    #   qual_basic        (A) - Basic qualification
    #   qual_morse_5wpm   (B) - 5 WPM Morse code
    #   qual_morse_12wpm  (C) - 12 WPM Morse code
    #   qual_advanced     (D) - Advanced qualification
    #   qual_honours      (E) - Basic with Honours
    # -----------------------------------------------------------
    qual_basic = db.Column(
        db.Boolean, default=False, nullable=False
    )
    qual_morse_5wpm = db.Column(
        db.Boolean, default=False, nullable=False
    )
    qual_morse_12wpm = db.Column(
        db.Boolean, default=False, nullable=False
    )
    qual_advanced = db.Column(
        db.Boolean, default=False, nullable=False
    )
    qual_honours = db.Column(
        db.Boolean, default=False, nullable=False
    )

    # -----------------------------------------------------------
    # Club Information
    # Fields 12-17 from source file
    # Only populated for club/repeater callsigns
    # -----------------------------------------------------------
    club_name_1 = db.Column(db.String(200), nullable=True)
    club_name_2 = db.Column(db.String(200), nullable=True)
    club_address = db.Column(db.String(200), nullable=True)
    club_city = db.Column(db.String(100), nullable=True)
    club_province = db.Column(db.String(5), nullable=True)
    club_postal_code = db.Column(db.String(10), nullable=True)

    # -----------------------------------------------------------
    # Record Metadata
    # -----------------------------------------------------------
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # -----------------------------------------------------------
    # Qualification display label map
    # Maps field letter -> human readable string
    # -----------------------------------------------------------
    QUAL_LABELS = {
        'A': 'Basic',
        'B': '5 WPM Morse',
        'C': '12 WPM Morse',
        'D': 'Advanced',
        'E': 'Basic with Honours',
    }

    # -----------------------------------------------------------
    # Badge colour map for UI display
    # -----------------------------------------------------------
    QUAL_BADGE_COLOURS = {
        'A': 'primary',    # Basic        -> blue
        'B': 'info',       # 5 WPM Morse  -> cyan
        'C': 'success',    # 12 WPM Morse -> green
        'D': 'danger',     # Advanced     -> red
        'E': 'warning',    # Honours      -> yellow
    }

    # Badge icon map
    QUAL_BADGE_ICONS = {
        'A': 'certificate',
        'B': 'dot-circle',
        'C': 'dot-circle',
        'D': 'star',
        'E': 'award',
    }

    def get_full_name(self):
        """
        Get operator's full name in display format.

        For individual operators: Given Names + SURNAME
        For club callsigns: Club Name (field 1) or field 2

        Returns:
            str: Full name string or 'Unknown'
        """
        # Check for club callsign first
        club = self.club_name_1 or self.club_name_2
        if club and club.strip():
            return club.strip()

        # Individual operator
        parts = []
        if self.given_names and self.given_names.strip():
            # Title-case given names
            parts.append(self.given_names.strip().title())
        if self.surname and self.surname.strip():
            # Upper-case surname (Canadian convention)
            parts.append(self.surname.strip().upper())

        return ' '.join(parts) if parts else 'Unknown'

    def get_held_qualifications(self):
        """
        Get list of qualification letter codes held.

        Returns codes in the defined order A -> E.

        Returns:
            list: Letter codes for held qualifications
                  e.g. ['A', 'D'] for Basic + Advanced
        """
        held = []

        if self.qual_basic:
            held.append('A')
        if self.qual_morse_5wpm:
            held.append('B')
        if self.qual_morse_12wpm:
            held.append('C')
        if self.qual_advanced:
            held.append('D')
        if self.qual_honours:
            held.append('E')

        return held

    def get_qualification_labels(self):
        """
        Get human-readable qualification label strings.

        Returns:
            list: Qualification name strings
                  e.g. ['Basic', 'Advanced']
        """
        return [
            self.QUAL_LABELS[code]
            for code in self.get_held_qualifications()
        ]

    def get_qualification_badges(self):
        """
        Get qualification badge data for UI rendering.

        Each badge has label, colour, icon, and code
        for flexible template rendering.

        Returns:
            list: Badge dictionaries with display data
        """
        badges = []
        for code in self.get_held_qualifications():
            badges.append({
                'code': code,
                'label': self.QUAL_LABELS[code],
                'colour': self.QUAL_BADGE_COLOURS[code],
                'icon': self.QUAL_BADGE_ICONS[code],
            })
        return badges

    def is_club(self):
        """
        Determine if this is a club callsign.

        Returns:
            bool: True if club_name_1 or club_name_2 present
        """
        return bool(
            (self.club_name_1 and self.club_name_1.strip()) or
            (self.club_name_2 and self.club_name_2.strip())
        )

    def get_location_display(self):
        """
        Get formatted location string for display.

        Returns:
            str: 'City, Province' or whichever is available
        """
        parts = []
        city = (
            self.club_city if self.is_club() else self.city
        )
        province = (
            self.club_province
            if self.is_club() else self.province
        )

        if city and city.strip():
            parts.append(city.strip().title())
        if province and province.strip():
            parts.append(province.strip().upper())

        return ', '.join(parts) if parts else ''

    def to_dict(self):
        """
        Serialise record to dictionary for JSON responses.

        Returns:
            dict: Complete operator record
        """
        return {
            'callsign': self.callsign,
            'full_name': self.get_full_name(),
            'given_names': self.given_names,
            'surname': self.surname,
            'street_address': self.street_address,
            'city': self.city,
            'province': self.province,
            'postal_code': self.postal_code,
            'location': self.get_location_display(),
            # Qualification codes held (e.g. ['A', 'D'])
            'qual_codes': self.get_held_qualifications(),
            # Human readable names
            'qualifications': self.get_qualification_labels(),
            # Badge data for UI
            'qualification_badges': (
                self.get_qualification_badges()
            ),
            # Individual flags
            'qual_basic': self.qual_basic,
            'qual_morse_5wpm': self.qual_morse_5wpm,
            'qual_morse_12wpm': self.qual_morse_12wpm,
            'qual_advanced': self.qual_advanced,
            'qual_honours': self.qual_honours,
            # Club fields
            'is_club': self.is_club(),
            'club_name_1': self.club_name_1,
            'club_name_2': self.club_name_2,
            'club_address': self.club_address,
            'club_city': self.club_city,
            'club_province': self.club_province,
        }

    def __repr__(self):
        return (
            f'<CanadianOperator {self.callsign} '
            f'{self.get_full_name()}>'
        )


class DatabaseMeta(db.Model):
    """
    Key/value metadata for the callsign database.

    Tracks download status, record count, timestamps,
    and source information.
    """

    __tablename__ = 'canadian_db_meta'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(
        db.String(50), unique=True, nullable=False
    )
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    @staticmethod
    def get(key, default=None):
        """
        Get metadata value by key.

        Args:
            key: Metadata key string
            default: Default if key not found

        Returns:
            str: Stored value or default
        """
        record = DatabaseMeta.query.filter_by(
            key=key
        ).first()
        return record.value if record else default

    @staticmethod
    def set(key, value):
        """
        Set a metadata key/value pair.

        Args:
            key: Metadata key string
            value: Value to store (converted to str)
        """
        from models import db as _db

        record = DatabaseMeta.query.filter_by(
            key=key
        ).first()

        if record:
            record.value = str(value)
            record.updated_at = datetime.utcnow()
        else:
            record = DatabaseMeta(
                key=key,
                value=str(value)
            )
            _db.session.add(record)

        _db.session.commit()
