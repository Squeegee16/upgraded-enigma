"""
FLdigi Plugin Forms
====================
WTForms for FLdigi configuration, TX operations,
and contact logging.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, IntegerField, FloatField,
    TextAreaField, SubmitField, BooleanField
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange
)


class FldigiSettingsForm(FlaskForm):
    """
    FLdigi plugin settings form.

    Configures connection parameters, default mode,
    and plugin behavior options.
    """

    # XML-RPC Connection
    xmlrpc_host = StringField(
        'XML-RPC Host',
        validators=[DataRequired(), Length(max=255)],
        default='localhost',
        description='FLdigi XML-RPC server host'
    )

    xmlrpc_port = IntegerField(
        'XML-RPC Port',
        validators=[NumberRange(min=1024, max=65535)],
        default=7362,
        description='FLdigi XML-RPC port (default: 7362)'
    )

    # Launch settings
    launch_mode = SelectField(
        'Launch Mode',
        choices=[
            ('gui', 'GUI Mode (requires display)'),
            ('connect', 'Connect to existing FLdigi'),
        ],
        description='How to start FLdigi'
    )

    display = StringField(
        'X Display',
        validators=[Optional(), Length(max=20)],
        default=':0',
        description='X display for GUI mode (e.g., :0)'
    )

    # Default operating settings
    default_mode = SelectField(
        'Default Mode',
        choices=[
            ('BPSK31', 'BPSK-31'),
            ('BPSK63', 'BPSK-63'),
            ('BPSK125', 'BPSK-125'),
            ('QPSK31', 'QPSK-31'),
            ('RTTY', 'RTTY'),
            ('MFSK-16', 'MFSK-16'),
            ('MFSK-22', 'MFSK-22'),
            ('OLIVIA-8/500', 'Olivia 8/500'),
            ('OLIVIA-16/500', 'Olivia 16/500'),
            ('CW', 'CW (Morse)'),
            ('WSPR', 'WSPR'),
            ('MT63-500', 'MT63-500'),
            ('MT63-1000', 'MT63-1000'),
        ],
        description='Default digital mode on startup'
    )

    default_frequency = IntegerField(
        'Default Frequency (Hz)',
        validators=[
            NumberRange(min=1800000, max=450000000)
        ],
        default=14070000,
        description='Default frequency in Hz (e.g., 14070000)'
    )

    # Station info
    callsign = StringField(
        'Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign (for logging)'
    )

    locator = StringField(
        'Grid Locator',
        validators=[Optional(), Length(min=4, max=8)],
        description='Maidenhead grid locator'
    )

    # Plugin behavior
    auto_start = BooleanField(
        'Auto-start FLdigi on plugin load',
        description='Launch FLdigi when plugin initializes'
    )

    auto_connect = BooleanField(
        'Auto-connect to existing FLdigi',
        default=True,
        description='Connect to running FLdigi instance'
    )

    log_rx_contacts = BooleanField(
        'Auto-log detected contacts',
        default=True,
        description='Add FLdigi log entries to central logbook'
    )

    monitor_interval = IntegerField(
        'Monitor Interval (seconds)',
        validators=[NumberRange(min=1, max=60)],
        default=5,
        description='How often to poll FLdigi status'
    )

    submit = SubmitField('Save Settings')


class FldigiTransmitForm(FlaskForm):
    """
    Form for transmitting text via FLdigi.
    """

    text = TextAreaField(
        'Text to Transmit',
        validators=[DataRequired(), Length(max=5000)],
        description='Text to send via FLdigi'
    )

    mode = SelectField(
        'Mode Override',
        choices=[('', 'Use current mode')] + [
            (m, m) for m in [
                'BPSK31', 'BPSK63', 'BPSK125',
                'QPSK31', 'RTTY', 'MFSK-16',
                'OLIVIA-8/500', 'CW',
            ]
        ],
        validators=[Optional()]
    )

    transmit_now = BooleanField(
        'Transmit immediately',
        default=True,
        description='Switch to TX after queuing text'
    )

    submit = SubmitField('Send')


class FldigiLogContactForm(FlaskForm):
    """
    Form for manually logging a FLdigi contact
    to the central logbook.
    """

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(max=20)]
    )

    mode = SelectField(
        'Mode',
        choices=[
            ('BPSK31', 'BPSK-31'),
            ('BPSK63', 'BPSK-63'),
            ('BPSK125', 'BPSK-125'),
            ('QPSK31', 'QPSK-31'),
            ('RTTY', 'RTTY'),
            ('MFSK-16', 'MFSK-16'),
            ('MFSK-22', 'MFSK-22'),
            ('OLIVIA-8/500', 'Olivia 8/500'),
            ('CW', 'CW'),
            ('WSPR', 'WSPR'),
            ('MT63-500', 'MT63-500'),
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
            ('', 'Select band'),
            ('160m', '160m'), ('80m', '80m'),
            ('40m', '40m'), ('30m', '30m'),
            ('20m', '20m'), ('17m', '17m'),
            ('15m', '15m'), ('12m', '12m'),
            ('10m', '10m'), ('6m', '6m'),
        ],
        validators=[Optional()]
    )

    rst_sent = StringField(
        'RST Sent',
        validators=[Optional(), Length(max=10)],
        default='599'
    )

    rst_rcvd = StringField(
        'RST Received',
        validators=[Optional(), Length(max=10)],
        default='599'
    )

    grid = StringField(
        'Grid Locator',
        validators=[Optional(), Length(max=8)]
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Contact')