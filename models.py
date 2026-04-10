"""
Database models for users and logbook entries.
"""

from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    callsign = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)


class ContactLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact_callsign = db.Column(db.String(20))
    mode = db.Column(db.String(10))
    band = db.Column(db.String(10))
    grid = db.Column(db.String(10))
    signal_report = db.Column(db.String(10))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)