"""
Authentication forms with strong validation.
"""

import re
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, ValidationError

CALLSIGN_REGEX = r'^[A-Z]{1,2}[0-9][A-Z0-9]{1,3}$'

def validate_callsign(form, field):
    if not re.match(CALLSIGN_REGEX, field.data.upper()):
        raise ValidationError("Invalid callsign format.")

def validate_password(form, field):
    pw = field.data
    if len(pw) < 8 or not re.search(r'[A-Z]', pw) \
       or not re.search(r'[a-z]', pw) \
       or not re.search(r'\d', pw) \
       or not re.search(r'[!@#$%^&*]', pw):
        raise ValidationError("Weak password.")

class RegisterForm(FlaskForm):
    callsign = StringField(validators=[DataRequired(), validate_callsign])
    password = PasswordField(validators=[DataRequired(), validate_password])
    submit = SubmitField("Register")

class LoginForm(FlaskForm):
    callsign = StringField(validators=[DataRequired()])
    password = PasswordField(validators=[DataRequired()])
    submit = SubmitField("Login")