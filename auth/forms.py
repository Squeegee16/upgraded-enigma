"""
Authentication Forms
====================
WTForms for user registration and login with validation.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Optional, Length
from models.user import User
import os

class LoginForm(FlaskForm):
    """Login form with callsign and password."""
    
    callsign = StringField('Callsign', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')
    
    def validate_callsign(self, callsign):
        """Validate callsign format."""
        if not User.validate_callsign_format(callsign.data):
            raise ValidationError('Invalid callsign format.')

class RegistrationForm(FlaskForm):
    """Registration form with callsign validation and password strength check."""
    
    callsign = StringField('Callsign', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email (Optional)', validators=[Optional(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    submit = SubmitField('Register')
    
    def validate_callsign(self, callsign):
        """
        Validate callsign format and uniqueness.
        Optionally check against known callsign list.
        """
        callsign_upper = callsign.data.upper()
        
        # Check format
        if not User.validate_callsign_format(callsign_upper):
            raise ValidationError('Invalid callsign format. Please use a valid ham radio callsign.')
        
        # Check if already exists
        user = User.query.filter_by(callsign=callsign_upper).first()
        if user is not None:
            raise ValidationError('Callsign already registered. Please use a different callsign.')
        
        # Optional: Check against known callsign list
        from flask import current_app
        if current_app.config.get('VALIDATE_CALLSIGNS', False):
            callsign_file = current_app.config.get('CALLSIGN_FILE')
            if callsign_file and os.path.exists(callsign_file):
                with open(callsign_file, 'r') as f:
                    valid_callsigns = set(line.strip().upper() for line in f)
                if callsign_upper not in valid_callsigns:
                    raise ValidationError(
                        'Callsign not found in database. Please verify your callsign.'
                    )
    
    def validate_email(self, email):
        """
        Validate email uniqueness if provided.
        Only check if email is not empty.
        """
        # Only validate if email was actually provided
        if email.data and email.data.strip():
            user = User.query.filter_by(email=email.data.strip().lower()).first()
            if user is not None:
                raise ValidationError('Email address already registered. Please use a different email address.')
    
    def validate_password(self, password):
        """Validate password strength."""
        is_valid, error_message = User.validate_password_strength(password.data)
        if not is_valid:
            raise ValidationError(error_message)
