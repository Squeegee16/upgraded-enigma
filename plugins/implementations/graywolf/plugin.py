"""
GrayWolf Plugin
================
Main plugin class integrating GrayWolf Winlink client
into the Ham Radio Web Application.

GrayWolf provides Winlink email over radio functionality.
Source: https://github.com/chrissnell/graywolf

This plugin:
    - Manages the GrayWolf process lifecycle
    - Provides a dedicated Flask UI
    - Integrates with the central logbook
    - Handles first-run dependency installation

Usage:
    Copy the graywolf/ directory to plugins/implementations/
    The plugin will install dependencies on first run.
"""

import os
import json
from datetime import datetime
from flask import (
    Blueprint, render_template, jsonify,
    request, redirect, url_for, flash
)
from flask_login import login_required, current_user

# Import base plugin class
from plugins.base import BasePlugin

# Import GrayWolf specific modules
from plugins.implementations.graywolf.installer import GrayWolfInstaller
from plugins.implementations.graywolf.graywolf_manager import GrayWolfManager
from plugins.implementations.graywolf.forms import (
    GrayWolfSettingsForm,
    GrayWolfComposeForm
)


class GrayWolfPlugin(BasePlugin):
    """
    GrayWolf Winlink Plugin.

    Provides Winlink email over radio via the GrayWolf client.
    Integrates with the central logbook for contact tracking.
    """

    # Plugin metadata
    name = "GrayWolf"
    description = "Winlink email over radio via GrayWolf client"
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://github.com/chrissnell/graywolf"

    def __init__(self, app=None, devices=None):
        """
        Initialize GrayWolf plugin.

        Args:
            app: Flask application instance
            devices: Dictionary of available device interfaces
        """
        super().__init__(app, devices)

        # Plugin directory for configuration storage
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'graywolf'
        )

        # Create plugin data directory
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Installer instance
        self.installer = GrayWolfInstaller()

        # GrayWolf process manager (initialized after install)
        self.manager = None

        # Track installation state
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize the plugin.

        Runs first-time installation if needed,
        then sets up the GrayWolf manager.

        Returns:
            bool: True if initialization was successful
        """
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Run installer (handles first-run detection internally)
            print(f"[{self.name}] Checking installation...")
            install_success = self.installer.run()

            if not install_success:
                self.install_error = "GrayWolf installation failed"
                print(f"[{self.name}] ERROR: {self.install_error}")
                # Continue anyway - show error in UI
                # Don't return False as we still want the UI to load

            self.install_complete = install_success

            # Initialize manager regardless of install state
            # Manager handles missing binary gracefully
            self.manager = GrayWolfManager(
                config_dir=self.plugin_data_dir,
                binary_path=self.installer.graywolf_binary_path
            )

            # Check for GPS device to pre-populate grid square
            gps_device = self.get_device('gps')
            if gps_device and gps_device.is_connected():
                position = gps_device.get_position()
                if position and position.get('grid'):
                    # Pre-populate grid in config
                    if not self.manager.config.get('grid'):
                        self.manager.save_config({'grid': position['grid']})
                        print(f"[{self.name}] Grid set from GPS: {position['grid']}")

            # Auto-start if configured
            if self.manager.config.get('auto_start') and self.install_complete:
                print(f"[{self.name}] Auto-starting GrayWolf...")
                success, message = self.manager.start()
                if success:
                    print(f"[{self.name}] ✓ Auto-start successful")
                else:
                    print(f"[{self.name}] Auto-start failed: {message}")

            print(f"[{self.name}] ✓ Plugin initialized")
            return True

        except Exception as e:
            self.install_error = str(e)
            print(f"[{self.name}] ERROR during initialization: {e}")
            import traceback
            traceback.print_exc()
            return False

    def shutdown(self):
        """
        Shutdown the plugin cleanly.
        Stops GrayWolf process if running.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            status = self.manager.get_status()
            if status.get('running'):
                success, message = self.manager.stop()
                print(f"[{self.name}] Stop result: {message}")

        print(f"[{self.name}] ✓ Shutdown complete")

    def get_blueprint(self):
        """
        Create and return the Flask Blueprint for GrayWolf UI.

        Returns:
            Blueprint: Flask blueprint with all plugin routes
        """
        # Create blueprint with template folder pointing to plugin templates
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/graywolf',
            template_folder=os.path.join(
                os.path.dirname(__file__),
                'templates'
            )
        )

        # Register all routes
        self._register_routes(bp)

        return bp

    def _register_routes(self, bp):
        """
        Register all Flask routes on the blueprint.

        Args:
            bp: Flask Blueprint instance
        """

        # ============================================================
        # Main Dashboard Route
        # ============================================================
        @bp.route('/')
        @login_required
        def index():
            """
            GrayWolf main dashboard page.

            Shows process status, web UI link, activity
            log, and basic controls. Message management
            is delegated to the GrayWolf web UI.
            """
            # Get status safely
            status = (
                self.manager.get_status()
                if self.manager else {}
            )

            # Get log entries
            logs = (
                self.manager.get_logs(50)
                if self.manager else []
            )

            # get_messages() now returns [] safely
            messages = (
                self.manager.get_messages()
                if self.manager else []
            )

            # Get message counts safely
            counts = (
                self.manager.get_message_counts()
                if self.manager else {
                    'inbox': 0,
                    'outbox': 0,
                    'sent': 0
                }
            )

            # Web UI URL for GrayWolf's own interface
            ui_url = (
                self.manager.get_web_ui_url()
                if self.manager
                else 'http://localhost:8080'
            )

            return render_template(
                'graywolf/index.html',
                plugin=self,
                status=status,
                logs=logs,
                messages=messages,
                counts=counts,
                ui_url=ui_url,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=(
                    self.manager.config
                    if self.manager else {}
                )
            )

        # ============================================================
        # Settings Route
        # ============================================================
        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """
            GrayWolf settings page.

            Handles configuration updates.
            """
            form = GrayWolfSettingsForm()

            # Pre-populate form with current config
            if request.method == 'GET' and self.manager:
                config = self.manager.config
                form.callsign.data = config.get('callsign', current_user.callsign)
                form.gateway.data = config.get('gateway', '')
                form.port.data = config.get('port', 8772)
                form.mode.data = config.get('mode', 'telnet')
                form.grid.data = config.get('grid', '')
                form.auto_start.data = config.get('auto_start', False)

            if form.validate_on_submit():
                # Build config from form data
                config_data = {
                    'callsign': form.callsign.data.upper(),
                    'gateway': form.gateway.data or '',
                    'port': form.port.data or 8772,
                    'mode': form.mode.data,
                    'grid': form.grid.data.upper() if form.grid.data else '',
                    'auto_start': form.auto_start.data
                }

                # Save password only if provided (avoid overwriting with blank)
                if form.password.data:
                    config_data['password'] = form.password.data

                if self.manager and self.manager.save_config(config_data):
                    flash('GrayWolf settings saved successfully!', 'success')
                else:
                    flash('Error saving settings', 'danger')

                return redirect(url_for(f'{self.name}.settings'))

            return render_template(
                'graywolf/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # Inbox Route
        # ============================================================
        @bp.route('/inbox')
        @login_required
        def inbox():
            """
            Display Winlink message inbox.
            """
            messages = self.manager.get_messages() if self.manager else []

            return render_template(
                'graywolf/inbox.html',
                plugin=self,
                messages=messages,
                status=self.manager.get_status() if self.manager else {}
            )

        # ============================================================
        # Compose Route
        # ============================================================
        @bp.route('/compose', methods=['GET', 'POST'])
        @login_required
        def compose():
            """
            Compose and send a Winlink message.

            Optionally logs the contact to the central logbook.
            """
            form = GrayWolfComposeForm()

            if form.validate_on_submit():
                if not self.manager:
                    flash('GrayWolf manager not available', 'danger')
                    return redirect(url_for(f'{self.name}.compose'))

                # Send message via GrayWolf
                success, message = self.manager.send_message(
                    to_address=form.to_address.data,
                    subject=form.subject.data,
                    body=form.body.data
                )

                if success:
                    flash(f'Message queued: {message}', 'success')

                    # Log contact to central logbook if requested
                    if form.log_as_contact.data:
                        self._log_winlink_contact(
                            to_callsign=form.to_address.data.split('@')[0],
                            subject=form.subject.data
                        )
                else:
                    flash(f'Failed to send: {message}', 'danger')

                return redirect(url_for(f'{self.name}.inbox'))

            return render_template(
                'graywolf/compose.html',
                plugin=self,
                form=form,
                status=self.manager.get_status() if self.manager else {}
            )

        # ============================================================
        # API Routes
        # ============================================================
        @bp.route('/api/start', methods=['POST'])
        @login_required
        def api_start():
            """API endpoint to start GrayWolf."""
            if not self.manager:
                return jsonify({'success': False, 'error': 'Manager not initialized'}), 503

            if not self.install_complete:
                return jsonify({'success': False, 'error': 'GrayWolf not installed'}), 503

            data = request.get_json() or {}
            success, message = self.manager.start(
                callsign=data.get('callsign'),
                gateway=data.get('gateway'),
                password=data.get('password')
            )

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/stop', methods=['POST'])
        @login_required
        def api_stop():
            """API endpoint to stop GrayWolf."""
            if not self.manager:
                return jsonify({'success': False, 'error': 'Manager not initialized'}), 503

            success, message = self.manager.stop()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/status')
        @login_required
        def api_status():
            """API endpoint for GrayWolf status."""
            if not self.manager:
                return jsonify({
                    'running': False,
                    'connected': False,
                    'error': 'Manager not initialized'
                })

            return jsonify(self.manager.get_status())

        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """API endpoint for recent GrayWolf logs."""
            limit = request.args.get('limit', 100, type=int)

            if not self.manager:
                return jsonify({'logs': []})

            return jsonify({'logs': self.manager.get_logs(limit)})

        @bp.route('/api/install', methods=['POST'])
        @login_required
        def api_install():
            """API endpoint to trigger installation."""
            try:
                # Reset installer state
                if os.path.exists(self.installer.INSTALL_MARKER):
                    os.remove(self.installer.INSTALL_MARKER)

                # Run installer
                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None

                    # Reinitialize manager
                    self.manager = GrayWolfManager(
                        config_dir=self.plugin_data_dir,
                        binary_path=self.installer.graywolf_binary_path
                    )

                return jsonify({
                    'success': success,
                    'message': 'Installation complete' if success else 'Installation failed'
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

    def _log_winlink_contact(self, to_callsign, subject=''):
        """
        Log a Winlink contact to the central logbook.

        Args:
            to_callsign: Callsign of the contacted station
            subject: Message subject for notes field
        """
        try:
            # Clean up callsign
            callsign = to_callsign.upper().split('@')[0].strip()

            if not callsign:
                return

            # Get current grid from GPS if available
            grid = self.manager.config.get('grid', '')
            gps_device = self.get_device('gps')
            if gps_device and gps_device.is_connected():
                position = gps_device.get_position()
                if position and position.get('grid'):
                    grid = position['grid']

            # Build contact data for central logbook
            contact_data = {
                'callsign': callsign,
                'mode': 'WINLINK',
                'band': 'INTERNET',
                'frequency': None,
                'grid': grid or None,
                'rst_sent': None,
                'rst_rcvd': None,
                'notes': f'Winlink message: {subject}'
            }

            # Use base class log_contact method
            success = self.log_contact(contact_data)

            if success:
                print(f"[{self.name}] ✓ Contact logged: {callsign}")
            else:
                print(f"[{self.name}] Warning: Could not log contact for {callsign}")

        except Exception as e:
            print(f"[{self.name}] Error logging contact: {e}")
