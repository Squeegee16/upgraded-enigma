"""
FLdigi Plugin
=============
Integration with FLdigi for digital modes.
"""

from plugins.base import BasePlugin
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
import xmlrpc.client

class FldigiPlugin(BasePlugin):
    """
    FLdigi plugin for digital mode operations.
    
    Integrates with FLdigi via XML-RPC for modes like PSK31, RTTY, etc.
    """
    
    name = "FLdigi"
    description = "Digital mode operations via FLdigi"
    version = "1.0.0"
    author = "Ham Radio App Team"
    
    def __init__(self, app=None, devices=None):
        super().__init__(app, devices)
        self.fldigi_server = None
        self.fldigi_url = "http://localhost:7362"
    
    def initialize(self):
        """Initialize FLdigi plugin."""
        try:
            # Connect to FLdigi XML-RPC server
            self.fldigi_server = xmlrpc.client.ServerProxy(self.fldigi_url)
            
            # Test connection
            try:
                version = self.fldigi_server.fldigi.version()
                print(f"Connected to FLdigi version: {version}")
            except Exception as e:
                print(f"FLdigi not running or XML-RPC not enabled: {e}")
                self.fldigi_server = None
            
            return True
        except Exception as e:
            print(f"Error initializing FLdigi plugin: {e}")
            return False
    
    def shutdown(self):
        """Shutdown FLdigi plugin."""
        self.fldigi_server = None
    
    def get_blueprint(self):
        """Get Flask blueprint for FLdigi routes."""
        bp = Blueprint('FLdigi', __name__, url_prefix='/plugin/fldigi')
        
        @bp.route('/')
        @login_required
        def index():
            """Main FLdigi page."""
            return render_template(
                'plugins/fldigi.html',
                plugin=self,
                user=current_user
            )
        
        @bp.route('/status')
        @login_required
        def get_status():
            """Get FLdigi status."""
            if not self.fldigi_server:
                return jsonify({'connected': False}), 503
            
            try:
                status = {
                    'connected': True,
                    'mode': self.fldigi_server.modem.get_name(),
                    'frequency': self.fldigi_server.main.get_frequency(),
                    'tx': self.fldigi_server.main.get_trx_status() == 'tx'
                }
                return jsonify(status)
            except Exception as e:
                return jsonify({'connected': False, 'error': str(e)}), 500
        
        @bp.route('/send', methods=['POST'])
        @login_required
        def send_text():
            """Send text via FLdigi."""
            if not self.fldigi_server:
                return jsonify({'success': False, 'error': 'FLdigi not connected'}), 503
            
            try:
                data = request.get_json()
                text = data.get('text', '')
                
                self.fldigi_server.text.add_tx(text)
                
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        return bp