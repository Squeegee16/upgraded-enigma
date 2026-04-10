"""
Logbook Forms
=============
Forms for adding and editing contact logs.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FloatField, TextAreaField, SubmitField, DateTimeField
from wtforms.validators import DataRequired, Optional, Length
from datetime import datetime
from models.logbook import ContactLog

class ContactLogForm(FlaskForm):
    """Form for logging a contact."""
    
    contact_callsign = StringField(
        'Contact Callsign',
        validators=[DataRequired(), Length(max=20)]
    )
    
    mode = SelectField(
        'Mode',
        choices=[(m, m) for m in ContactLog.VALID_MODES],
        validators=[DataRequired()]
    )
    
    band = SelectField(
        'Band',
        choices=[('', 'Select Band')] + [(b, b) for b in ContactLog.VALID_BANDS],
        validators=[Optional()]
    )
    
    frequency = FloatField(
        'Frequency (MHz)',
        validators=[Optional()]
    )
    
    grid = StringField(
        'Grid Locator',
        validators=[Optional(), Length(max=10)]
    )
    
    timestamp = DateTimeField(
        'Date/Time (UTC)',
        default=datetime.utcnow,
        format='%Y-%m-%d %H:%M:%S',
        validators=[DataRequired()]
    )
    
    signal_report_sent = StringField(
        'RST Sent',
        validators=[Optional(), Length(max=10)]
    )
    
    signal_report_rcvd = StringField(
        'RST Received',
        validators=[Optional(), Length(max=10)]
    )
    
    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )
    
    submit = SubmitField('Log Contact')