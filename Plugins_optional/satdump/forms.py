"""
SatDump Plugin Forms
=====================
WTForms for SatDump configuration and pipeline control.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, SelectField, IntegerField, BooleanField,
    SubmitField, FloatField, TextAreaField
)
from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange
)


class SatDumpSettingsForm(FlaskForm):
    """
    SatDump plugin settings form.

    Configures SDR device, output directory, display
    settings, and plugin behavior.
    """

    # SDR Device
    sdr_source = SelectField(
        'SDR Source',
        choices=[
            ('rtlsdr', 'RTL-SDR'),
            ('airspy', 'Airspy'),
            ('airspyhf', 'Airspy HF+'),
            ('hackrf', 'HackRF One'),
            ('sdrplay', 'SDRplay (RSP)'),
            ('plutosdr', 'PlutoSDR'),
            ('limesdr', 'LimeSDR'),
            ('spyserver', 'SpyServer'),
            ('file', 'IQ Recording File'),
        ],
        description='SDR hardware to use with SatDump'
    )

    sdr_device_id = StringField(
        'Device ID / Serial',
        validators=[Optional(), Length(max=100)],
        default='0',
        description='Device index or serial number'
    )

    sdr_gain = IntegerField(
        'SDR Gain (dB)',
        validators=[NumberRange(min=0, max=60)],
        default=30,
        description='SDR receiver gain'
    )

    sdr_ppm = IntegerField(
        'PPM Correction',
        validators=[NumberRange(min=-200, max=200)],
        default=0,
        description='Frequency correction in PPM'
    )

    # SpyServer settings
    spyserver_host = StringField(
        'SpyServer Host',
        validators=[Optional(), Length(max=255)],
        default='localhost',
        description='SpyServer hostname or IP'
    )

    spyserver_port = IntegerField(
        'SpyServer Port',
        validators=[Optional(), NumberRange(min=1024, max=65535)],
        default=5555,
        description='SpyServer port'
    )

    # Output settings
    output_dir = StringField(
        'Output Directory',
        validators=[DataRequired(), Length(max=500)],
        description='Directory for SatDump output products'
    )

    # Display
    display = StringField(
        'X Display',
        validators=[Optional(), Length(max=20)],
        default=':0',
        description='X display for SatDump GUI'
    )

    # Station info
    callsign = StringField(
        'Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your callsign for logging'
    )

    locator = StringField(
        'Grid Locator',
        validators=[Optional(), Length(min=4, max=8)],
        description='Maidenhead grid locator'
    )

    # Plugin behavior
    auto_listen = BooleanField(
        'Auto-start data monitoring',
        default=True,
        description='Start monitoring output directory on load'
    )

    log_products = BooleanField(
        'Log satellite passes to logbook',
        default=True,
        description='Add satellite passes to central logbook'
    )

    auto_start = BooleanField(
        'Auto-launch SatDump UI',
        default=False,
        description='Launch SatDump GUI on plugin load'
    )

    submit = SubmitField('Save Settings')


class SatDumpPipelineForm(FlaskForm):
    """
    Form for starting a SatDump pipeline.

    Configures satellite, frequency, SDR source,
    and output options for a new recording session.
    """

    pipeline = SelectField(
        'Pipeline',
        validators=[DataRequired()],
        description='Satellite processing pipeline to use'
    )

    frequency_override = FloatField(
        'Frequency Override (MHz)',
        validators=[Optional()],
        description='Override default frequency (leave blank for default)'
    )

    sdr_override = SelectField(
        'SDR Source Override',
        choices=[
            ('', 'Use configured SDR'),
            ('rtlsdr', 'RTL-SDR'),
            ('airspy', 'Airspy'),
            ('hackrf', 'HackRF One'),
            ('sdrplay', 'SDRplay'),
        ],
        validators=[Optional()]
    )

    output_subdir = StringField(
        'Output Subdirectory',
        validators=[Optional(), Length(max=100)],
        description='Optional subdirectory name for output'
    )

    extra_args = StringField(
        'Extra Arguments',
        validators=[Optional(), Length(max=500)],
        description='Additional satdump CLI arguments'
    )

    submit = SubmitField('Start Pipeline')


class SatDumpOfflineForm(FlaskForm):
    """
    Form for offline processing of IQ recordings.

    Allows processing of pre-recorded IQ files through
    SatDump pipelines.
    """

    pipeline = SelectField(
        'Pipeline',
        validators=[DataRequired()],
        description='Processing pipeline to apply'
    )

    input_file = StringField(
        'Input File Path',
        validators=[DataRequired(), Length(max=500)],
        description='Path to IQ recording file'
    )

    extra_args = StringField(
        'Extra Arguments',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Process File')


class SatDumpLogProductForm(FlaskForm):
    """
    Form for logging a satellite product as a contact.
    """

    product_id = StringField(
        'Product ID',
        validators=[DataRequired()]
    )

    satellite = StringField(
        'Satellite',
        validators=[DataRequired(), Length(max=50)]
    )

    callsign = StringField(
        'Operator Callsign',
        validators=[Optional(), Length(max=20)]
    )

    frequency = FloatField(
        'Frequency (MHz)',
        validators=[Optional()]
    )

    band = SelectField(
        'Band',
        choices=[
            ('', 'Select band'),
            ('2m', '2m VHF'),
            ('70cm', '70cm UHF'),
            ('L-Band', 'L-Band (1.7 GHz)'),
            ('S-Band', 'S-Band (2.4 GHz)'),
        ],
        validators=[Optional()]
    )

    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)]
    )

    submit = SubmitField('Log Pass')