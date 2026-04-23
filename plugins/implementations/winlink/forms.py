"""
Winlink Plugin Forms
=====================
WTForms for Winlink configuration, message composition,
and contact management.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField,
    TextAreaField, SubmitField, BooleanField,
    IntegerField
)
from wtforms.validators import (
    DataRequired, Optional, Length,
    NumberRange, ValidationError
)
import re


def validate_callsign(form, field):
    """
    Validate ham radio callsign format.

    Args:
        form: WTForms form instance
        field: Field being validated
    """
    if field.data:
        pattern = re.compile(
            r'^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$',
            re.IGNORECASE
        )
        if not pattern.match(field.data.upper()):
            raise ValidationError(
                'Invalid callsign format'
            )


class WinlinkSettingsForm(FlaskForm):
    """
    Winlink/Pat configuration settings form.
    """

    # Identity
    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(min=3, max=10),
                    validate_callsign],
        description='Your ham radio callsign'
    )

    password = PasswordField(
        'Winlink Password',
        validators=[Optional(), Length(max=64)],
        description='Winlink account password (leave blank to keep current)'
    )

    locator = StringField(
        'Grid Locator',
        validators=[Optional(), Length(min=4, max=8)],
        description='Maidenhead grid locator (e.g., FN20)'
    )

    # Connection Mode
    connection_mode = SelectField(
        'Connection Mode',
        choices=[
            ('telnet', 'Telnet (Internet/CMS)'),
            ('ax25', 'AX.25 (VHF/UHF Packet)'),
            ('vara_hf', 'VARA HF'),
            ('vara_fm', 'VARA FM'),
            ('ardop', 'ARDOP (HF)'),
        ],
        validators=[DataRequired()],
        description='Default Winlink connection mode'
    )

    # Telnet Settings
    telnet_host = StringField(
        'CMS Host',
        validators=[Optional(), Length(max=255)],
        default='server.winlink.org',
        description='Winlink CMS server hostname'
    )

    telnet_port = IntegerField(
        'CMS Port',
        validators=[Optional(), NumberRange(min=1, max=65535)],
        default=8772,
        description='Winlink CMS port number'
    )

    # AX.25 Settings
    ax25_port = StringField(
        'AX.25 Port',
        validators=[Optional(), Length(max=20)],
        default='wl2k',
        description='AX.25 port name from axports'
    )

    # VARA Settings
    vara_host = StringField(
        'VARA Host',
        validators=[Optional(), Length(max=255)],
        default='localhost',
        description='VARA modem host address'
    )

    vara_port = IntegerField(
        'VARA Port',
        validators=[Optional(), NumberRange(min=1, max=65535)],
        default=8300,
        description='VARA modem port'
    )

    # Pat Settings
    pat_http_addr = StringField(
        'Pat HTTP Address',
        validators=[Optional(), Length(max=50)],
        default='0.0.0.0:8080',
        description='Pat web interface bind address'
    )

    send_heartbeat = BooleanField(
        'Send Position Heartbeat',
        default=True,
        description='Periodically report position to Winlink'
    )

    # Plugin Settings
    auto_start = BooleanField(
        'Auto-start Pat on plugin load',
        description='Automatically start Pat when plugin loads'
    )

    auto_connect = BooleanField(
        'Auto-connect on start',
        description='Automatically connect to Winlink when Pat starts'
    )

    log_messages = BooleanField(
        'Log messages as contacts',
        default=True,
        description='Add sent messages to central logbook'
    )

    submit = SubmitField('Save Settings')


class WinlinkComposeForm(FlaskForm):
    """
    Message composition form for Winlink.
    """

    to_address = StringField(
        'To',
        validators=[DataRequired(), Length(max=255)],
        description='Recipient callsign or email (e.g., W1ABC or user@example.com)'
    )

    subject = StringField(
        'Subject',
        validators=[DataRequired(), Length(max=255)],
        description='Message subject line'
    )

    body = TextAreaField(
        'Message',
        validators=[DataRequired(), Length(max=32768)],
        description='Message body (plain text)'
    )

    log_as_contact = BooleanField(
        'Log as contact',
        default=True,
        description='Add to central logbook'
    )

    submit = SubmitField('Queue Message')