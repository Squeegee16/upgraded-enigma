"""
Configuration Management Module
================================
Centralized configuration for the Ham Radio application.
Handles environment-specific settings and security parameters.
"""

import os
from datetime import timedelta

class Config:
    """Base configuration class with common settings."""
    
    # Application Settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.join(BASE_DIR, "ham_radio.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = True  # Use HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Plugin Configuration
    PLUGINS_DIR = os.path.join(BASE_DIR, 'plugins', 'implementations')
    PLUGIN_ENABLED = True
    
    # Device Configuration
    USE_MOCK_DEVICES = os.environ.get('USE_MOCK_DEVICES', 'True').lower() == 'true'
    GPS_SERIAL_PORT = os.environ.get('GPS_SERIAL_PORT', '/dev/ttyUSB0')
    GPS_BAUD_RATE = int(os.environ.get('GPS_BAUD_RATE', '9600'))
    
    # Radio Configuration (Hamlib)
    RADIO_MODEL = int(os.environ.get('RADIO_MODEL', '1035'))  # Yaesu FT-891
    RADIO_PORT = os.environ.get('RADIO_PORT', '/dev/ttyUSB1')
    RADIO_BAUD_RATE = int(os.environ.get('RADIO_BAUD_RATE', '38400'))
    
    # RTL-SDR Configuration
    SDR_DEVICE_INDEX = int(os.environ.get('SDR_DEVICE_INDEX', '0'))
    SDR_SAMPLE_RATE = int(os.environ.get('SDR_SAMPLE_RATE', '2048000'))
    
    # Callsign Validation
    CALLSIGN_FILE = os.path.join(BASE_DIR, 'data', 'callsigns.txt')
    VALIDATE_CALLSIGNS = os.environ.get('VALIDATE_CALLSIGNS', 'False').lower() == 'true'
    
    # SSL Configuration
    SSL_CERT = os.path.join(BASE_DIR, 'data', 'certs', 'cert.pem')
    SSL_KEY = os.path.join(BASE_DIR, 'data', 'certs', 'key.pem')
    USE_SSL = os.environ.get('USE_SSL', 'True').lower() == 'true'
    
    # Server Configuration
    HOST = os.environ.get('FLASK_HOST', '0.0.0.0')
    PORT = int(os.environ.get('FLASK_PORT', '5000'))
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

class DevelopmentConfig(Config):
    """Development-specific configuration."""
    DEBUG = True
    USE_MOCK_DEVICES = True
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    """Production-specific configuration."""
    DEBUG = False
    USE_MOCK_DEVICES = False
    SESSION_COOKIE_SECURE = True

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

