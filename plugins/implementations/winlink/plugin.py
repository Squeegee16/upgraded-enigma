"""
Winlink Express Plugin
=======================
Main plugin integrating Winlink email over radio into the
Ham Radio Web Application.

Uses Pat Winlink client (https://getpat.io/) as the
primary Winlink implementation on Linux.

Pat provides:
    - Full Winlink protocol support
    - HTTP API for integration
    - Multiple connection modes
    - Cross-platform support

Winlink modes supported:
    - Telnet (Internet gateway - for testing/emcomm)
    - AX.25 (VHF/UHF packet radio)
    - VARA HF (HF digital modem)
    - VARA FM (VHF/UHF digital modem)
    - ARDOP (HF digital modem)

Official Winlink: https://winlink.org/WinlinkExpress
Pat Client: https://getpat.io/

Installation:
    Copy winlink/ directory to plugins/implementations/
    First run automatically installs Pat Winlink client.
"""

import os
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request,
    redirect, url_for, flash
)
from flask_login import login_required, current_user

from plugins.base import BasePlugin
from plugins.implementations.winlink.installer import WinlinkInstaller
from plugins.implementations.winlink.winlink_manager import WinlinkManager
from plugins.implementations.winlink.forms import (
    WinlinkSettingsForm,
    WinlinkComposeForm
)


