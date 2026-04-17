"""
Configuration Management Module
================================
Centralized configuration for the Ham Radio application.
Handles environment-specific settings and security parameters.
"""

import os
from datetime import timedelta
from pathlib import Path
from secret_key_manager import get_secret_key

class Config:
    """Base configuration class with common settings."""
    
    # Application Settings - Use auto-generated key if not provided
    SECRET_KEY = os.environ.get('SECRET_KEY') or get_secret_key()
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Validate SECRET_KEY
    if not SECRET_KEY or len(SECRET_KEY) < 32:
        print("ERROR: SECRET_KEY is invalid or too short!")
        print("A secure key will be generated automatically.")
        SECRET_KEY = get_secret_key()
    
    # Database Configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        # Create data directory if it doesn't exist
        data_dir = os.path.join(BASE_DIR, 'data', 'db')
        os.makedirs(data_dir, exist_ok=True)
        DATABASE_URL = f'sqlite:///{os.path.join(data_dir, "ham_radio.db")}'
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = True
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
    RADIO_MODEL = int(os.environ.get('RADIO_MODEL', '1035'))
    RADIO_PORT = os.environ.get('RADIO_PORT', '/dev/ttyUSB1')
    RADIO_BAUD_RATE = int(os.environ.get('RADIO_BAUD_RATE', '38400'))
    
    # RTL-SDR Configuration
    SDR_DEVICE_INDEX = int(os.environ.get('SDR_DEVICE_INDEX', '0'))
    SDR_SAMPLE_RATE = int(os.environ.get('SDR_SAMPLE_RATE', '2048000'))
    
    # Callsign Validation
    CALLSIGN_FILE = os.environ.get('CALLSIGN_FILE', os.path.join(BASE_DIR, 'data', 'callsigns', 'callsigns.txt'))
    VALIDATE_CALLSIGNS = os.environ.get('VALIDATE_CALLSIGNS', 'False').lower() == 'true'
    
    # SSL Configuration
    SSL_CERT = os.environ.get('SSL_CERT', os.path.join(BASE_DIR, 'data', 'certs', 'cert.pem'))
    SSL_KEY = os.environ.get('SSL_KEY', os.path.join(BASE_DIR, 'data', 'certs', 'key.pem'))
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
