"""
Ham Radio Operator Web Application
===================================
Main application entry point.

This Flask application provides a web-based interface for ham radio operators
with support for:
- User authentication and registration
- Plugin-based architecture for external programs
- Device integration (GPS, Radio, SDR)
- Contact logging and export
- Dashboard with real-time information

Author: Ham Radio App Team
Version: 1.0.0
License: MIT
"""

import os
import sys
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from config import config
from models import db
from models.user import User
from datetime import datetime

# Import blueprints
from auth.routes import auth_bp
from dashboard.routes import dashboard_bp
from logbook.routes import logbook_bp
from plugins.routes import plugins_bp

# Import device interfaces
from devices.gps import get_gps_device
from devices.radio import get_radio_device
from devices.sdr import get_sdr_device

# Import plugin loader
from plugins.loader import PluginLoader

def create_app(config_name='default'):
    """
    Application factory for creating Flask app instances.
    
    Args:
        config_name: Configuration name ('development', 'production', 'default')
        
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login."""
        return User.query.get(int(user_id))
    
    # Create database tables
    with app.app_context():
        db.create_all()
        print("Database tables created successfully")
    
    # Initialize devices
    print("\nInitializing devices...")
    gps_device = get_gps_device(app.config)
    radio_device = get_radio_device(app.config)
    sdr_device = get_sdr_device(app.config)
    
    # Attempt to connect devices
    if gps_device.connect():
        print("✓ GPS device initialized")
    else:
        print("✗ GPS device not available (using mock)")
    
    if radio_device.connect():
        print("✓ Radio device initialized")
    else:
        print("✗ Radio device not available (using mock)")
    
    if sdr_device.connect():
        print("✓ SDR device initialized")
    else:
        print("✗ SDR device not available (using mock)")
    
    # Store devices in app extensions for access by plugins
    app.extensions['gps_device'] = gps_device
    app.extensions['radio_device'] = radio_device
    app.extensions['sdr_device'] = sdr_device
    
    # Initialize plugin system
    print("\nInitializing plugin system...")
    devices = {
        'gps': gps_device,
        'radio': radio_device,
        'sdr': sdr_device
    }
    
    plugin_loader = PluginLoader(
        app=app,
        plugins_dir=app.config['PLUGINS_DIR'],
        devices=devices
    )
    
    # Load all plugins
    plugins = plugin_loader.load_all_plugins()
    app.extensions['plugin_loader'] = plugin_loader
    
# -------------------------------------------------------
    # Context processor - injects data into ALL templates
    # -------------------------------------------------------
    @app.context_processor
    def inject_globals():
        """
        Inject global variables into all template contexts.

        Makes plugins, current time, and other globals
        available in every template without explicit passing.
        """
        from flask_login import current_user

        # Get plugins from loader
        plugin_list = []
        plugins = {}

        if plugin_loader:
            plugins = plugin_loader.get_all_plugins()
            plugin_list = plugin_loader.get_plugin_list()

        return dict(
            plugins=plugins,         # Raw dict for nav menu
            plugin_list=plugin_list, # Structured list for cards
            utc_now=datetime.utcnow()
        )
    # Root route
    @app.route('/')
    def index():
        """Redirect root to dashboard or login."""
        from flask_login import current_user
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))
    
    # Error handlers
# Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors."""
        from flask import render_template
        try:
            return render_template('errors/404.html'), 404
        except Exception as e:
            print(f"Error rendering 404 template: {e}")
            # Fallback to simple HTML if template fails
            return '''
            <!DOCTYPE html>
            <html>
            <head><title>404 - Not Found</title></head>
            <body>
                <h1>404 - Page Not Found</h1>
                <p>The page you are looking for does not exist.</p>
                <a href="/">Go to Home</a>
            </body>
            </html>
            ''', 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        from flask import render_template
        db.session.rollback()
        
        # Log the error
        print(f"500 Error: {error}")
        import traceback
        traceback.print_exc()
        
        try:
            return render_template('errors/500.html', error=str(error)), 500
        except Exception as e:
            print(f"Error rendering 500 template: {e}")
            # Fallback to simple HTML if template fails
            return '''
            <!DOCTYPE html>
            <html>
            <head><title>500 - Internal Server Error</title></head>
            <body>
                <h1>500 - Internal Server Error</h1>
                <p>An unexpected error occurred. Please try again later.</p>
                <a href="/">Go to Home</a>
            </body>
            </html>
            ''', 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 errors."""
        from flask import render_template
        try:
            return render_template('errors/403.html'), 403
        except:
            return '''
            <!DOCTYPE html>
            <html>
            <head><title>403 - Forbidden</title></head>
            <body>
                <h1>403 - Forbidden</h1>
                <p>You don't have permission to access this resource.</p>
                <a href="/">Go to Home</a>
            </body>
            </html>
            ''', 403
    @app.route('/debug/plugins')
    def debug_plugins():
        """
        Debug route to check plugin discovery status.
        Remove in production.
        """
        import os
        from flask_login import current_user

        if not app.debug:
            return "Debug mode only", 403

        plugin_loader = app.extensions.get('plugin_loader')

        info = {
            'plugins_dir': app.config.get('PLUGINS_DIR'),
            'plugins_dir_exists': os.path.exists(
                app.config.get('PLUGINS_DIR', '')
            ),
            'loaded_plugins': [],
            'plugins_dir_contents': []
        }

        # List plugins directory
        plugins_dir = app.config.get('PLUGINS_DIR', '')
        if os.path.exists(plugins_dir):
            try:
                info['plugins_dir_contents'] = (
                    os.listdir(plugins_dir)
                )
            except Exception as e:
                info['plugins_dir_error'] = str(e)

        # Get loaded plugin info
        if plugin_loader:
            info['loaded_plugins'] = (
                plugin_loader.get_plugin_list()
            )

        # Return as pretty JSON
        import json
        return (
            f"<pre>{json.dumps(info, indent=2)}</pre>",
            200,
            {'Content-Type': 'text/html'}
        )
    # Cleanup on shutdown
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Clean up database session."""
        db.session.remove()
    
    print("\n" + "="*50)
    print("Ham Radio App initialized successfully!")
    print("="*50 + "\n")
    
    return app

