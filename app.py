"""
Ham Radio Operator Web Application
====================================
Main application entry point.

This module creates and configures the Flask application,
initialises all extensions, registers blueprints, loads
plugins, and starts the web server.

Author: Ham Radio App Team
Version: 1.0.0
"""

import os
import sys
import traceback
from datetime import datetime
from flask import Flask, redirect, url_for, render_template


def create_app(config_name='default'):
    """
    Application factory.

    Creates and fully configures the Flask application
    including database, login manager, blueprints,
    devices, plugins, and the callsign database.

    Args:
        config_name: Configuration environment name
                     ('development', 'production', 'default')

    Returns:
        Flask: Fully configured application instance
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Load Configuration
    # ------------------------------------------------------------------
    try:
        from config import config
        app.config.from_object(config[config_name])
        print(f"✓ Config loaded: {config_name}")
    except Exception as e:
        print(f"✗ Config load error: {e}")
        traceback.print_exc()
        raise

    # ------------------------------------------------------------------
    # Initialise SQLAlchemy Database
    # ------------------------------------------------------------------
    try:
        from models import db
        db.init_app(app)
        print("✓ SQLAlchemy initialised")
    except Exception as e:
        print(f"✗ SQLAlchemy init error: {e}")
        traceback.print_exc()
        raise

    # ------------------------------------------------------------------
    # Initialise Flask-Login
    # ------------------------------------------------------------------
    try:
        from flask_login import LoginManager
        from models.user import User

        login_manager = LoginManager()
        login_manager.init_app(app)
        login_manager.login_view = 'auth.login'
        login_manager.login_message = (
            'Please log in to access this page.'
        )
        login_manager.login_message_category = 'info'

        @login_manager.user_loader
        def load_user(user_id):
            """Load user by ID for Flask-Login sessions."""
            try:
                return User.query.get(int(user_id))
            except Exception:
                return None

        print("✓ Flask-Login initialised")
    except Exception as e:
        print(f"✗ Flask-Login init error: {e}")
        traceback.print_exc()
        raise

    # ------------------------------------------------------------------
    # Create Database Tables
    # ------------------------------------------------------------------
    with app.app_context():
        try:
            from models import db as _db
            _db.create_all()
            print("✓ Main database tables created")
        except Exception as e:
            print(f"✗ Main DB table error: {e}")
            traceback.print_exc()
            raise

        # Create callsign database tables
        try:
            from callsign_db.models import (
                CanadianOperator, DatabaseMeta
            )
            _db.create_all()
            print("✓ Callsign database tables created")
        except Exception as e:
            print(f"✗ Callsign DB table error: {e}")
            traceback.print_exc()
            # Non-fatal — app can run without callsign DB

    # ------------------------------------------------------------------
    # Initialise Canadian Callsign Database
    # ------------------------------------------------------------------
    try:
        from callsign_db.database import CallsignDatabase
        callsign_db_instance = CallsignDatabase(app)
        print("✓ Callsign database initialised")
    except Exception as e:
        print(f"✗ Callsign DB init error: {e}")
        traceback.print_exc()
        # Non-fatal

    # ------------------------------------------------------------------
    # Register Blueprints
    # Each blueprint is imported and registered individually
    # with explicit error handling so one failure does not
    # prevent the others from loading.
    # ------------------------------------------------------------------
    print("\nRegistering blueprints...")

    # Auth blueprint
    try:
        from auth.routes import auth_bp
        app.register_blueprint(auth_bp)
        print("✓ auth blueprint registered")
    except Exception as e:
        print(f"✗ auth blueprint FAILED: {e}")
        traceback.print_exc()
        raise  # Auth is required — fatal

    # Dashboard blueprint
    try:
        from dashboard.routes import dashboard_bp
        app.register_blueprint(dashboard_bp)
        print("✓ dashboard blueprint registered")
    except Exception as e:
        print(f"✗ dashboard blueprint FAILED: {e}")
        traceback.print_exc()
        raise  # Dashboard is required — fatal

    # Logbook blueprint
    try:
        from logbook.routes import logbook_bp
        app.register_blueprint(logbook_bp)
        print("✓ logbook blueprint registered")
    except Exception as e:
        print(f"✗ logbook blueprint FAILED: {e}")
        traceback.print_exc()
        raise  # Logbook is required — fatal

    # Plugins management blueprint
    try:
        from plugins.routes import plugins_bp
        app.register_blueprint(plugins_bp)
        print("✓ plugins blueprint registered")
    except Exception as e:
        print(f"✗ plugins blueprint FAILED: {e}")
        traceback.print_exc()
        # Non-fatal — plugin management page optional

    print("✓ Core blueprints registered\n")

    # ------------------------------------------------------------------
    # Initialise Hardware Devices
    # ------------------------------------------------------------------
    print("Initializing devices...")

    devices = {}

    # GPS Device
    try:
        from devices.gps import get_gps_device
        gps_device = get_gps_device(app.config)
        if gps_device.connect():
            print("✓ GPS device initialised")
        else:
            print("✗ GPS device not available (using mock)")
        app.extensions['gps_device'] = gps_device
        devices['gps'] = gps_device
    except Exception as e:
        print(f"✗ GPS device error: {e}")
        traceback.print_exc()
        app.extensions['gps_device'] = None
        devices['gps'] = None

    # Radio Device (Hamlib)
    try:
        from devices.radio import get_radio_device
        radio_device = get_radio_device(app.config)
        if radio_device.connect():
            print("✓ Radio device initialised")
        else:
            print("✗ Radio device not available (using mock)")
        app.extensions['radio_device'] = radio_device
        devices['radio'] = radio_device
    except Exception as e:
        print(f"✗ Radio device error: {e}")
        traceback.print_exc()
        app.extensions['radio_device'] = None
        devices['radio'] = None

    # SDR Device (RTL-SDR)
    try:
        from devices.sdr import get_sdr_device
        sdr_device = get_sdr_device(app.config)
        if sdr_device.connect():
            print("✓ SDR device initialised")
        else:
            print("✗ SDR device not available (using mock)")
        app.extensions['sdr_device'] = sdr_device
        devices['sdr'] = sdr_device
    except Exception as e:
        print(f"✗ SDR device error: {e}")
        traceback.print_exc()
        app.extensions['sdr_device'] = None
        devices['sdr'] = None

    print("")

    # ------------------------------------------------------------------
    # Initialise Plugin System
    # ------------------------------------------------------------------
    print("Initializing plugin system...")

    try:
        from plugins.loader import PluginLoader

        plugin_loader = PluginLoader(
            app=app,
            plugins_dir=app.config['PLUGINS_DIR'],
            devices=devices
        )

        # Discover and load all plugins
        plugins = plugin_loader.load_all_plugins()
        app.extensions['plugin_loader'] = plugin_loader

    except Exception as e:
        print(f"✗ Plugin system error: {e}")
        traceback.print_exc()

        # Create empty loader so app still works
        class _EmptyLoader:
            def get_all_plugins(self):
                return {}
            def get_plugin_list(self):
                return []
            def shutdown_all(self):
                pass

        app.extensions['plugin_loader'] = _EmptyLoader()
        plugins = {}

    # ------------------------------------------------------------------
    # Template Context Processor
    # Injects shared variables into every template render.
    # ------------------------------------------------------------------
    @app.context_processor
    def inject_globals():
        """
        Make plugin list and UTC time available in all templates.

        Returns:
            dict: Template context variables
        """
        from flask_login import current_user

        try:
            _loader = app.extensions.get('plugin_loader')
            _plugins = (
                _loader.get_all_plugins() if _loader else {}
            )
            _plugin_list = (
                _loader.get_plugin_list() if _loader else []
            )
        except Exception:
            _plugins = {}
            _plugin_list = []

        return dict(
            plugins=_plugins,
            plugin_list=_plugin_list,
            utc_now=datetime.utcnow()
        )

    # ------------------------------------------------------------------
    # Root Route
    # ------------------------------------------------------------------
    @app.route('/')
    def index():
        """
        Root URL handler.

        Redirects authenticated users to dashboard,
        unauthenticated users to login page.
        """
        from flask_login import current_user

        try:
            if current_user.is_authenticated:
                return redirect(url_for('dashboard.index'))
            return redirect(url_for('auth.login'))
        except Exception as e:
            print(f"Root route error: {e}")
            # Hard fallback — return minimal HTML
            return (
                '<html><body>'
                '<h1>Ham Radio App</h1>'
                '<p><a href="/auth/login">Login</a></p>'
                '<p><a href="/auth/register">Register</a></p>'
                '</body></html>'
            ), 200

    # ------------------------------------------------------------------
    # Error Handlers
    # ------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 Not Found errors."""
        try:
            return render_template('errors/404.html'), 404
        except Exception:
            return (
                '<html><body>'
                '<h1>404 - Page Not Found</h1>'
                '<p><a href="/">Home</a></p>'
                '</body></html>'
            ), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server errors."""
        from models import db
        try:
            db.session.rollback()
        except Exception:
            pass

        print(f"500 Error: {error}")
        traceback.print_exc()

        try:
            return render_template(
                'errors/500.html',
                error=str(error)
            ), 500
        except Exception:
            return (
                '<html><body>'
                '<h1>500 - Internal Server Error</h1>'
                '<p><a href="/">Home</a></p>'
                '</body></html>'
            ), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 Forbidden errors."""
        try:
            return render_template('errors/403.html'), 403
        except Exception:
            return (
                '<html><body>'
                '<h1>403 - Forbidden</h1>'
                '<p><a href="/">Home</a></p>'
                '</body></html>'
            ), 403

    # ------------------------------------------------------------------
    # Debug Routes (development only)
    # ------------------------------------------------------------------
    if app.debug:
        @app.route('/debug/routes')
        def debug_routes():
            """List all registered URL rules."""
            rules = []
            for rule in sorted(
                app.url_map.iter_rules(),
                key=lambda r: r.endpoint
            ):
                rules.append(
                    f"{rule.endpoint:40s} {rule.rule}"
                )
            return (
                '<pre>' + '\n'.join(rules) + '</pre>',
                200,
                {'Content-Type': 'text/html'}
            )

        @app.route('/debug/plugins')
        def debug_plugins():
            """Show plugin discovery status."""
            import json

            _loader = app.extensions.get('plugin_loader')
            info = {
                'plugins_dir': app.config.get('PLUGINS_DIR'),
                'plugins_dir_exists': os.path.exists(
                    app.config.get('PLUGINS_DIR', '')
                ),
                'loaded_plugins': (
                    _loader.get_plugin_list()
                    if _loader else []
                ),
                'registered_endpoints': [
                    r.endpoint
                    for r in app.url_map.iter_rules()
                ],
            }
            return (
                '<pre>' +
                json.dumps(info, indent=2) +
                '</pre>',
                200,
                {'Content-Type': 'text/html'}
            )

    # ------------------------------------------------------------------
    # Session Cleanup
    # ------------------------------------------------------------------
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Remove database session at end of request."""
        from models import db
        try:
            db.session.remove()
        except Exception:
            pass

    print("\n" + "=" * 50)
    print("Ham Radio App initialized successfully!")
    print("=" * 50 + "\n")

    return app


def create_ssl_context(cert_path, key_path):
    """
    Create SSL context or generate self-signed certificate.

    Args:
        cert_path: Path to SSL certificate file
        key_path: Path to SSL private key file

    Returns:
        tuple or None: (cert_path, key_path) or None
    """
    if os.path.exists(cert_path) and os.path.exists(key_path):
        print("✓ SSL certificates found")
        return (cert_path, key_path)

    print("Generating self-signed SSL certificate...")

    try:
        from OpenSSL import crypto

        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 2048)

        cert = crypto.X509()
        cert.get_subject().C = "CA"
        cert.get_subject().ST = "Province"
        cert.get_subject().L = "City"
        cert.get_subject().O = "Ham Radio App"
        cert.get_subject().CN = "localhost"
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha256')

        os.makedirs(os.path.dirname(cert_path), exist_ok=True)

        with open(cert_path, 'wb') as f:
            f.write(
                crypto.dump_certificate(
                    crypto.FILETYPE_PEM, cert
                )
            )

        with open(key_path, 'wb') as f:
            f.write(
                crypto.dump_privatekey(
                    crypto.FILETYPE_PEM, key
                )
            )

        print("✓ SSL certificate generated")
        return (cert_path, key_path)

    except ImportError:
        # Use subprocess as fallback
        try:
            os.makedirs(
                os.path.dirname(cert_path),
                exist_ok=True
            )
            os.system(
                f'openssl req -x509 -newkey rsa:2048 -nodes '
                f'-out {cert_path} -keyout {key_path} '
                f'-days 365 -subj '
                f'"/C=CA/ST=Province/L=City/'
                f'O=HamRadio/CN=localhost" 2>/dev/null'
            )
            if os.path.exists(cert_path):
                print("✓ SSL certificate generated via openssl")
                return (cert_path, key_path)
        except Exception as e:
            print(f"✗ openssl fallback failed: {e}")

    except Exception as e:
        print(f"✗ SSL certificate error: {e}")

    print("✗ SSL disabled — running over HTTP")
    return None


def main():
    """
    Application entry point.

    Reads environment configuration, creates the Flask
    application, configures SSL, and starts the server.
    """

    # Determine environment
    config_name = os.environ.get('FLASK_ENV', 'production')

    print("\n" + "=" * 50)
    print("HAM RADIO OPERATOR WEB APPLICATION")
    print("=" * 50)
    print(f"Environment: {config_name}")
    print(f"Python version: {sys.version.split(chr(10))[0]}")
    print("=" * 50 + "\n")

    # Initialise secret key before app creation
    print("Initializing security...")
    try:
        from secret_key_manager import get_secret_key
        secret_key = get_secret_key()
        if not os.environ.get('SECRET_KEY'):
            os.environ['SECRET_KEY'] = secret_key
        print("✓ Secret key initialized\n")
    except Exception as e:
        print(f"✗ Secret key error: {e}")
        # Generate a temporary key
        import secrets
        os.environ['SECRET_KEY'] = secrets.token_hex(32)
        print("✓ Temporary secret key generated\n")

    # Create application
    try:
        app = create_app(config_name)
    except Exception as e:
        print(f"\n✗ FATAL: Application creation failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    # ------------------------------------------------------------------
    # Verify critical routes are registered
    # ------------------------------------------------------------------
    registered_endpoints = [
        rule.endpoint for rule in app.url_map.iter_rules()
    ]

    critical_endpoints = [
        'auth.login',
        'auth.register',
        'auth.logout',
        'dashboard.index',
        'logbook.index',
    ]

    missing = [
        ep for ep in critical_endpoints
        if ep not in registered_endpoints
    ]

    if missing:
        print(
            f"\n✗ FATAL: Missing critical endpoints: {missing}"
        )
        print("Registered endpoints:")
        for ep in sorted(registered_endpoints):
            print(f"  - {ep}")
        sys.exit(1)
    else:
        print(
            f"✓ All critical endpoints registered "
            f"({len(registered_endpoints)} total)"
        )

    # ------------------------------------------------------------------
    # Configure SSL
    # ------------------------------------------------------------------
    ssl_context = None
    use_ssl = app.config.get('USE_SSL', True)

    if use_ssl:
        ssl_context = create_ssl_context(
            app.config.get('SSL_CERT'),
            app.config.get('SSL_KEY')
        )

    # ------------------------------------------------------------------
    # Print startup information
    # ------------------------------------------------------------------
    protocol = 'https' if ssl_context else 'http'
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 5000)

    print("\n" + "=" * 50)
    print("SERVER INFORMATION")
    print("=" * 50)
    print(f"Server URL: {protocol}://{host}:{port}")
    print(f"Access from WiFi hotspot clients using server IP")
    print(f"Debug mode: {app.config.get('DEBUG', False)}")
    print(
        f"Mock devices: "
        f"{app.config.get('USE_MOCK_DEVICES', True)}"
    )
    print("=" * 50 + "\n")
    print("Starting server...")
    print("Press CTRL+C to stop\n")

    # ------------------------------------------------------------------
    # Start Flask server
    # ------------------------------------------------------------------
    try:
        app.run(
            host=host,
            port=port,
            debug=app.config.get('DEBUG', False),
            ssl_context=ssl_context,
            threaded=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        _shutdown(app)
        print("\n73! (Best regards)")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Server error: {e}")
        traceback.print_exc()
        sys.exit(1)


def _shutdown(app):
    """
    Graceful shutdown handler.

    Stops all plugins and disconnects devices.

    Args:
        app: Flask application instance
    """
    with app.app_context():
        # Shutdown plugins
        try:
            plugin_loader = app.extensions.get('plugin_loader')
            if plugin_loader and hasattr(
                plugin_loader, 'shutdown_all'
            ):
                plugin_loader.shutdown_all()
                print("✓ Plugins shutdown")
        except Exception as e:
            print(f"Plugin shutdown error: {e}")

        # Disconnect devices
        for device_name in [
            'gps_device', 'radio_device', 'sdr_device'
        ]:
            try:
                device = app.extensions.get(device_name)
                if device and hasattr(device, 'disconnect'):
                    device.disconnect()
                    print(f"✓ {device_name} disconnected")
            except Exception as e:
                print(f"Device disconnect error ({device_name}): {e}")


if __name__ == '__main__':
    main()
