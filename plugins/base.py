"""
Base Plugin Class
=================
Abstract base class for all plugins.
Defines the plugin interface and lifecycle.
"""

from abc import ABC, abstractmethod
from flask import Blueprint

class BasePlugin(ABC):
    """
    Abstract base class for plugins.
    
    All plugins must inherit from this class and implement
    the required abstract methods.
    """
    
    # Plugin metadata (must be defined by subclasses)
    name = "Base Plugin"
    description = "Base plugin class"
    version = "1.0.0"
    author = "Unknown"
    
    def __init__(self, app=None, devices=None):
        """
        Initialize plugin.
        
        Args:
            app: Flask application instance
            devices: Dictionary of available devices (gps, radio, sdr)
        """
        self.app = app
        self.devices = devices or {}
        self.enabled = False
        self.blueprint = None
    
    @abstractmethod
    def initialize(self):
        """
        Initialize plugin resources.
        Called when plugin is loaded.
        
        Returns:
            bool: True if initialization successful
        """
        pass
    
    @abstractmethod
    def shutdown(self):
        """
        Cleanup plugin resources.
        Called when plugin is unloaded or app shuts down.
        """
        pass
    
    @abstractmethod
    def get_blueprint(self):
        """
        Get Flask blueprint for plugin routes.
        
        Returns:
            Blueprint: Flask blueprint with plugin routes
        """
        pass
    
    def get_status(self):
        """
        Get plugin status information.
        
        Returns:
            dict: Status information
        """
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'author': self.author,
            'enabled': self.enabled
        }
    
    def enable(self):
        """Enable the plugin."""
        self.enabled = True
    
    def disable(self):
        """Disable the plugin."""
        self.enabled = False
    
    def get_device(self, device_name):
        """
        Get a device interface by name.
        
        Args:
            device_name: Name of device (gps, radio, sdr)
            
        Returns:
            Device interface or None
        """
        return self.devices.get(device_name)
    
    def log_contact(self, contact_data):
        """
        Log a contact to the central logbook.
        
        Args:
            contact_data: Dictionary with contact information
            
        Returns:
            bool: True if logged successfully
        """
        from models import db
        from models.logbook import ContactLog
        from flask_login import current_user
        
        try:
            contact = ContactLog(
                operator_id=current_user.id,
                contact_callsign=contact_data.get('callsign'),
                mode=contact_data.get('mode'),
                band=contact_data.get('band'),
                frequency=contact_data.get('frequency'),
                grid=contact_data.get('grid'),
                signal_report_sent=contact_data.get('rst_sent'),
                signal_report_rcvd=contact_data.get('rst_rcvd'),
                notes=contact_data.get('notes')
            )
            
            db.session.add(contact)
            db.session.commit()
            return True
        except Exception as e:
            print(f"Error logging contact: {e}")
            db.session.rollback()
            return False