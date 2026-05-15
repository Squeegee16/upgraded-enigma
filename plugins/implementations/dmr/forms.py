"""
DMR Plugin Forms
==================
Settings and logging forms for the DMR plugin.
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

from plugins.implementations.dmr.dmr_constants import (
    DMR_TIERS, COMMON_TALKGROUPS, NETWORK_TYPES,
    CODECS
)


class DMRSettingsForm(FlaskForm):
    """DMR plugin settings form."""

    # -------------------------------------------------------
    # RF / SDR settings
    # -------------------------------------------------------
    center_frequency_mhz = FloatField(
        'Center Frequency (MHz)',
        validators=[NumberRange(min=100.0, max=3000.0)],
        default=438.0,
        description=(
            'Center frequency for RTL-SDR receive. '
            'Set to your local DMR repeater output. '
            'Common: 438-440 MHz (UHF), 145-148 MHz (VHF)'
        )
    )

    source = SelectField(
        'Default Receive Source',
        choices=[
            ('sdr', 'RTL-SDR (default)'),
            ('radio', 'Configured Radio'),
        ],
        default='sdr',
        description='Default receive source on plugin load'
    )

    sdr_gain = IntegerField(
        'SDR Gain (dB)',
        validators=[NumberRange(min=0, max=60)],
        default=40,
        description='RTL-SDR gain (40 typical for DMR)'
    )

    sdr_device_index = IntegerField(
        'SDR Device Index',
        validators=[NumberRange(min=0, max=10)],
        default=0,
        description='RTL-SDR device index (0 = first)'
    )

    # -------------------------------------------------------
    # DMR protocol parameters
    # -------------------------------------------------------
    tier = SelectField(
        'DMR Tier',
        choices=[
            ('1', 'Tier I — Unlicensed simplex (PMR446)'),
            ('2', 'Tier II — Licensed conventional'),
            ('3', 'Tier III — Licensed trunked'),
        ],
        default='2',
        description='DMR system tier'
    )

    color_code = IntegerField(
        'Color Code',
        validators=[NumberRange(min=0, max=15)],
        default=1,
        description=(
            'Repeater color code (0-15). '
            'Must match the repeater. Default: 1'
        )
    )

    timeslot = SelectField(
        'Default Timeslot',
        choices=[
            ('1', 'Timeslot 1 (TS1)'),
            ('2', 'Timeslot 2 (TS2)'),
        ],
        default='1',
        description='Active TDMA timeslot (1 or 2)'
    )

    talkgroup = IntegerField(
        'Default Talk Group',
        validators=[NumberRange(min=1, max=16777215)],
        default=9990,
        description=(
            '9990 = Parrot/Echo test | '
            '91 = Worldwide | '
            '3100 = North America | '
            '3026 = Canada'
        )
    )

    source_id = IntegerField(
        'My DMR Radio ID',
        validators=[NumberRange(min=1, max=16777215)],
        default=3000000,
        description=(
            'Your DMR Radio ID (7 digits). '
            'Register at radioid.net'
        )
    )

    # -------------------------------------------------------
    # Network settings
    # -------------------------------------------------------
    network_type = SelectField(
        'Network Type',
        choices=[
            ('BrandMeister', 'BrandMeister'),
            ('DMR-MARC', 'DMR-MARC'),
            ('TGIF', 'TGIF Network'),
            ('Standalone', 'Standalone Repeater'),
            ('None', 'Simplex / No Network'),
        ],
        default='BrandMeister',
        description='DMR network the repeater connects to'
    )

    repeater_callsign = StringField(
        'Repeater Callsign',
        validators=[Optional(), Length(max=10)],
        description='Callsign of the repeater you use'
    )

    # -------------------------------------------------------
    # Audio settings
    # -------------------------------------------------------
    radio_audio_device = StringField(
        'Radio Audio Input Device',
        validators=[Optional(), Length(max=100)],
        description=(
            'Sound card input from radio discriminator. '
            'Leave blank for system default. '
            'Example: hw:1,0 or pulse'
        )
    )

    audio_output_device = StringField(
        'Audio Output Device',
        validators=[Optional(), Length(max=100)],
        description='Speaker output for decoded audio'
    )

    squelch_level = IntegerField(
        'Squelch Level',
        validators=[NumberRange(min=0, max=100)],
        default=0,
        description=(
            'Digital squelch (0=open, 100=tight). '
            'DMR is digital so squelch is usually 0'
        )
    )

    # -------------------------------------------------------
    # TX / PTT settings
    # -------------------------------------------------------
    ptt_port = StringField(
        'PTT Serial Port',
        validators=[Optional(), Length(max=50)],
        description=(
            'Serial port for PTT keying via RTS. '
            'Example: /dev/ttyUSB0 '
            'Leave blank if using VOX or external PTT'
        )
    )

    tx_power = IntegerField(
        'TX Power Level (1-8)',
        validators=[NumberRange(min=1, max=8)],
        default=4,
        description='Transmit power level (radio-dependent)'
    )

    mic_gain = IntegerField(
        'Microphone Gain (%)',
        validators=[NumberRange(min=0, max=200)],
        default=100,
        description='Browser microphone gain for PTT'
    )

    # -------------------------------------------------------
    # Station info
    # -------------------------------------------------------
    callsign = StringField(
        'My Callsign',
        validators=[Optional(), Length(max=15)],
        description='Your amateur radio callsign'
    )

    # -------------------------------------------------------
    # Decode settings
    # -------------------------------------------------------
    auto_log_calls = BooleanField(
        'Auto-log received calls',
        default=True,
        description='Automatically log decoded calls to logbook'
    )

    log_min_duration_s = IntegerField(
        'Minimum call duration to log (seconds)',
        validators=[NumberRange(min=0, max=60)],
        default=2,
        description='Ignore very short calls (squelch tails)'
    )

    submit = SubmitField('Save Settings')


class DMRLogForm(FlaskForm):
    """Manual DMR contact log form."""

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(max=20)]
    )

    dmr_id = IntegerField(
        'DMR ID',
        validators=[Optional(),
                    NumberRange(min=1, max=16777215)]
    )

    talkgroup = IntegerField(
        'Talk Group',
        validators=[Optional()]
    )

    timeslot = SelectField(
        'Timeslot',
        choices=[('1', 'TS1'), ('2', 'TS2')],
        default='1'
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
