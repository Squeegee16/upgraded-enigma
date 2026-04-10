"""
Contact Log Model
=================
Defines the ContactLog model for storing radio contacts.
Supports standard ham radio contact fields.
"""

from models import db
from datetime import datetime

class ContactLog(db.Model):
    """
    Contact log model for storing radio communications.
    
    Attributes:
        id: Primary key
        operator_id: Foreign key to User
        contact_callsign: Callsign of contacted station
        mode: Communication mode (SSB, CW, FT8, etc.)
        band: Frequency band (e.g., "20m", "2m")
        frequency: Actual frequency in MHz
        grid: Maidenhead grid locator
        timestamp: Contact date/time
        signal_report_sent: Signal report sent (e.g., "59")
        signal_report_rcvd: Signal report received
        notes: Optional notes about the contact
    """
    
    __tablename__ = 'contact_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Contact Information
    contact_callsign = db.Column(db.String(20), nullable=False, index=True)
    mode = db.Column(db.String(20), nullable=False, index=True)
    band = db.Column(db.String(10), nullable=True, index=True)
    frequency = db.Column(db.Float, nullable=True)  # in MHz
    
    # Location
    grid = db.Column(db.String(10), nullable=True, index=True)  # Maidenhead locator
    
    # Time
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Signal Reports
    signal_report_sent = db.Column(db.String(10), nullable=True)
    signal_report_rcvd = db.Column(db.String(10), nullable=True)
    
    # Additional Information
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Common modes for validation
    VALID_MODES = [
        'SSB', 'USB', 'LSB', 'CW', 'FM', 'AM',
        'FT8', 'FT4', 'PSK31', 'RTTY', 'SSTV',
        'DSTAR', 'DMR', 'C4FM', 'PACKET'
    ]
    
    # Common bands
    VALID_BANDS = [
        '2200m', '630m', '160m', '80m', '60m', '40m',
        '30m', '20m', '17m', '15m', '12m', '10m',
        '6m', '4m', '2m', '1.25m', '70cm', '33cm', '23cm'
    ]
    
    def to_dict(self):
        """
        Convert contact log to dictionary for export.
        
        Returns:
            dict: Contact log data
        """
        return {
            'id': self.id,
            'callsign': self.contact_callsign,
            'mode': self.mode,
            'band': self.band,
            'frequency': self.frequency,
            'grid': self.grid,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'signal_report_sent': self.signal_report_sent,
            'signal_report_rcvd': self.signal_report_rcvd,
            'notes': self.notes
        }
    
    def __repr__(self):
        return f'<ContactLog {self.contact_callsign} on {self.band} {self.mode}>'