"""
Global configuration
Supports mock vs real devices, hotspot hosting, HTTPS.
"""

import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = "sqlite:///hamradio.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Device mode: "mock" or "real"
    DEVICE_MODE = os.environ.get("DEVICE_MODE", "mock")

    # Flask HTTPS (self-signed cert)
    SSL_CERT = "cert.pem"
    SSL_KEY = "key.pem"

    # Allowed callsigns file
    CALLSIGN_DB = "callsigns.txt"