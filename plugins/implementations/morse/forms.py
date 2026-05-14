"""
Morse Plugin Forms
==================
Settings forms for the Morse Code plugin.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, IntegerField,
    FloatField, BooleanField, SubmitField, TextAreaField
)
from wtforms.validators import (
    DataRequired, Optional, Length,
    NumberRange, ValidationError
)


class MorseSettingsForm(FlaskForm):
    """Morse code settings form."""

    # -------------------------------------------------------
    # Timing settings
    # -------------------------------------------------------
    wpm = IntegerField(
        'Speed (WPM)',
        validators=[NumberRange(min=1, max=60)],
        default=20,
        description='Words per minute (5-40 typical)'
    )

    farnsworth_wpm = IntegerField(
        'Farnsworth Speed (WPM)',
        validators=[Optional(), NumberRange(min=1, max=40)],
        default=0,
        description=(
            'Slower inter-character spacing for learners. '
            '0 = disabled'
        )
    )

    tone_hz = IntegerField(
        'Sidetone Frequency (Hz)',
        validators=[NumberRange(min=400, max=1200)],
        default=700,
        description='CW tone frequency 400-1200 Hz'
    )

    # -------------------------------------------------------
    # SDR settings
    # -------------------------------------------------------
    center_frequency_mhz = FloatField(
        'Center Frequency (MHz)',
        validators=[
            NumberRange(min=0.1, max=2000.0)
        ],
        default=7.030,
        description=(
            '40m CW: 7.030 MHz | '
            '20m CW: 14.030 MHz | '
            '80m CW: 3.530 MHz'
        )
    )

    sdr_gain = IntegerField(
        'SDR Gain (dB)',
        validators=[NumberRange(min=0, max=60)],
        default=30,
        description='RTL-SDR receiver gain'
    )

    sdr_device_index = IntegerField(
        'SDR Device Index',
        validators=[NumberRange(min=0, max=10)],
        default=0,
        description='RTL-SDR device index (0 = first)'
    )

    tone_detection_threshold = FloatField(
        'Tone Detection Threshold',
        validators=[NumberRange(min=0.001, max=0.5)],
        default=0.01,
        description=(
            'Lower = more sensitive. '
            'Increase if false triggers occur.'
        )
    )

    # -------------------------------------------------------
    # Radio settings
    # -------------------------------------------------------
    radio_audio_device = StringField(
        'Radio Audio Input Device',
        validators=[Optional(), Length(max=100)],
        description=(
            'Sound card input connected to radio audio out. '
            'Leave blank for system default.'
        )
    )

    # -------------------------------------------------------
    # Transmit settings
    # -------------------------------------------------------
    default_source = SelectField(
        'Default Receive Source',
        choices=[
            ('sdr', 'RTL-SDR (default)'),
            ('radio', 'Configured Radio'),
        ],
        default='sdr',
        description='Default receive mode on plugin load'
    )

    # -------------------------------------------------------
    # Plugin behaviour
    # -------------------------------------------------------
    auto_log = BooleanField(
        'Auto-log decoded QSOs',
        default=True,
        description=(
            'Automatically detect and log callsigns '
            'heard in decoded text'
        )
    )

    callsign = StringField(
        'My Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign (for logbook entries)'
    )

    submit = SubmitField('Save Settings')


class MorseLogForm(FlaskForm):
    """Manual contact logging form for Morse plugin."""

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(max=20)]
    )

    frequency = FloatField(
        'Frequency (MHz)',
        validators=[Optional()]
    )

    rst_sent = StringField(
        'RST Sent',
        validators=[Optional(), Length(max=5)],
        default='599'
    )

    rst_rcvd = StringField(
        'RST Received',
        validators=[Optional(), Length(max=5)],
        default='599'
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Contact')
