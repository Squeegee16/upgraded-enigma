"""
WSJT-X Plugin
==============
Main plugin class integrating WSJT-X weak signal digital
modes into the Ham Radio Web Application.

WSJT-X provides:
    - FT8, FT4, JT65, JT9, WSPR digital modes
    - Real-time decode display
    - Automatic QSO logging
    - Propagation monitoring via WSPR

Integration:
    - UDP listener receives WSJT-X decoded messages
    - QSO_LOGGED packets auto-logged to central logbook
    - Status updates provide real-time monitoring
    - GPS provides grid square
    - Hamlib radio provides frequency

Source: https://github.com/WSJTX/wsjtx
Documentation: https://physics.princeton.edu/pulsar/k1jt/wsjtx-doc/

Installation:
    Copy wsjtx/ directory to plugins/implementations/
    Dependencies installed automatically on first run.
"""

import os
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request,
    redirect, url_for, flash
)
from flask_login import login_required, current_user

from plugins.base import BasePlugin
from plugins.implementations.wsjtx.installer import WSJTXInstaller
from plugins.implementations.wsjtx.wsjtx_manager import WSJTXManager
from plugins.implementations.wsjtx.forms import (
    WSJTXSettingsForm,
    WSJTXLogContactForm
)


class WSJTXPlugin(BasePlugin):
    """
    WSJT-X Weak Signal Digital Modes Plugin.

    Integrates WSJT-X into the Ham Radio Application,
    providing real-time decode monitoring, spot display,
    and automatic QSO logging.
    """

    # Plugin metadata
    name = "WSJTX"
    description = "FT8, FT4, JT65, WSPR weak signal digital modes"
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://github.com/WSJTX/wsjtx"

    def __init__(self, app=None, devices=None):
        """
        Initialize WSJT-X plugin.

        Args:
            app: Flask application instance
            devices: Available device interfaces
        """
        super().__init__(app, devices)

        # Plugin data directory
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'wsjtx'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Core components
        self.installer = WSJTXInstaller()
        self.manager = None

        # State
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize plugin on application load.

        Runs installation check, initializes manager,
        integrates GPS data, and starts UDP listener.

        Returns:
            bool: True if initialization successful
        """
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Installation check
            install_success = self.installer.run()

            if not install_success:
                self.install_error = (
                    "WSJT-X installation failed. "
                    "Install manually: "
                    "https://physics.princeton.edu/pulsar/k1jt/wsjtx.html"
                )
                print(
                    f"[{self.name}] WARNING: {self.install_error}"
                )

            self.install_complete = install_success

            # Initialize manager
            self.manager = WSJTXManager(
                config_dir=self.plugin_data_dir,
                binary_path=self.installer.wsjtx_binary_path
            )

            # Update grid from GPS
            self._update_gps_grid()

            # Update callsign from user
            if not self.manager.config.get('callsign'):
                self.manager.save_config({
                    'callsign': getattr(
                        current_user, 'callsign', ''
                    )
                })

            # Auto-start UDP listener
            if self.manager.config.get('auto_listen', True):
                success, msg = self.manager.start_listener()
                if success:
                    print(f"[{self.name}] ✓ {msg}")
                else:
                    print(f"[{self.name}] Listener: {msg}")

            # Auto-launch WSJT-X if configured
            if (self.manager.config.get('auto_start') and
                    self.install_complete):
                success, msg = self.manager.start_wsjtx()
                if success:
                    print(f"[{self.name}] ✓ {msg}")

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

        Stops UDP listener and WSJT-X process if running.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            self.manager.stop_listener()

            if self.manager._status.get('process_running'):
                self.manager.stop_wsjtx()

        print(f"[{self.name}] ✓ Shutdown complete")

    def _update_gps_grid(self):
        """
        Update grid locator from GPS device.
        """
        try:
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos and pos.get('grid'):
                    if not self.manager.config.get('grid'):
                        self.manager.save_config(
                            {'grid': pos['grid']}
                        )
                        print(
                            f"[{self.name}] ✓ Grid: "
                            f"{pos['grid']}"
                        )
        except Exception as e:
            print(f"[{self.name}] GPS warning: {e}")

    def get_blueprint(self):
        """
        Create Flask Blueprint for WSJT-X UI.

        Returns:
            Blueprint: Configured blueprint
        """
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/wsjtx',
            template_folder=os.path.join(
                os.path.dirname(__file__),
                'templates'
            )
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """
        Register all plugin routes.

        Args:
            bp: Flask Blueprint instance
        """

        # ============================================================
        # Main Dashboard
        # ============================================================
        @bp.route('/')
        @login_required
        def index():
            """WSJT-X main dashboard."""
            status = (
                self.manager.get_status()
                if self.manager else {}
            )
            wsjtx_status = (
                self.manager.get_wsjtx_status()
                if self.manager else {}
            )
            decodes = (
                self.manager.get_decodes(20)
                if self.manager else []
            )
            logs = (
                self.manager.get_logs(30)
                if self.manager else []
            )

            # Process pending QSOs
            if self.manager and \
                    self.manager.config.get('auto_log_qsos', True):
                self._process_pending_qsos()

            log_form = WSJTXLogContactForm()

            return render_template(
                'wsjtx/index.html',
                plugin=self,
                status=status,
                wsjtx_status=wsjtx_status,
                decodes=decodes,
                logs=logs,
                log_form=log_form,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=self.manager.config if self.manager else {}
            )

        # ============================================================
        # Spots Page
        # ============================================================
        @bp.route('/spots')
        @login_required
        def spots():
            """Real-time spot display page."""
            mode_filter = request.args.get('mode', None)
            show_cq = request.args.get('cq', 'false').lower() == 'true'

            all_spots = (
                self.manager.get_spots(
                    limit=100,
                    mode_filter=mode_filter
                ) if self.manager else []
            )

            # Filter CQ only if requested
            if show_cq:
                all_spots = [
                    s for s in all_spots
                    if s.get('is_cq', False)
                ]

            wsjtx_status = (
                self.manager.get_wsjtx_status()
                if self.manager else {}
            )
            log_form = WSJTXLogContactForm()

            return render_template(
                'wsjtx/spots.html',
                plugin=self,
                spots=all_spots,
                wsjtx_status=wsjtx_status,
                mode_filter=mode_filter,
                show_cq=show_cq,
                log_form=log_form,
                status=(
                    self.manager.get_status()
                    if self.manager else {}
                )
            )

        # ============================================================
        # Logbook Page
        # ============================================================
        @bp.route('/logbook')
        @login_required
        def logbook():
            """WSJT-X contacts from central logbook."""
            from models.logbook import ContactLog

            wsjtx_modes = [
                'FT8', 'FT4', 'JT65', 'JT9',
                'WSPR', 'Q65', 'MSK144', 'JS8'
            ]

            contacts = ContactLog.query.filter(
                ContactLog.operator_id == current_user.id,
                ContactLog.mode.in_(wsjtx_modes)
            ).order_by(
                ContactLog.timestamp.desc()
            ).limit(200).all()

            log_form = WSJTXLogContactForm()

            return render_template(
                'wsjtx/logbook.html',
                plugin=self,
                contacts=contacts,
                log_form=log_form,
                status=(
                    self.manager.get_status()
                    if self.manager else {}
                )
            )

        # ============================================================
        # Settings
        # ============================================================
        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """WSJT-X plugin settings."""
            form = WSJTXSettingsForm()

            if request.method == 'GET' and self.manager:
                cfg = self.manager.config
                form.udp_host.data = cfg.get(
                    'udp_host', '0.0.0.0'
                )
                form.udp_port.data = cfg.get('udp_port', 2237)
                form.multicast_group.data = cfg.get(
                    'multicast_group', ''
                )
                form.launch_mode.data = cfg.get(
                    'launch_mode', 'connect'
                )
                form.display.data = cfg.get('display', ':0')
                form.callsign.data = cfg.get(
                    'callsign', current_user.callsign
                )
                form.grid.data = cfg.get('grid', '')
                form.auto_start.data = cfg.get('auto_start', False)
                form.auto_listen.data = cfg.get('auto_listen', True)
                form.auto_log_qsos.data = cfg.get(
                    'auto_log_qsos', True
                )
                form.show_cq_only.data = cfg.get(
                    'show_cq_only', False
                )
                form.max_spots.data = cfg.get('max_spots', 100)

            if form.validate_on_submit():
                config_data = {
                    'udp_host': form.udp_host.data,
                    'udp_port': form.udp_port.data,
                    'multicast_group': (
                        form.multicast_group.data or None
                    ),
                    'launch_mode': form.launch_mode.data,
                    'display': form.display.data or ':0',
                    'callsign': (
                        form.callsign.data.upper()
                        if form.callsign.data else ''
                    ),
                    'grid': (
                        form.grid.data.upper()
                        if form.grid.data else ''
                    ),
                    'auto_start': form.auto_start.data,
                    'auto_listen': form.auto_listen.data,
                    'auto_log_qsos': form.auto_log_qsos.data,
                    'show_cq_only': form.show_cq_only.data,
                    'max_spots': form.max_spots.data
                }

                if self.manager and \
                        self.manager.save_config(config_data):
                    flash('Settings saved!', 'success')
                else:
                    flash('Error saving settings', 'danger')

                return redirect(
                    url_for(f'{self.name}.settings')
                )

            return render_template(
                'wsjtx/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # API: Start Listener
        # ============================================================
        @bp.route('/api/start_listener', methods=['POST'])
        @login_required
        def api_start_listener():
            """Start UDP listener."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            success, message = self.manager.start_listener()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Stop Listener
        # ============================================================
        @bp.route('/api/stop_listener', methods=['POST'])
        @login_required
        def api_stop_listener():
            """Stop UDP listener."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            success, message = self.manager.stop_listener()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Start WSJT-X
        # ============================================================
        @bp.route('/api/start_wsjtx', methods=['POST'])
        @login_required
        def api_start_wsjtx():
            """Launch WSJT-X process."""
            if not self.manager or not self.install_complete:
                return jsonify({
                    'success': False,
                    'error': 'Not ready'
                }), 503

            success, message = self.manager.start_wsjtx()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Stop WSJT-X
        # ============================================================
        @bp.route('/api/stop_wsjtx', methods=['POST'])
        @login_required
        def api_stop_wsjtx():
            """Stop WSJT-X process."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            success, message = self.manager.stop_wsjtx()
            return jsonify({
                'success': success,
                'message': message
            })

        # ============================================================
        # API: Status
        # ============================================================
        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get plugin and WSJT-X status."""
            if not self.manager:
                return jsonify({
                    'process_running': False,
                    'udp_listening': False
                })

            return jsonify({
                'plugin': self.manager.get_status(),
                'wsjtx': self.manager.get_wsjtx_status()
            })

        # ============================================================
        # API: Get Decodes
        # ============================================================
        @bp.route('/api/decodes')
        @login_required
        def api_decodes():
            """Get recent decoded messages."""
            limit = request.args.get('limit', 50, type=int)

            if not self.manager:
                return jsonify({'decodes': []})

            decodes = self.manager.get_decodes(limit)

            # Process pending QSOs
            if self.manager.config.get('auto_log_qsos', True):
                self._process_pending_qsos()

            return jsonify({'decodes': decodes})

        # ============================================================
        # API: Get Spots
        # ============================================================
        @bp.route('/api/spots')
        @login_required
        def api_spots():
            """Get decoded spots."""
            limit = request.args.get('limit', 100, type=int)
            mode = request.args.get('mode', None)
            cq_only = request.args.get('cq', 'false').lower() == 'true'

            if not self.manager:
                return jsonify({'spots': []})

            spots = self.manager.get_spots(limit, mode)

            if cq_only:
                spots = [s for s in spots if s.get('is_cq', False)]

            return jsonify({'spots': spots})

        # ============================================================
        # API: Log Contact
        # ============================================================
        @bp.route('/api/log_contact', methods=['POST'])
        @login_required
        def api_log_contact():
            """Log a contact to central logbook."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data'
                    }), 400

                success = self._log_wsjtx_contact(
                    callsign=data.get('callsign', ''),
                    mode=data.get('mode', 'FT8'),
                    frequency=data.get('frequency'),
                    band=data.get('band'),
                    rst_sent=data.get('rst_sent', '-10'),
                    rst_rcvd=data.get('rst_rcvd', '-10'),
                    grid=data.get('grid', ''),
                    notes=data.get('notes', '')
                )

                return jsonify({
                    'success': success,
                    'message': (
                        'Contact logged!' if success
                        else 'Logging failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        # ============================================================
        # API: Halt TX
        # ============================================================
        @bp.route('/api/halt_tx', methods=['POST'])
        @login_required
        def api_halt_tx():
            """Send halt TX command to WSJT-X."""
            if not self.manager:
                return jsonify({
                    'success': False
                }), 503

            data = request.get_json() or {}
            success = self.manager.halt_tx(
                auto_only=data.get('auto_only', False)
            )

            return jsonify({
                'success': success,
                'message': (
                    'Halt TX sent' if success else 'Failed'
                )
            })

        # ============================================================
        # API: Get Logs
        # ============================================================
        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """Get plugin log entries."""
            limit = request.args.get('limit', 50, type=int)

            if not self.manager:
                return jsonify({'logs': []})

            return jsonify({
                'logs': self.manager.get_logs(limit)
            })

        # ============================================================
        # API: Install
        # ============================================================
        @bp.route('/api/install', methods=['POST'])
        @login_required
        def api_install():
            """Trigger WSJT-X installation."""
            try:
                if os.path.exists(self.installer.INSTALL_MARKER):
                    os.remove(self.installer.INSTALL_MARKER)

                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None
                    self.manager = WSJTXManager(
                        config_dir=self.plugin_data_dir
                    )

                return jsonify({
                    'success': success,
                    'message': (
                        'WSJT-X installed!' if success
                        else 'Installation failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        # ============================================================
        # API: Clear Spots
        # ============================================================
        @bp.route('/api/clear_spots', methods=['POST'])
        @login_required
        def api_clear_spots():
            """Clear all accumulated spot data."""
            if self.manager:
                self.manager.clear_spots()
            return jsonify({
                'success': True,
                'message': 'Spots cleared'
            })

    def _process_pending_qsos(self):
        """
        Process QSOs logged by WSJT-X into central logbook.

        Reads pending QSO_LOGGED packets from the UDP
        listener and creates central logbook entries.
        """
        if not self.manager:
            return

        pending = self.manager.get_pending_qsos()

        for qso in pending:
            callsign = qso.get('dx_call', '').strip()
            if not callsign:
                continue

            freq_hz = qso.get('tx_frequency', 0)
            freq_mhz = freq_hz / 1_000_000 if freq_hz else None
            mode = qso.get('mode', 'FT8')
            band = self._freq_to_band(freq_mhz) if freq_mhz else None

            self._log_wsjtx_contact(
                callsign=callsign,
                mode=mode,
                frequency=freq_mhz,
                band=band,
                rst_sent=qso.get('rst_sent', '-10'),
                rst_rcvd=qso.get('rst_rcvd', '-10'),
                grid=qso.get('dx_grid', ''),
                notes=(
                    f"WSJT-X auto-log: "
                    f"{qso.get('comments', '')}"
                )
            )

    def _log_wsjtx_contact(self, callsign, mode='FT8',
                            frequency=None, band=None,
                            rst_sent='-10', rst_rcvd='-10',
                            grid='', notes=''):
        """
        Log a WSJT-X contact to the central logbook.

        Uses the base plugin log_contact() method to
        create a standardized logbook entry.

        Args:
            callsign: Contact callsign
            mode: Digital mode (FT8, FT4, JT65, etc.)
            frequency: Frequency in MHz
            band: Band designation
            rst_sent: Signal report sent
            rst_rcvd: Signal report received
            grid: Contact grid locator
            notes: Additional notes

        Returns:
            bool: True if logged successfully
        """
        try:
            if not callsign or not callsign.strip():
                return False

            # Get GPS grid for our station if not set
            our_grid = self.manager.config.get('grid', '') \
                if self.manager else ''

            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos:
                    our_grid = pos.get('grid', our_grid)

            # Determine band from frequency
            contact_band = band
            if not contact_band and frequency:
                contact_band = self._freq_to_band(frequency)

            # Build standardized contact data
            contact_data = {
                'callsign': callsign.upper().strip(),
                'mode': mode.upper(),
                'band': contact_band or None,
                'frequency': frequency,
                'grid': grid or None,
                'rst_sent': rst_sent,
                'rst_rcvd': rst_rcvd,
                'notes': (
                    f"WSJT-X: {notes}" if notes
                    else "Logged via WSJT-X"
                )
            }

            success = self.log_contact(contact_data)

            if success:
                print(
                    f"[{self.name}] ✓ Logged: "
                    f"{callsign} {mode}"
                )

            return success

        except Exception as e:
            print(f"[{self.name}] Log error: {e}")
            return False

    @staticmethod
    def _freq_to_band(freq_mhz):
        """
        Convert frequency to amateur band designation.

        Args:
            freq_mhz: Frequency in MHz

        Returns:
            str: Band designation or None
        """
        if not freq_mhz:
            return None

        bands = [
            (1.8, 2.0, '160m'),
            (3.5, 4.0, '80m'),
            (5.3, 5.4, '60m'),
            (7.0, 7.3, '40m'),
            (10.1, 10.15, '30m'),
            (14.0, 14.35, '20m'),
            (18.068, 18.168, '17m'),
            (21.0, 21.45, '15m'),
            (24.89, 24.99, '12m'),
            (28.0, 29.7, '10m'),
            (50.0, 54.0, '6m'),
            (144.0, 148.0, '2m'),
            (420.0, 450.0, '70cm'),
        ]

        for low, high, band in bands:
            if low <= freq_mhz <= high:
                return band

        return None