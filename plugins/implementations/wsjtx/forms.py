"""
WSJT-X Plugin Forms
====================
WTForms for WSJT-X configuration and contact logging.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, IntegerField, BooleanField,
    SubmitField, FloatField, TextAreaField
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange
)


class WSJTXSettingsForm(FlaskForm):
    """
    WSJT-X plugin settings form.

    Configures UDP listener parameters and
    plugin behavior options.
    """

    # UDP Settings
    udp_host = StringField(
        'UDP Bind Address',
        validators=[DataRequired(), Length(max=50)],
        default='0.0.0.0',
        description='IP address to listen on (0.0.0.0 = all interfaces)'
    )

    udp_port = IntegerField(
        'UDP Port',
        validators=[NumberRange(min=1024, max=65535)],
        default=2237,
        description='WSJT-X UDP port (default: 2237)'
    )

    multicast_group = StringField(
        'Multicast Group',
        validators=[Optional(), Length(max=20)],
        description='Multicast IP (leave blank for unicast)'
    )

    # Launch settings
    launch_mode = SelectField(
        'Launch Mode',
        choices=[
            ('connect', 'Connect to existing WSJT-X'),
            ('launch', 'Launch WSJT-X automatically'),
        ],
        description='How to interact with WSJT-X'
    )

    display = StringField(
        'X Display',
        validators=[Optional(), Length(max=20)],
        default=':0',
        description='X display for GUI (e.g., :0)'
    )

    # Station settings
    callsign = StringField(
        'My Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign for logging'
    )

    grid = StringField(
        'My Grid',
        validators=[Optional(), Length(min=4, max=8)],
        description='Your Maidenhead grid locator'
    )

    # Plugin behavior
    auto_start = BooleanField(
        'Auto-start on plugin load',
        description='Start WSJT-X when plugin loads'
    )

    auto_listen = BooleanField(
        'Auto-start UDP listener',
        default=True,
        description='Start UDP listener automatically'
    )

    auto_log_qsos = BooleanField(
        'Auto-log QSOs to logbook',
        default=True,
        description='Automatically log QSOs from WSJT-X'
    )

    show_cq_only = BooleanField(
        'Show CQ spots only',
        default=False,
        description='Filter spots to CQ calls only'
    )

    max_spots = IntegerField(
        'Maximum Spots',
        validators=[NumberRange(min=10, max=1000)],
        default=100,
        description='Maximum spots to display'
    )

    submit = SubmitField('Save Settings')


class WSJTXLogContactForm(FlaskForm):
    """
    Form for manually logging a WSJT-X contact.
    """

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(max=20)]
    )

    mode = SelectField(
        'Mode',
        choices=[
            ('FT8', 'FT8'),
            ('FT4', 'FT4'),
            ('JT65', 'JT65'),
            ('JT9', 'JT9'),
            ('WSPR', 'WSPR'),
            ('Q65', 'Q65'),
            ('MSK144', 'MSK144'),
            ('JS8', 'JS8Call'),
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
            ('2m', '2m'), ('70cm', '70cm'),
        ],
        validators=[Optional()]
    )

    rst_sent = StringField(
        'Signal Report Sent',
        validators=[Optional(), Length(max=10)],
        default='-10'
    )

    rst_rcvd = StringField(
        'Signal Report Rcvd',
        validators=[Optional(), Length(max=10)],
        default='-10'
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