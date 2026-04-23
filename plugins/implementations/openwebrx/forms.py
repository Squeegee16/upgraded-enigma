"""
OpenWebRX Plugin Forms
=======================
WTForms definitions for OpenWebRX configuration,
signal logging, and contact management.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, IntegerField,
    FloatField, BooleanField, SubmitField, TextAreaField
)
from wtforms.validators import (
    DataRequired, Optional, NumberRange, Length
)


class OpenWebRXSettingsForm(FlaskForm):
    """
    Form for OpenWebRX configuration settings.
    Handles SDR device, server, and receiver parameters.
    """

    # Server settings
    http_port = IntegerField(
        'Web Interface Port',
        validators=[NumberRange(min=1024, max=65535)],
        default=8073,
        description='Port for OpenWebRX web interface'
    )

    allow_anonymous = BooleanField(
        'Allow Anonymous Access',
        default=True,
        description='Allow unauthenticated users to view SDR'
    )

    # Receiver information
    receiver_name = StringField(
        'Receiver Name',
        validators=[DataRequired(), Length(max=100)],
        description='Name displayed in OpenWebRX'
    )

    receiver_location = StringField(
        'Receiver Location',
        validators=[Optional(), Length(max=200)],
        description='Location description'
    )

    receiver_asl = IntegerField(
        'Altitude (ASL, meters)',
        validators=[Optional(), NumberRange(min=-500, max=9000)],
        default=0,
        description='Altitude above sea level in meters'
    )

    receiver_admin = StringField(
        'Admin Callsign/Email',
        validators=[Optional(), Length(max=100)],
        description='Contact information for receiver admin'
    )

    # SDR Device settings
    sdr_type = SelectField(
        'SDR Device Type',
        choices=[
            ('rtlsdr', 'RTL-SDR'),
            ('hackrf', 'HackRF One'),
            ('sdrplay', 'SDRplay'),
            ('plutosdr', 'PlutoSDR'),
            ('airspy', 'Airspy'),
            ('soapy', 'SoapySDR (Generic)'),
        ],
        validators=[DataRequired()],
        description='Type of SDR hardware'
    )

    sdr_device_index = IntegerField(
        'Device Index',
        validators=[NumberRange(min=0, max=10)],
        default=0,
        description='Index of SDR device (if multiple)'
    )

    gain = IntegerField(
        'RF Gain (dB)',
        validators=[NumberRange(min=0, max=60)],
        default=30,
        description='Receiver gain in dB'
    )

    ppm = IntegerField(
        'PPM Correction',
        validators=[NumberRange(min=-200, max=200)],
        default=0,
        description='Frequency correction in PPM'
    )

    # Initial tuning
    initial_frequency = IntegerField(
        'Initial Frequency (Hz)',
        validators=[DataRequired()],
        default=145000000,
        description='Starting frequency in Hz'
    )

    initial_modulation = SelectField(
        'Initial Modulation',
        choices=[
            ('nfm', 'NFM (Narrow FM)'),
            ('wfm', 'WFM (Wide FM / Broadcast)'),
            ('am', 'AM'),
            ('lsb', 'LSB'),
            ('usb', 'USB'),
            ('cw', 'CW'),
            ('ft8', 'FT8'),
            ('ft4', 'FT4'),
            ('js8', 'JS8Call'),
            ('packet', 'APRS/Packet'),
        ],
        description='Starting demodulation mode'
    )

    # Signal logging
    log_signals = BooleanField(
        'Log Detected Signals',
        default=True,
        description='Automatically log decoded digital signals to logbook'
    )

    min_signal_strength = IntegerField(
        'Minimum Signal Strength (dBm)',
        validators=[NumberRange(min=-120, max=0)],
        default=-70,
        description='Only log signals stronger than this threshold'
    )

    auto_start = BooleanField(
        'Auto-start on plugin load',
        description='Start OpenWebRX automatically when plugin loads'
    )

    submit = SubmitField('Save Settings')


class SignalLogForm(FlaskForm):
    """
    Form for manually logging a signal to the central logbook.
    Used when a signal is detected in OpenWebRX.
    """

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(max=20)],
        description='Callsign of detected station'
    )

    frequency = FloatField(
        'Frequency (MHz)',
        validators=[DataRequired()],
        description='Signal frequency in MHz'
    )

    mode = SelectField(
        'Mode',
        choices=[
            ('FT8', 'FT8'),
            ('FT4', 'FT4'),
            ('JS8', 'JS8Call'),
            ('WSPR', 'WSPR'),
            ('APRS', 'APRS/Packet'),
            ('NFM', 'NFM'),
            ('AM', 'AM'),
            ('SSB', 'SSB'),
            ('CW', 'CW'),
            ('OTHER', 'Other'),
        ],
        validators=[DataRequired()]
    )

    signal_report = StringField(
        'Signal Report (SNR)',
        validators=[Optional(), Length(max=10)],
        description='Signal-to-noise ratio or RST report'
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Signal')