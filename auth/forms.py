"""
Authentication Forms
====================
WTForms for user registration and login with validation.
Updated with Canadian callsign database validation.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import (
    DataRequired, Email, EqualTo,
    ValidationError, Optional, Length
)
from models.user import User
from callsign_db.validator import CallsignValidator
import os


class LoginForm(FlaskForm):
    """Login form with callsign and password."""

    callsign = StringField(
        'Callsign',
        validators=[DataRequired()]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired()]
    )
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

    def validate_callsign(self, callsign):
        """Validate callsign format only (no DB check on login)."""
        if not CallsignValidator.is_valid_format(callsign.data):
            raise ValidationError('Invalid callsign format.')


class RegistrationForm(FlaskForm):
    """
    Registration form with Canadian database validation.

    When VALIDATE_CALLSIGNS=True and the callsign is
    Canadian, validates against the local ISED database.
    """

    callsign = StringField(
        'Callsign',
        validators=[DataRequired(), Length(min=3, max=20)]
    )
    email = StringField(
        'Email (Optional)',
        validators=[Optional(), Email()]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired()]
    )
    password2 = PasswordField(
        'Repeat Password',
        validators=[
            DataRequired(),
            EqualTo('password', message='Passwords must match.')
        ]
    )
    submit = SubmitField('Register')

    def validate_callsign(self, callsign):
        """
        Validate callsign format, uniqueness, and database.

        Checks:
        1. Format validation (regex)
        2. Uniqueness in app user table
        3. Canadian database lookup (if enabled + populated)
        """
        from flask import current_app

        callsign_upper = callsign.data.upper().strip()

        # 1. Format check
        if not CallsignValidator.is_valid_format(callsign_upper):
            raise ValidationError(
                'Invalid callsign format. '
                'Please use a valid amateur radio callsign.'
            )

        # 2. Uniqueness check
        existing = User.query.filter_by(
            callsign=callsign_upper
        ).first()
        if existing:
            raise ValidationError(
                'Callsign already registered.'
            )

        # 3. Canadian database check (if enabled)
        validate_db = current_app.config.get(
            'VALIDATE_CALLSIGNS', False
        )

        if validate_db and CallsignValidator.is_canadian(
            callsign_upper
        ):
            is_valid, operator, error = (
                CallsignValidator.validate(
                    callsign_upper,
                    check_database=True
                )
            )

            if not is_valid and error:
                raise ValidationError(
                    f'{error}. Ensure the ISED database is '
                    f'downloaded via the Dashboard.'
                )

    def validate_email(self, email):
        """Validate email uniqueness if provided."""
        if email.data and email.data.strip():
            existing = User.query.filter_by(
                email=email.data.strip().lower()
            ).first()
            if existing:
                raise ValidationError(
                    'Email already registered.'
                )

    def validate_password(self, password):
        """Validate password strength."""
        is_valid, error = User.validate_password_strength(
            password.data
        )
        if not is_valid:
            raise ValidationError(error)
