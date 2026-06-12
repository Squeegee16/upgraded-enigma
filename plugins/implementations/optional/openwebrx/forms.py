"""
OpenWebRX Plugin Forms
=======================
Settings and contact forms for the OpenWebRX plugin.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, IntegerField,
    FloatField, BooleanField, SubmitField,
    TextAreaField, PasswordField
)
from wtforms.validators import (
    DataRequired, Optional, Length,
    NumberRange, URL
)


class OpenWebRXSettingsForm(FlaskForm):
    """OpenWebRX plugin settings form."""

    # -------------------------------------------------------
    # Connection settings
    # -------------------------------------------------------
    openwebrx_url = StringField(
        'OpenWebRX URL',
        validators=[DataRequired(), Length(max=255)],
        default='http://openwebrx:8073',
        description=(
            'URL to reach the OpenWebRX web interface. '
            'Docker default: http://openwebrx:8073 '
            'Host access: http://localhost:8073'
        )
    )

    http_port = IntegerField(
        'HTTP Port',
        validators=[NumberRange(min=1024, max=65535)],
        default=8073,
        description='OpenWebRX web interface port'
    )

    admin_password = PasswordField(
        'Admin Password',
        validators=[Optional(), Length(max=128)],
        description=(
            'OpenWebRX admin password '
            '(leave blank to keep current)'
        )
    )

    # -------------------------------------------------------
    # Station info
    # -------------------------------------------------------
    receiver_name = StringField(
        'Receiver Name',
        validators=[Optional(), Length(max=100)],
        default='Ham Radio SDR',
        description='Name shown in OpenWebRX interface'
    )

    callsign = StringField(
        'Operator Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign for logbook entries'
    )

    locator = StringField(
        'Grid Locator',
        validators=[Optional(), Length(min=4, max=8)],
        description='Maidenhead grid locator'
    )

    # -------------------------------------------------------
    # Signal logging
    # -------------------------------------------------------
    log_ft8 = BooleanField(
        'Log FT8 spots',
        default=True,
        description='Log FT8 decoded signals to logbook'
    )

    log_wspr = BooleanField(
        'Log WSPR spots',
        default=True,
        description='Log WSPR propagation spots'
    )

    log_aprs = BooleanField(
        'Log APRS packets',
        default=True,
        description='Log APRS position reports'
    )

    log_other = BooleanField(
        'Log other digital modes',
        default=False,
        description='Log all other decoded modes'
    )

    min_snr_log = IntegerField(
        'Minimum SNR for logging (dB)',
        validators=[NumberRange(min=-40, max=30)],
        default=-20,
        description=(
            'Only log signals stronger than this SNR. '
            'FT8 typical range: -20 to +10 dB'
        )
    )

    poll_interval = IntegerField(
        'Poll Interval (seconds)',
        validators=[NumberRange(min=5, max=300)],
        default=15,
        description=(
            'How often to check OpenWebRX for new spots'
        )
    )

    submit = SubmitField('Save Settings')


class OpenWebRXLogForm(FlaskForm):
    """Manual contact logging form."""

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(max=20)]
    )

    mode = SelectField(
        'Mode',
        choices=[
            ('FT8', 'FT8'),
            ('FT4', 'FT4'),
            ('WSPR', 'WSPR'),
            ('JT65', 'JT65'),
            ('JT9', 'JT9'),
            ('APRS', 'APRS'),
            ('SSTV', 'SSTV'),
            ('PSK31', 'PSK31'),
            ('RTTY', 'RTTY'),
            ('CW', 'CW'),
            ('SSB', 'SSB'),
            ('AM', 'AM'),
            ('FM', 'FM'),
            ('OTHER', 'Other'),
        ],
        validators=[DataRequired()]
    )

    frequency = FloatField(
        'Frequency (MHz)',
        validators=[Optional()]
    )

    band = SelectField(
        'Band',
        choices=[
            ('', 'Auto-detect'),
            ('160m', '160m'),
            ('80m', '80m'),
            ('60m', '60m'),
            ('40m', '40m'),
            ('30m', '30m'),
            ('20m', '20m'),
            ('17m', '17m'),
            ('15m', '15m'),
            ('12m', '12m'),
            ('10m', '10m'),
            ('6m', '6m'),
            ('2m', '2m'),
            ('70cm', '70cm'),
            ('L-Band', 'L-Band (1.7 GHz)'),
        ],
        validators=[Optional()]
    )

    rst_sent = StringField(
        'RST Sent',
        validators=[Optional(), Length(max=10)],
        default=''
    )

    rst_rcvd = StringField(
        'RST / SNR Received',
        validators=[Optional(), Length(max=10)],
        default=''
    )

    grid = StringField(
        'Grid Locator',
        validators=[Optional(), Length(max=8)],
        description='Contact grid square'
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Contact')
