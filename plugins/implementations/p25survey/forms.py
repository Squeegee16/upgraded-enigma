"""
P25 Survey Plugin Forms
========================
Settings and logging forms for the P25 Survey plugin.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, IntegerField,
    FloatField, BooleanField, SubmitField,
    TextAreaField
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange
)


class P25SettingsForm(FlaskForm):
    """P25 Survey plugin settings form."""

    # -------------------------------------------------------
    # RF / SDR settings
    # -------------------------------------------------------
    center_frequency_mhz = FloatField(
        'Center Frequency (MHz)',
        validators=[NumberRange(min=25.0, max=1300.0)],
        default=851.0125,
        description=(
            'Initial tuning frequency. '
            '700 MHz: 763-776 MHz | '
            '800 MHz: 806-870 MHz | '
            'VHF: 136-174 MHz | UHF: 380-512 MHz'
        )
    )

    source = SelectField(
        'Default Source',
        choices=[
            ('sdr', 'RTL-SDR (default)'),
            ('radio', 'Configured Radio'),
        ],
        default='sdr',
        description='Default receive source on load'
    )

    sdr_gain = IntegerField(
        'SDR Gain (dB)',
        validators=[NumberRange(min=0, max=60)],
        default=40,
        description='RTL-SDR gain (40 typical for P25)'
    )

    sdr_device_index = IntegerField(
        'SDR Device Index',
        validators=[NumberRange(min=0, max=10)],
        default=0,
        description='RTL-SDR device index (0 = first)'
    )

    op25_port = IntegerField(
        'OP25 HTTP Port',
        validators=[NumberRange(min=1024, max=65535)],
        default=8080,
        description='OP25 HTTP status port'
    )

    # -------------------------------------------------------
    # P25 protocol
    # -------------------------------------------------------
    nac = StringField(
        'Network Access Code (hex)',
        validators=[Optional(), Length(max=5)],
        default='0',
        description=(
            'NAC filter (0 = receive all). '
            'Format: hex, e.g. 293. '
            'Default 0x293 is common.'
        )
    )

    phase = SelectField(
        'P25 Phase',
        choices=[
            ('1', 'Phase 1 (C4FM/CQPSK)'),
            ('2', 'Phase 2 (HDQPSK TDMA)'),
        ],
        default='1',
        description='P25 phase to decode'
    )

    scan_mode = SelectField(
        'Scan Mode',
        choices=[
            ('conventional', 'Conventional — single frequency'),
            ('survey', 'Survey — scan frequency list'),
            ('trunked', 'Trunked — follow control channel'),
        ],
        default='conventional',
        description='Operating mode'
    )

    survey_frequencies = TextAreaField(
        'Survey Frequency List (MHz)',
        validators=[Optional(), Length(max=5000)],
        description=(
            'One frequency per line (MHz). '
            'Used in Survey mode. '
            'Example: 851.0125'
        )
    )

    dwell_time_ms = IntegerField(
        'Dwell Time per Frequency (ms)',
        validators=[NumberRange(min=100, max=30000)],
        default=1000,
        description=(
            'How long to listen at each survey '
            'frequency (milliseconds)'
        )
    )

    # -------------------------------------------------------
    # Audio
    # -------------------------------------------------------
    radio_audio_device = StringField(
        'Radio Audio Input Device',
        validators=[Optional(), Length(max=100)],
        description=(
            'Sound card input from radio discriminator. '
            'Leave blank for system default.'
        )
    )

    audio_output_device = StringField(
        'Audio Output Device',
        validators=[Optional(), Length(max=100)],
        description='Speaker output for decoded audio'
    )

    # -------------------------------------------------------
    # Station info
    # -------------------------------------------------------
    callsign = StringField(
        'My Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign for logbook entries'
    )

    # -------------------------------------------------------
    # Logging
    # -------------------------------------------------------
    auto_log_calls = BooleanField(
        'Auto-log received voice calls',
        default=True,
        description='Automatically log P25 calls to logbook'
    )

    log_encrypted = BooleanField(
        'Log encrypted calls',
        default=True,
        description='Include encrypted calls in log'
    )

    log_min_duration_s = IntegerField(
        'Min call duration to log (seconds)',
        validators=[NumberRange(min=0, max=60)],
        default=2,
        description='Ignore very short calls'
    )

    submit = SubmitField('Save Settings')


class P25LogForm(FlaskForm):
    """Manual P25 contact log form."""

    callsign = StringField(
        'Callsign / Unit ID',
        validators=[DataRequired(), Length(max=20)]
    )

    talkgroup = IntegerField(
        'Talk Group',
        validators=[Optional()]
    )

    nac = StringField(
        'NAC (hex)',
        validators=[Optional(), Length(max=5)]
    )

    frequency = FloatField(
        'Frequency (MHz)',
        validators=[Optional()]
    )

    rst_sent = StringField(
        'RST Sent',
        validators=[Optional(), Length(max=10)],
        default='59'
    )

    rst_rcvd = StringField(
        'RST Received',
        validators=[Optional(), Length(max=10)],
        default='59'
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Contact')
