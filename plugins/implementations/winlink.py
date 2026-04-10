"""
Winlink Plugin
==============
Integration with Winlink for email over radio.
"""

from plugins.base import BasePlugin
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

class WinlinkPlugin(BasePlugin):
    """
    Winlink plugin for email over radio.
    
    Note: This is a stub implementation. Full Winlink integration
    requires Pat or similar Winlink client software.
    """
    
    name = "Winlink"
    description = "Email over radio via Winlink"
    version = "1.0.0"
    author = "Ham Radio App Team"
    
    def initialize(self):
        """Initialize Winlink plugin."""
        print("Winlink plugin initialized (stub)")
        return True
    
    def shutdown(self):
        """Shutdown Winlink plugin."""
        pass
    
    def get_blueprint(self):
        """Get Flask blueprint for Winlink routes."""
        bp = Blueprint('Winlink', __name__, url_prefix='/plugin/winlink')
        
        @bp.route('/')
        @login_required
        def index():
            """Main Winlink page."""
            return render_template(
                'plugins/winlink.html',
                plugin=self,
                user=current_user
            )
        
        @bp.route('/status')
        @login_required
        def get_status():
            """Get Winlink status."""
            return jsonify({
                'connected': False,
                'message': 'Winlink integration requires Pat or similar client'
            })
        
        return bp