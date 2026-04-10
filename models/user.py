"""
User Model
==========
Defines the User model for authentication and user management.
Implements secure password hashing using bcrypt.
"""

from models import db
from flask_login import UserMixin
import bcrypt
from datetime import datetime
import re

class User(UserMixin, db.Model):
    """
    User model for storing ham radio operator information.
    
    Attributes:
        id: Primary key
        callsign: Unique ham radio callsign (username)
        password_hash: Bcrypt hashed password
        email: Optional email address
        created_at: Account creation timestamp
        last_login: Last successful login timestamp
    """
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    callsign = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationship to contact logs
    contacts = db.relationship('ContactLog', backref='operator', lazy='dynamic')
    
    # Callsign validation regex (supports various formats)
    CALLSIGN_REGEX = re.compile(
        r'^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$',
        re.IGNORECASE
    )
    
    def set_password(self, password):
        """
        Hash and set the user's password using bcrypt.
        
        Args:
            password: Plain text password
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    def check_password(self, password):
        """
        Verify a password against the stored hash.
        
        Args:
            password: Plain text password to verify
            
        Returns:
            bool: True if password matches, False otherwise
        """
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    
    @staticmethod
    def validate_callsign_format(callsign):
        """
        Validate callsign format using regex.
        
        Args:
            callsign: Callsign string to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        if not callsign:
            return False
        return bool(User.CALLSIGN_REGEX.match(callsign.upper()))
    
    @staticmethod
    def validate_password_strength(password):
        """
        Validate password meets strength requirements:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        
        Args:
            password: Password string to validate
            
        Returns:
            tuple: (bool, str) - (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        if not re.search(r'\d', password):
            return False, "Password must contain at least one digit"
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        return True, ""
    
    def update_last_login(self):
        """Update the last login timestamp to current time."""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.callsign}>'