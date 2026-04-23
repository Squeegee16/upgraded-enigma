"""
GrayWolf Plugin Forms
=====================
WTForms definitions for GrayWolf configuration and messaging.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField,
    TextAreaField, SubmitField, BooleanField, IntegerField
)
from wtforms.validators import (
    DataRequired, Optional, Length,
    NumberRange, Email
)


class GrayWolfSettingsForm(FlaskForm):
    """
    Form for configuring GrayWolf settings.
    Handles callsign, gateway, and connection parameters.
    """

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(min=3, max=10)],
        description='Your ham radio callsign'
    )

    password = PasswordField(
        'Winlink Password',
        validators=[Optional(), Length(max=64)],
        description='Your Winlink account password'
    )

    gateway = StringField(
        'Gateway Address',
        validators=[Optional(), Length(max=255)],
        description='Winlink gateway hostname or IP (leave blank for auto)'
    )

    port = IntegerField(
        'Gateway Port',
        validators=[Optional(), NumberRange(min=1, max=65535)],
        default=8772,
        description='Gateway connection port'
    )

    mode = SelectField(
        'Connection Mode',
        choices=[
            ('telnet', 'Telnet (Internet)'),
            ('ax25', 'AX.25 (Packet Radio)'),
            ('vara', 'VARA HF'),
            ('vara_fm', 'VARA FM'),
        ],
        validators=[DataRequired()],
        description='Winlink connection mode'
    )

    grid = StringField(
        'Grid Square',
        validators=[Optional(), Length(min=4, max=8)],
        description='Your Maidenhead grid square'
    )

    auto_start = BooleanField(
        'Auto-start on plugin load',
        description='Automatically start GrayWolf when plugin loads'
    )

    submit = SubmitField('Save Settings')


class GrayWolfComposeForm(FlaskForm):
    """
    Form for composing Winlink messages.
    """

    to_address = StringField(
        'To',
        validators=[DataRequired(), Length(max=255)],
        description='Recipient callsign or email address'
    )

    subject = StringField(
        'Subject',
        validators=[DataRequired(), Length(max=255)],
        description='Message subject'
    )

    body = TextAreaField(
        'Message',
        validators=[DataRequired(), Length(max=10000)],
        description='Message body'
    )

    log_as_contact = BooleanField(
        'Log as contact',
        default=True,
        description='Add this communication to the logbook'
    )

    submit = SubmitField('Send Message')