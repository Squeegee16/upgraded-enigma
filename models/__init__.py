"""
Database Models Package
=======================
Contains all SQLAlchemy models for the application.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import models to register them with SQLAlchemy
from models.user import User
from models.logbook import ContactLog

__all__ = ['db', 'User', 'ContactLog']