"""
Callsign Database Models
=========================
SQLAlchemy models for the Canadian ISED amateur radio
operator database.

Qualification codes (from readme_amat_delim.txt):
    A = Basic
    B = 5 WPM Morse
    C = 12 WPM Morse
    D = Advanced
    E = Basic with Honours

Delimiter: semicolon (;)
"""

from datetime import datetime
from models import db


class CanadianOperator(db.Model):
    """
    Canadian amateur radio operator record from ISED.

    Field positions match the semicolon-delimited format
    defined in readme_amat_delim.txt exactly.
    """

    __tablename__ = 'canadian_operators'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Field 0: Callsign — unique, indexed
    callsign = db.Column(
        db.String(20),
        unique=True,
        nullable=False,
        index=True
    )

    # Fields 1-2: Name
    given_names = db.Column(db.String(150), nullable=True)
    surname = db.Column(db.String(100), nullable=True)

    # Fields 3-6: Address
    street_address = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    province = db.Column(db.String(5), nullable=True)
    postal_code = db.Column(db.String(10), nullable=True)

    # Fields 7-11: Qualifications (A through E)
    qual_basic = db.Column(
        db.Boolean, default=False, nullable=False
    )         # A
    qual_morse_5wpm = db.Column(
        db.Boolean, default=False, nullable=False
    )    # B
    qual_morse_12wpm = db.Column(
        db.Boolean, default=False, nullable=False
    )   # C
    qual_advanced = db.Column(
        db.Boolean, default=False, nullable=False
    )     # D
    qual_honours = db.Column(
        db.Boolean, default=False, nullable=False
    )      # E

    # Fields 12-17: Club information
    club_name_1 = db.Column(db.String(200), nullable=True)
    club_name_2 = db.Column(db.String(200), nullable=True)
    club_address = db.Column(db.String(200), nullable=True)
    club_city = db.Column(db.String(100), nullable=True)
    club_province = db.Column(db.String(5), nullable=True)
    club_postal_code = db.Column(db.String(10), nullable=True)

    # Metadata
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    QUAL_LABELS = {
        'A': 'Basic',
        'B': '5 WPM Morse',
        'C': '12 WPM Morse',
        'D': 'Advanced',
        'E': 'Basic with Honours',
    }

    QUAL_BADGE_COLOURS = {
        'A': 'primary',
        'B': 'info',
        'C': 'success',
        'D': 'danger',
        'E': 'warning',
    }

    QUAL_BADGE_ICONS = {
        'A': 'certificate',
        'B': 'dot-circle',
        'C': 'dot-circle',
        'D': 'star',
        'E': 'award',
    }

    def get_full_name(self):
        """Return display name for operator or club."""
        club = self.club_name_1 or self.club_name_2
        if club and club.strip():
            return club.strip()

        parts = []
        if self.given_names and self.given_names.strip():
            parts.append(self.given_names.strip().title())
        if self.surname and self.surname.strip():
            parts.append(self.surname.strip().upper())

        return ' '.join(parts) if parts else 'Unknown'

    def get_held_qualifications(self):
        """Return list of held qualification codes."""
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
        """Return human-readable qualification names."""
        return [
            self.QUAL_LABELS[c]
            for c in self.get_held_qualifications()
        ]

    def get_qualification_badges(self):
        """Return badge data dicts for UI rendering."""
        return [
            {
                'code': c,
                'label': self.QUAL_LABELS[c],
                'colour': self.QUAL_BADGE_COLOURS[c],
                'icon': self.QUAL_BADGE_ICONS[c],
            }
            for c in self.get_held_qualifications()
        ]

    def is_club(self):
        """Return True if this is a club callsign."""
        return bool(
            (self.club_name_1 and self.club_name_1.strip()) or
            (self.club_name_2 and self.club_name_2.strip())
        )

    def get_location_display(self):
        """Return formatted city, province string."""
        city = self.club_city if self.is_club() else self.city
        prov = (
            self.club_province
            if self.is_club() else self.province
        )
        parts = []
        if city and city.strip():
            parts.append(city.strip().title())
        if prov and prov.strip():
            parts.append(prov.strip().upper())
        return ', '.join(parts) if parts else ''

    def to_dict(self):
        """Serialise to dictionary for JSON responses."""
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
            'qual_codes': self.get_held_qualifications(),
            'qualifications': self.get_qualification_labels(),
            'qualification_badges': (
                self.get_qualification_badges()
            ),
            'qual_basic': self.qual_basic,
            'qual_morse_5wpm': self.qual_morse_5wpm,
            'qual_morse_12wpm': self.qual_morse_12wpm,
            'qual_advanced': self.qual_advanced,
            'qual_honours': self.qual_honours,
            'is_club': self.is_club(),
            'club_name_1': self.club_name_1,
            'club_name_2': self.club_name_2,
        }

    def __repr__(self):
        return (
            f'<CanadianOperator {self.callsign} '
            f'{self.get_full_name()}>'
        )


class DatabaseMeta(db.Model):
    """
    Key/value metadata for the callsign database.

    Tracks download status, record counts, timestamps
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
        Get a metadata value by key.

        Args:
            key: Lookup key string
            default: Value to return if key not found

        Returns:
            str: Stored value or default
        """
        try:
            record = DatabaseMeta.query.filter_by(
                key=key
            ).first()
            return record.value if record else default
        except Exception:
            return default

    @staticmethod
    def set(key, value):
        """
        Set a metadata key/value pair.

        Imports db inside the method to avoid circular
        import issues. Uses merge() pattern to handle
        both insert and update safely.

        Args:
            key: Metadata key string
            value: Value to store (converted to str)
        """
        # Import db here to avoid circular imports
        from models import db as _db

        try:
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

        except Exception as e:
            print(
                f"[DatabaseMeta] Error setting "
                f"{key}={value}: {e}"
            )
            try:
                from models import db as _db2
                _db2.session.rollback()
            except Exception:
                pass