def create_ssl_cert(cert_path, key_path):
    """
    Create a self-signed SSL certificate if it doesn't exist.
    
    Args:
        cert_path: Path to certificate file
        key_path: Path to key file
        
    Returns:
        bool: True if certificates exist or were created successfully
    """
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return True
    
    try:
        from OpenSSL import crypto
        
        # Create key pair
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 2048)
        
        # Create self-signed certificate
        cert = crypto.X509()
        cert.get_subject().C = "US"
        cert.get_subject().ST = "State"
        cert.get_subject().L = "City"
        cert.get_subject().O = "Ham Radio App"
        cert.get_subject().OU = "Ham Radio Operators"
        cert.get_subject().CN = "localhost"
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for 1 year
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha256')
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(cert_path), exist_ok=True)
        
        # Write certificate and key
        with open(cert_path, 'wb') as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        
        with open(key_path, 'wb') as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
        
        print(f"✓ Self-signed SSL certificate created")
        return True
    
    except ImportError:
        print("✗ pyOpenSSL not installed. SSL certificate creation skipped.")
        print("  Install with: pip install pyopenssl")
        return False
    except Exception as e:
        print(f"✗ Error creating SSL certificate: {e}")
        return False

def main():
    """Main entry point for running the application."""
    
    # Determine configuration from environment
    config_name = os.environ.get('FLASK_ENV', 'development')
    
    print("\n" + "="*50)
    print("HAM RADIO OPERATOR WEB APPLICATION")
    print("="*50)
    print(f"Environment: {config_name}")
    print(f"Python version: {sys.version}")
    print("="*50 + "\n")
    
    # Initialize secret key manager early
    print("Initializing security...")
    from secret_key_manager import get_secret_key
    secret_key = get_secret_key()
    
    # Set environment variable so config can use it
    if not os.environ.get('SECRET_KEY'):
        os.environ['SECRET_KEY'] = secret_key
    
    print("✓ Secret key initialized\n")
    
    # Create application
    app = create_app(config_name)
    
    # SSL setup
    ssl_context = None
    if app.config['USE_SSL']:
        cert_path = app.config['SSL_CERT']
        key_path = app.config['SSL_KEY']
        
        # Create SSL certificate if needed
        if create_ssl_cert(cert_path, key_path):
            ssl_context = (cert_path, key_path)
            print(f"✓ SSL enabled (HTTPS)")
        else:
            print("✗ SSL disabled - using HTTP")
            print("  WARNING: HTTP is not secure for production use!")
    
    # Display startup information
    protocol = 'https' if ssl_context else 'http'
    host = app.config['HOST']
    port = app.config['PORT']
    
    print("\n" + "="*50)
    print("SERVER INFORMATION")
    print("="*50)
    print(f"Server URL: {protocol}://{host}:{port}")
    print(f"Access from WiFi hotspot clients using server IP")
    print(f"Debug mode: {app.config['DEBUG']}")
    print(f"Mock devices: {app.config['USE_MOCK_DEVICES']}")
    print("="*50 + "\n")
    
    print("Starting server...")
    print("Press CTRL+C to stop\n")
    
    try:
        # Run the application
        app.run(
            host=host,
            port=port,
            debug=app.config['DEBUG'],
            ssl_context=ssl_context,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        
        # Cleanup plugins
        plugin_loader = app.extensions.get('plugin_loader')
        if plugin_loader:
            plugin_loader.shutdown_all()
        
        # Disconnect devices
        for device_name in ['gps_device', 'radio_device', 'sdr_device']:
            device = app.extensions.get(device_name)
            if device:
                device.disconnect()
                print(f"✓ {device_name} disconnected")
        
        print("\n73! (Best regards)")
        sys.exit(0)

if __name__ == '__main__':
    main()
