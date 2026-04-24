"""
Callsign Database SQLAlchemy Model
====================================
Defines the SQLAlchemy model for storing Canadian
amateur radio operator records from the ISED database.

The model uses a separate SQLite database file from
the main application database for performance and
to allow easy replacement when the ISED data is updated.

Fields mirror the ISED amateur_delim.zip structure.
"""

from datetime import datetime
from models import db


class CanadianOperator(db.Model):
    """
    Canadian amateur radio operator record.

    Stores data from the ISED amateur radio database
    (https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip).

    Attributes:
        id: Primary key
        callsign: Amateur radio callsign (indexed, unique)
        surname: Operator surname
        given_name: Operator given name(s)
        city: City of licence
        province: Province/Territory abbreviation
        postal_code: Canadian postal code
        qual_basic: Basic qualification flag
        qual_advanced: Advanced qualification flag
        qual_honours: Basic with Honours flag
        qual_morse_5: Morse code 5 WPM flag
        qual_morse_12: Morse code 12 WPM flag
        club_name: Club name (for club callsigns)
        expiry_date: Licence expiry date string
        created_at: Record creation timestamp
        updated_at: Record last update timestamp
    """

    __tablename__ = 'canadian_operators'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Callsign - indexed for fast lookup
    callsign = db.Column(
        db.String(20),
        unique=True,
        nullable=False,
        index=True
    )

    # Operator name
    surname = db.Column(db.String(100), nullable=True)
    given_name = db.Column(db.String(100), nullable=True)

    # Location
    city = db.Column(db.String(100), nullable=True)
    province = db.Column(db.String(5), nullable=True)
    postal_code = db.Column(db.String(10), nullable=True)

    # Qualifications (stored as booleans from qualification codes)
    qual_basic = db.Column(db.Boolean, default=False)
    qual_advanced = db.Column(db.Boolean, default=False)
    qual_honours = db.Column(db.Boolean, default=False)
    qual_morse_5 = db.Column(db.Boolean, default=False)
    qual_morse_12 = db.Column(db.Boolean, default=False)

    # Raw qualification string for display
    qualifications = db.Column(db.String(50), nullable=True)

    # Club information
    club_name = db.Column(db.String(200), nullable=True)

    # Licence details
    expiry_date = db.Column(db.String(20), nullable=True)

    # Record metadata
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def get_full_name(self):
        """
        Get operator's full name.

        Returns:
            str: Full name (Given Name + Surname) or
                 club name for club callsigns
        """
        if self.club_name:
            return self.club_name

        parts = []
        if self.given_name:
            parts.append(self.given_name.strip())
        if self.surname:
            parts.append(self.surname.strip().upper())

        return ' '.join(parts) if parts else 'Unknown'

    def get_qualification_list(self):
        """
        Get list of qualification names.

        Returns:
            list: Human-readable qualification strings
        """
        quals = []

        if self.qual_advanced:
            quals.append('Advanced')
        if self.qual_honours:
            quals.append('Basic with Honours')
        elif self.qual_basic:
            quals.append('Basic')
        if self.qual_morse_12:
            quals.append('Morse 12 WPM')
        elif self.qual_morse_5:
            quals.append('Morse 5 WPM')

        return quals

    def get_qualification_badges(self):
        """
        Get qualification badge data for UI display.

        Returns:
            list: Dicts with 'label' and 'colour' keys
        """
        badges = []

        if self.qual_advanced:
            badges.append({
                'label': 'Advanced',
                'colour': 'danger',
                'icon': 'star'
            })
        if self.qual_honours:
            badges.append({
                'label': 'Basic Honours',
                'colour': 'warning',
                'icon': 'award'
            })
        elif self.qual_basic:
            badges.append({
                'label': 'Basic',
                'colour': 'primary',
                'icon': 'certificate'
            })
        if self.qual_morse_12:
            badges.append({
                'label': 'Morse 12 WPM',
                'colour': 'success',
                'icon': 'dot-circle'
            })
        elif self.qual_morse_5:
            badges.append({
                'label': 'Morse 5 WPM',
                'colour': 'info',
                'icon': 'dot-circle'
            })

        return badges

    def to_dict(self):
        """
        Convert record to dictionary for JSON serialisation.

        Returns:
            dict: Operator data
        """
        return {
            'callsign': self.callsign,
            'full_name': self.get_full_name(),
            'surname': self.surname,
            'given_name': self.given_name,
            'city': self.city,
            'province': self.province,
            'postal_code': self.postal_code,
            'qualifications': self.get_qualification_list(),
            'qualification_badges': self.get_qualification_badges(),
            'club_name': self.club_name,
            'expiry_date': self.expiry_date,
            'is_club': bool(self.club_name),
        }

    def __repr__(self):
        return (
            f'<CanadianOperator {self.callsign} - '
            f'{self.get_full_name()}>'
        )


class DatabaseMeta(db.Model):
    """
    Metadata table for tracking database download status.

    Stores information about when the ISED database
    was last downloaded and how many records it contains.
    """

    __tablename__ = 'canadian_db_meta'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    @staticmethod
    def get(key, default=None):
        """
        Get a metadata value by key.

        Args:
            key: Metadata key string
            default: Default value if not found

        Returns:
            str: Metadata value or default
        """
        record = DatabaseMeta.query.filter_by(key=key).first()
        return record.value if record else default

    @staticmethod
    def set(key, value):
        """
        Set a metadata value.

        Args:
            key: Metadata key string
            value: Value to store
        """
        record = DatabaseMeta.query.filter_by(key=key).first()
        if record:
            record.value = str(value)
            record.updated_at = datetime.utcnow()
        else:
            record = DatabaseMeta(key=key, value=str(value))
            db.session.add(record)
        db.session.commit()