class WinlinkPlugin(BasePlugin):
    """
    Winlink Plugin using Pat client.

    Provides Winlink radio email via the Pat Winlink client,
    with full integration into the Ham Radio App framework.
    """

    # Plugin metadata
    name = "Winlink"
    description = "Radio email via Winlink network using Pat client"
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://winlink.org/WinlinkExpress"

    def __init__(self, app=None, devices=None):
        """
        Initialize plugin.

        Args:
            app: Flask application instance
            devices: Available device interfaces
        """
        super().__init__(app, devices)

        # Plugin data directory
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'winlink'
        )

        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Installer and manager
        self.installer = WinlinkInstaller()
        self.manager = None

        # Installation state
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize plugin on load.

        Runs first-run installation check, initializes
        manager, and integrates GPS data.

        Returns:
            bool: True if initialization successful
        """
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Run installation check
            print(f"[{self.name}] Checking installation...")
            install_success = self.installer.run()

            if not install_success:
                self.install_error = (
                    "Pat Winlink installation failed. "
                    "Please install manually: https://getpat.io/"
                )
                print(f"[{self.name}] WARNING: {self.install_error}")

            self.install_complete = install_success

            # Initialize manager
            self.manager = WinlinkManager(
                config_dir=self.plugin_data_dir,
                binary_path=self.installer.pat_binary_path
            )

            # Update grid from GPS
            self._update_gps_grid()

            # Update callsign from logged-in user if not set
            if not self.manager.config.get('callsign'):
                self.manager.save_config({
                    'callsign': ''
                })

            # Auto-start if configured
            if (self.manager.config.get('auto_start') and
                    self.install_complete):
                print(f"[{self.name}] Auto-starting Pat...")
                success, message = self.manager.start()

                if success and self.manager.config.get('auto_connect'):
                    import time
                    time.sleep(3)  # Wait for Pat to initialize
                    self.manager.connect()

            print(f"[{self.name}] ✓ Plugin initialized")
            return True

        except Exception as e:
            self.install_error = str(e)
            print(f"[{self.name}] ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

    def shutdown(self):
        """
        Clean plugin shutdown.
        Stops Pat if running.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            status = self.manager.get_status()
            if status.get('running'):
                success, msg = self.manager.stop()
                print(f"[{self.name}] {msg}")

        print(f"[{self.name}] ✓ Shutdown complete")

    def _update_gps_grid(self):
        """
        Update Winlink locator from GPS device.

        Gets current grid square from GPS and updates
        the Pat configuration.
        """
        try:
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos and pos.get('grid'):
                    if not self.manager.config.get('locator'):
                        self.manager.save_config({
                            'locator': pos['grid']
                        })
                        print(
                            f"[{self.name}] ✓ Grid from GPS: "
                            f"{pos['grid']}"
                        )
        except Exception as e:
            print(f"[{self.name}] GPS grid warning: {e}")

    def get_blueprint(self):
        """
        Create Flask Blueprint for Winlink UI.

        Returns:
            Blueprint: Configured blueprint with all routes
        """
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/winlink',
            template_folder=os.path.join(
                os.path.dirname(__file__),
                'templates'
            )
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """
        Register all routes on the blueprint.

        Args:
            bp: Flask Blueprint instance
        """

        # ============================================================
        # Dashboard Route
        # ============================================================
        @bp.route('/')
        @login_required
        def index():
            """Main Winlink dashboard."""
            status = self.manager.get_status() if self.manager else {}
            logs = self.manager.get_logs(50) if self.manager else []
            counts = self.manager.get_message_counts() \
                if self.manager else {}
            inbox = self.manager.get_inbox()[:5] \
                if self.manager else []

            return render_template(
                'winlink/index.html',
                plugin=self,
                status=status,
                logs=logs,
                counts=counts,
                inbox=inbox,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=self.manager.config if self.manager else {}
            )

        # ============================================================
        # Inbox Route
        # ============================================================
        @bp.route('/inbox')
        @login_required
        def inbox():
            """Display received messages."""
            messages = self.manager.get_inbox() if self.manager else []
            counts = self.manager.get_message_counts() \
                if self.manager else {}

            return render_template(
                'winlink/inbox.html',
                plugin=self,
                messages=messages,
                counts=counts,
                status=self.manager.get_status() if self.manager else {},
                folder='inbox'
            )

        # ============================================================
        # Sent Messages Route
        # ============================================================
        @bp.route('/sent')
        @login_required
        def sent():
            """Display sent messages."""
            messages = self.manager.get_sent() if self.manager else []
            counts = self.manager.get_message_counts() \
                if self.manager else {}

            return render_template(
                'winlink/inbox.html',
                plugin=self,
                messages=messages,
                counts=counts,
                status=self.manager.get_status() if self.manager else {},
                folder='sent'
            )

        # ============================================================
        # Outbox Route
        # ============================================================
        @bp.route('/outbox')
        @login_required
        def outbox():
            """Display queued outgoing messages."""
            messages = self.manager.get_outbox() if self.manager else []
            counts = self.manager.get_message_counts() \
                if self.manager else {}

            return render_template(
                'winlink/inbox.html',
                plugin=self,
                messages=messages,
                counts=counts,
                status=self.manager.get_status() if self.manager else {},
                folder='outbox'
            )

        # ============================================================
        # Compose Route
        # ============================================================
        @bp.route('/compose', methods=['GET', 'POST'])
        @login_required
        def compose():
            """Compose and queue a Winlink message."""
            form = WinlinkComposeForm()

            if form.validate_on_submit():
                if not self.manager:
                    flash('Winlink manager not available', 'danger')
                    return redirect(url_for(f'{self.name}.compose'))

                # Queue message
                success, message = self.manager.send_message(
                    to_address=form.to_address.data,
                    subject=form.subject.data,
                    body=form.body.data
                )

                if success:
                    flash(f'Message queued: {message}', 'success')

                    # Log to central logbook
                    if form.log_as_contact.data:
                        self._log_winlink_contact(
                            to_callsign=form.to_address.data,
                            subject=form.subject.data,
                            direction='sent'
                        )
                else:
                    flash(f'Failed: {message}', 'danger')

                return redirect(url_for(f'{self.name}.outbox'))

            return render_template(
                'winlink/compose.html',
                plugin=self,
                form=form,
                status=self.manager.get_status() if self.manager else {}
            )

        # ============================================================
        # Settings Route
        # ============================================================
        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """Plugin settings and configuration."""
            form = WinlinkSettingsForm()

            # Pre-populate from config
            if request.method == 'GET' and self.manager:
                cfg = self.manager.config
                form.callsign.data = cfg.get(
                    'callsign', current_user.callsign
                )
                form.locator.data = cfg.get('locator', '')
                form.connection_mode.data = cfg.get(
                    'connection_mode', 'telnet'
                )
                form.telnet_host.data = cfg.get(
                    'telnet_host', 'server.winlink.org'
                )
                form.telnet_port.data = cfg.get('telnet_port', 8772)
                form.ax25_port.data = cfg.get('ax25_port', 'wl2k')
                form.vara_host.data = cfg.get('vara_host', 'localhost')
                form.vara_port.data = cfg.get('vara_port', 8300)
                form.pat_http_addr.data = cfg.get(
                    'pat_http_addr', '0.0.0.0:8080'
                )
                form.send_heartbeat.data = cfg.get(
                    'send_heartbeat', True
                )
                form.auto_start.data = cfg.get('auto_start', False)
                form.auto_connect.data = cfg.get('auto_connect', False)
                form.log_messages.data = cfg.get('log_messages', True)

            if form.validate_on_submit():
                config_data = {
                    'callsign': form.callsign.data.upper(),
                    'locator': form.locator.data.upper()
                    if form.locator.data else '',
                    'connection_mode': form.connection_mode.data,
                    'telnet_host': form.telnet_host.data or
                    'server.winlink.org',
                    'telnet_port': form.telnet_port.data or 8772,
                    'ax25_port': form.ax25_port.data or 'wl2k',
                    'vara_host': form.vara_host.data or 'localhost',
                    'vara_port': form.vara_port.data or 8300,
                    'pat_http_addr': form.pat_http_addr.data or
                    '0.0.0.0:8080',
                    'send_heartbeat': form.send_heartbeat.data,
                    'auto_start': form.auto_start.data,
                    'auto_connect': form.auto_connect.data,
                    'log_messages': form.log_messages.data
                }

                # Save password only if provided
                if form.password.data:
                    config_data['password'] = form.password.data

                if self.manager and self.manager.save_config(config_data):
                    # Regenerate Pat config
                    self.manager.generate_pat_config()
                    flash('Settings saved!', 'success')
                else:
                    flash('Error saving settings', 'danger')

                return redirect(url_for(f'{self.name}.settings'))

            return render_template(
                'winlink/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # Contacts Route
        # ============================================================
        @bp.route('/contacts')
        @login_required
        def contacts():
            """View Winlink contacts from logbook."""
            from models import db
            from models.logbook import ContactLog

            # Get Winlink contacts from central logbook
            winlink_contacts = ContactLog.query.filter_by(
                operator_id=current_user.id,
                mode='WINLINK'
            ).order_by(ContactLog.timestamp.desc()).limit(100).all()

            return render_template(
                'winlink/contacts.html',
                plugin=self,
                contacts=winlink_contacts
            )

        # ============================================================
        # API Routes
        # ============================================================
        @bp.route('/api/start', methods=['POST'])
        @login_required
        def api_start():
            """Start Pat Winlink client."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            if not self.install_complete:
                return jsonify({
                    'success': False,
                    'error': 'Pat not installed. See settings.'
                }), 503

            success, message = self.manager.start()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/stop', methods=['POST'])
        @login_required
        def api_stop():
            """Stop Pat Winlink client."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            success, message = self.manager.stop()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/connect', methods=['POST'])
        @login_required
        def api_connect():
            """Connect to Winlink gateway."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            data = request.get_json() or {}
            success, message = self.manager.connect(
                mode=data.get('mode'),
                target=data.get('target')
            )

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/disconnect', methods=['POST'])
        @login_required
        def api_disconnect():
            """Disconnect from Winlink gateway."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            success, message = self.manager.disconnect()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get Pat/Winlink status."""
            if not self.manager:
                return jsonify({
                    'running': False,
                    'connected': False,
                    'error': 'Not initialized'
                })

            return jsonify(self.manager.get_status())

        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """Get recent Pat log entries."""
            limit = request.args.get('limit', 100, type=int)

            if not self.manager:
                return jsonify({'logs': []})

            return jsonify({'logs': self.manager.get_logs(limit)})

        @bp.route('/api/install', methods=['POST'])
        @login_required
        def api_install():
            """Trigger Pat installation."""
            try:
                if os.path.exists(self.installer.INSTALL_MARKER):
                    os.remove(self.installer.INSTALL_MARKER)

                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None
                    self.manager = WinlinkManager(
                        config_dir=self.plugin_data_dir,
                        binary_path=self.installer.pat_binary_path
                    )

                return jsonify({
                    'success': success,
                    'message': 'Pat installed!' if success
                    else 'Installation failed'
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

    def _log_winlink_contact(self, to_callsign, subject='',
                              direction='sent'):
        """
        Log a Winlink message as a contact in the central logbook.

        Args:
            to_callsign: Recipient/sender callsign
            subject: Message subject for notes
            direction: 'sent' or 'received'
        """
        try:
            # Extract base callsign (remove @winlink.org etc)
            callsign = to_callsign.upper().split('@')[0].strip()

            if not callsign:
                return

            # Get GPS grid
            grid = self.manager.config.get('locator', '')
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos:
                    grid = pos.get('grid', grid)

            # Determine mode from connection type
            mode_map = {
                'telnet': 'WINLINK',
                'ax25': 'PACKET',
                'vara_hf': 'VARA',
                'vara_fm': 'VARA-FM',
                'ardop': 'ARDOP'
            }

            mode = mode_map.get(
                self.manager.config.get('connection_mode', 'telnet'),
                'WINLINK'
            )

            contact_data = {
                'callsign': callsign,
                'mode': mode,
                'band': None,
                'frequency': None,
                'grid': grid or None,
                'rst_sent': None,
                'rst_rcvd': None,
                'notes': (
                    f"Winlink {direction}: {subject}"
                )
            }

            success = self.log_contact(contact_data)

            if success:
                print(
                    f"[{self.name}] ✓ Logged: {callsign} ({mode})"
                )

        except Exception as e:
            print(f"[{self.name}] Log error: {e}")