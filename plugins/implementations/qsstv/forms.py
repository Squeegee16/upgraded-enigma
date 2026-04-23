"""
QSSTV Plugin Forms
==================
WTForms for QSSTV settings, transmission, and logging.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, SelectField, IntegerField, BooleanField,
    SubmitField, TextAreaField, FloatField
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange
)


class QSStvSettingsForm(FlaskForm):
    """
    QSSTV plugin settings form.

    Configures display, mode defaults, station info,
    and plugin behavior options.
    """

    # Display
    display = StringField(
        'X Display',
        validators=[Optional(), Length(max=20)],
        default=':0',
        description='X display for QSSTV GUI (e.g., :0)'
    )

    # SSTV defaults
    default_mode = SelectField(
        'Default SSTV Mode',
        choices=[
            ('Martin M1', 'Martin M1 (114s, popular)'),
            ('Martin M2', 'Martin M2 (58s)'),
            ('Martin M3', 'Martin M3 (28s)'),
            ('Scottie S1', 'Scottie S1 (110s)'),
            ('Scottie S2', 'Scottie S2 (71s)'),
            ('Scottie DX', 'Scottie DX (269s, DX)'),
            ('Robot 36', 'Robot 36 Color'),
            ('Robot 72', 'Robot 72 Color'),
            ('PD-90', 'PD-90 (90s)'),
            ('PD-120', 'PD-120 (120s)'),
            ('PD-180', 'PD-180 (180s, high-res)'),
            ('PD-240', 'PD-240 (240s)'),
            ('FAX480', 'FAX480 (Weather fax)'),
        ],
        description='Default mode for SSTV transmission'
    )

    default_frequency = IntegerField(
        'Default Frequency (Hz)',
        validators=[
            NumberRange(min=1800000, max=450000000)
        ],
        default=14230000,
        description='Default frequency in Hz (14230000 = 14.230 MHz)'
    )

    # Station info
    callsign = StringField(
        'Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign for image annotation'
    )

    locator = StringField(
        'Grid Locator',
        validators=[Optional(), Length(min=4, max=8)],
        description='Maidenhead grid locator'
    )

    # Plugin behavior
    auto_start = BooleanField(
        'Auto-start QSSTV on plugin load',
        description='Launch QSSTV when plugin loads'
    )

    auto_monitor = BooleanField(
        'Auto-start image monitoring',
        default=True,
        description='Monitor for received images automatically'
    )

    log_received_images = BooleanField(
        'Log received images to logbook',
        default=True,
        description='Add received SSTV contacts to central logbook'
    )

    max_gallery_images = IntegerField(
        'Maximum Gallery Images',
        validators=[NumberRange(min=10, max=1000)],
        default=100,
        description='Maximum images to keep in gallery'
    )

    submit = SubmitField('Save Settings')


class QSStvTransmitForm(FlaskForm):
    """
    Form for queuing an image for SSTV transmission.
    """

    image = FileField(
        'Image File',
        validators=[
            FileAllowed(
                ['jpg', 'jpeg', 'png', 'bmp', 'gif'],
                'Images only!'
            )
        ],
        description='Image to transmit via SSTV'
    )

    mode = SelectField(
        'SSTV Mode',
        choices=[
            ('Martin M1', 'Martin M1 (popular)'),
            ('Martin M2', 'Martin M2 (faster)'),
            ('Scottie S1', 'Scottie S1'),
            ('Scottie S2', 'Scottie S2'),
            ('Robot 36', 'Robot 36 Color'),
            ('Robot 72', 'Robot 72 Color'),
            ('PD-90', 'PD-90'),
            ('PD-120', 'PD-120 (high quality)'),
            ('PD-180', 'PD-180 (best quality)'),
            ('FAX480', 'FAX480 (weather fax)'),
        ],
        validators=[DataRequired()]
    )

    callsign_overlay = StringField(
        'Callsign Overlay',
        validators=[Optional(), Length(max=15)],
        description='Callsign to overlay on image (optional)'
    )

    submit = SubmitField('Prepare for TX')


class QSStvLogImageForm(FlaskForm):
    """
    Form for logging a received SSTV image as a contact.
    """

    image_id = StringField(
        'Image ID',
        validators=[DataRequired()]
    )

    callsign = StringField(
        'Contact Callsign',
        validators=[DataRequired(), Length(max=20)],
        description='Callsign of station that sent the image'
    )

    frequency = FloatField(
        'Frequency (MHz)',
        validators=[Optional()],
        description='Frequency in MHz'
    )

    band = SelectField(
        'Band',
        choices=[
            ('', 'Select band'),
            ('160m', '160m'), ('80m', '80m'),
            ('40m', '40m'), ('20m', '20m'),
            ('15m', '15m'), ('10m', '10m'),
            ('6m', '6m'), ('2m', '2m'),
        ],
        validators=[Optional()]
    )

    mode = SelectField(
        'SSTV Mode',
        choices=[
            ('SSTV', 'SSTV (generic)'),
            ('Martin M1', 'Martin M1'),
            ('Martin M2', 'Martin M2'),
            ('Scottie S1', 'Scottie S1'),
            ('Scottie S2', 'Scottie S2'),
            ('Robot 36', 'Robot 36'),
            ('Robot 72', 'Robot 72'),
            ('PD-120', 'PD-120'),
            ('PD-180', 'PD-180'),
            ('FAX480', 'FAX480'),
        ],
        validators=[DataRequired()],
        default='SSTV'
    )

    rst_rcvd = StringField(
        'Signal Report',
        validators=[Optional(), Length(max=10)],
        default='59'
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Contact')