"""
FLdigi Plugin
==============
Main plugin class integrating FLdigi digital modem
software into the Ham Radio Web Application.

FLdigi provides digital mode communications via:
    - XML-RPC API for programmatic control
    - Many supported digital modes
    - Built-in log panel for contact data
    - Waterfall display for signal visualization

Integration Points:
    - XML-RPC: Full FLdigi control
    - Central Logbook: Auto-log FLdigi contacts
    - GPS Device: Auto-populate grid locator
    - Radio Device: Frequency synchronization

Source: https://github.com/w1hkj/fldigi/
Help: http://www.w1hkj.com/FldigiHelp/

Installation:
    Copy fldigi/ directory to plugins/implementations/
    First run installs FLdigi via package manager.
"""

import os
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify,
    request, redirect, url_for, flash
)
from flask_login import login_required, current_user

from plugins.base import BasePlugin
from plugins.implementations.fldigi.installer import FldigiInstaller
from plugins.implementations.fldigi.fldigi_manager import FldigiManager
from plugins.implementations.fldigi.forms import (
    FldigiSettingsForm,
    FldigiTransmitForm,
    FldigiLogContactForm
)


class FldigiPlugin(BasePlugin):
    """
    FLdigi Digital Modem Plugin.

    Provides digital mode communications via FLdigi
    with full XML-RPC control and logbook integration.
    """

    # Plugin metadata
    name = "FLdigi"
    description = "Digital modes via FLdigi modem software"
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://github.com/w1hkj/fldigi/"

    def __init__(self, app=None, devices=None):
        """
        Initialize FLdigi plugin.

        Args:
            app: Flask application instance
            devices: Available device interfaces dict
        """
        super().__init__(app, devices)

        # Plugin persistent data directory
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'fldigi'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Core components
        self.installer = FldigiInstaller()
        self.manager = None

        # State tracking
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize plugin on application load.

        Performs first-run installation check, initializes
        the FLdigi manager, integrates GPS data, and
        optionally starts or connects to FLdigi.

        Returns:
            bool: True if initialization successful
        """
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Check and run installation
            print(f"[{self.name}] Checking installation...")
            install_success = self.installer.run()

            if not install_success:
                self.install_error = (
                    "FLdigi installation failed. "
                    "Install manually: "
                    "https://github.com/w1hkj/fldigi/"
                )
                print(f"[{self.name}] WARNING: {self.install_error}")

            self.install_complete = install_success

            # Initialize manager
            self.manager = FldigiManager(
                config_dir=self.plugin_data_dir,
                xmlrpc_host='localhost',
                xmlrpc_port=7362
            )

            # Update grid locator from GPS
            self._update_gps_locator()

            # Update callsign from current user if not set
            if not self.manager.config.get('callsign'):
                self.manager.save_config({
                    'callsign': current_user.callsign
                    if hasattr(current_user, 'callsign')
                    else ''
                })

            # Sync frequency from radio device
            self._sync_radio_frequency()

            # Auto-connect to existing FLdigi if configured
            if self.manager.config.get('auto_connect'):
                success, msg = self.manager.connect_to_existing()
                if success:
                    print(f"[{self.name}] ✓ {msg}")
                else:
                    print(f"[{self.name}] INFO: {msg}")

            # Auto-start FLdigi if configured
            elif (self.manager.config.get('auto_start') and
                  self.install_complete):
                print(f"[{self.name}] Auto-starting FLdigi...")
                success, msg = self.manager.start_fldigi()
                if success:
                    print(f"[{self.name}] ✓ {msg}")
                else:
                    print(f"[{self.name}] WARNING: {msg}")

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

        Stops monitoring and optionally closes FLdigi.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            self.manager._rx_monitor_active = False
            # Only stop FLdigi if we started it
            status = self.manager.get_status()
            if status.get('process_running'):
                self.manager.stop_fldigi()

        print(f"[{self.name}] ✓ Shutdown complete")

    def _update_gps_locator(self):
        """
        Update grid locator from GPS device.

        Reads GPS position and updates FLdigi
        configuration with current grid square.
        """
        try:
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos and pos.get('grid'):
                    if not self.manager.config.get('locator'):
                        self.manager.save_config(
                            {'locator': pos['grid']}
                        )
                        print(
                            f"[{self.name}] ✓ Grid: {pos['grid']}"
                        )
        except Exception as e:
            print(f"[{self.name}] GPS warning: {e}")

    def _sync_radio_frequency(self):
        """
        Sync FLdigi default frequency from radio device.

        Gets current radio frequency via Hamlib and
        sets it as the FLdigi default frequency.
        """
        try:
            radio = self.get_device('radio')
            if radio and radio.is_connected():
                freq_mhz = radio.get_frequency()
                if freq_mhz:
                    freq_hz = int(freq_mhz * 1_000_000)
                    self.manager.save_config(
                        {'default_frequency': freq_hz}
                    )
                    print(
                        f"[{self.name}] ✓ Freq: {freq_mhz} MHz"
                    )
        except Exception as e:
            print(f"[{self.name}] Radio sync warning: {e}")

    def get_blueprint(self):
        """
        Create Flask Blueprint for FLdigi UI.

        Returns:
            Blueprint: Configured blueprint with all routes
        """
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/fldigi',
            template_folder=os.path.join(
                os.path.dirname(__file__),
                'templates'
            )
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """
        Register all Flask routes.

        Args:
            bp: Flask Blueprint instance
        """

        # ============================================================
        # Main Dashboard
        # ============================================================
        @bp.route('/')
        @login_required
        def index():
            """FLdigi main dashboard page."""
            status = (
                self.manager.get_status()
                if self.manager else {}
            )
            logs = (
                self.manager.get_logs(50)
                if self.manager else []
            )
            modes = (
                self.manager.get_available_modes()
                if self.manager else []
            )

            # Process any pending contacts
            if self.manager:
                self._process_pending_contacts()

            tx_form = FldigiTransmitForm()
            log_form = FldigiLogContactForm()

            return render_template(
                'fldigi/index.html',
                plugin=self,
                status=status,
                logs=logs,
                modes=modes[:30],  # Limit for UI
                tx_form=tx_form,
                log_form=log_form,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=self.manager.config if self.manager else {}
            )

        # ============================================================
        # Modem/Mode Control
        # ============================================================
        @bp.route('/modem')
        @login_required
        def modem():
            """FLdigi modem control and monitoring page."""
            status = (
                self.manager.get_status()
                if self.manager else {}
            )
            modes = (
                self.manager.get_available_modes()
                if self.manager else []
            )
            rx_text = (
                self.manager.get_rx_text()
                if self.manager else ''
            )
            tx_form = FldigiTransmitForm()

            return render_template(
                'fldigi/modem.html',
                plugin=self,
                status=status,
                modes=modes,
                rx_text=rx_text,
                tx_form=tx_form,
                config=self.manager.config if self.manager else {}
            )

        # ============================================================
        # Logbook Page
        # ============================================================
        @bp.route('/logbook')
        @login_required
        def logbook():
            """FLdigi contacts from central logbook."""
            from models import db
            from models.logbook import ContactLog

            # Get digital mode contacts from logbook
            digital_modes = [
                'BPSK31', 'BPSK63', 'BPSK125', 'QPSK31',
                'RTTY', 'MFSK-16', 'CW', 'WSPR',
                'OLIVIA-8/500'
            ]

            contacts = ContactLog.query.filter(
                ContactLog.operator_id == current_user.id,
                ContactLog.mode.in_(digital_modes)
            ).order_by(
                ContactLog.timestamp.desc()
            ).limit(100).all()

            log_form = FldigiLogContactForm()

            return render_template(
                'fldigi/logbook.html',
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
            """FLdigi plugin settings page."""
            form = FldigiSettingsForm()

            # Pre-populate from config
            if request.method == 'GET' and self.manager:
                cfg = self.manager.config
                form.xmlrpc_host.data = cfg.get(
                    'xmlrpc_host', 'localhost'
                )
                form.xmlrpc_port.data = cfg.get(
                    'xmlrpc_port', 7362
                )
                form.launch_mode.data = cfg.get(
                    'launch_mode', 'connect'
                )
                form.display.data = cfg.get('display', ':0')
                form.default_mode.data = cfg.get(
                    'default_mode', 'BPSK31'
                )
                form.default_frequency.data = cfg.get(
                    'default_frequency', 14070000
                )
                form.callsign.data = cfg.get(
                    'callsign', current_user.callsign
                )
                form.locator.data = cfg.get('locator', '')
                form.auto_start.data = cfg.get(
                    'auto_start', False
                )
                form.auto_connect.data = cfg.get(
                    'auto_connect', True
                )
                form.log_rx_contacts.data = cfg.get(
                    'log_rx_contacts', True
                )
                form.monitor_interval.data = cfg.get(
                    'monitor_interval', 5
                )

            if form.validate_on_submit():
                config_data = {
                    'xmlrpc_host': form.xmlrpc_host.data,
                    'xmlrpc_port': form.xmlrpc_port.data,
                    'launch_mode': form.launch_mode.data,
                    'display': form.display.data or ':0',
                    'default_mode': form.default_mode.data,
                    'default_frequency': (
                        form.default_frequency.data
                    ),
                    'callsign': (
                        form.callsign.data.upper()
                        if form.callsign.data else ''
                    ),
                    'locator': (
                        form.locator.data.upper()
                        if form.locator.data else ''
                    ),
                    'auto_start': form.auto_start.data,
                    'auto_connect': form.auto_connect.data,
                    'log_rx_contacts': form.log_rx_contacts.data,
                    'monitor_interval': form.monitor_interval.data
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
                'fldigi/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # API: Start FLdigi
        # ============================================================
        @bp.route('/api/start', methods=['POST'])
        @login_required
        def api_start():
            """Start FLdigi process via API."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            if not self.install_complete:
                return jsonify({
                    'success': False,
                    'error': 'FLdigi not installed'
                }), 503

            success, message = self.manager.start_fldigi()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Connect to existing FLdigi
        # ============================================================
        @bp.route('/api/connect', methods=['POST'])
        @login_required
        def api_connect():
            """Connect to existing FLdigi instance."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            success, message = self.manager.connect_to_existing()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Stop FLdigi
        # ============================================================
        @bp.route('/api/stop', methods=['POST'])
        @login_required
        def api_stop():
            """Stop FLdigi via API."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            success, message = self.manager.stop_fldigi()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Status
        # ============================================================
        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get FLdigi status via API."""
            if not self.manager:
                return jsonify({
                    'xmlrpc_connected': False,
                    'process_running': False
                })

            return jsonify(self.manager.get_status())

        # ============================================================
        # API: Set Mode
        # ============================================================
        @bp.route('/api/set_mode', methods=['POST'])
        @login_required
        def api_set_mode():
            """Set FLdigi operating mode."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            data = request.get_json() or {}
            mode = data.get('mode', '')

            if not mode:
                return jsonify({
                    'success': False,
                    'error': 'Mode required'
                }), 400

            success, message = self.manager.set_mode(mode)

            return jsonify({
                'success': success,
                'message': message
            })

        # ============================================================
        # API: Set Frequency
        # ============================================================
        @bp.route('/api/set_frequency', methods=['POST'])
        @login_required
        def api_set_frequency():
            """Set radio frequency."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            data = request.get_json() or {}
            freq_hz = data.get('frequency')

            if not freq_hz:
                return jsonify({
                    'success': False,
                    'error': 'Frequency required'
                }), 400

            success, message = self.manager.set_frequency(
                int(freq_hz)
            )

            return jsonify({
                'success': success,
                'message': message
            })

        # ============================================================
        # API: Send Text
        # ============================================================
        @bp.route('/api/send_text', methods=['POST'])
        @login_required
        def api_send_text():
            """Queue text for FLdigi transmission."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            data = request.get_json() or {}
            text = data.get('text', '')
            transmit = data.get('transmit', True)
            mode = data.get('mode')

            if not text:
                return jsonify({
                    'success': False,
                    'error': 'Text required'
                }), 400

            # Optionally set mode first
            if mode:
                self.manager.set_mode(mode)

            success, message = self.manager.send_text(
                text, transmit
            )

            return jsonify({
                'success': success,
                'message': message
            })

        # ============================================================
        # API: Abort TX
        # ============================================================
        @bp.route('/api/abort', methods=['POST'])
        @login_required
        def api_abort():
            """Abort current transmission."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            success, message = self.manager.abort_tx()

            return jsonify({
                'success': success,
                'message': message
            })

        # ============================================================
        # API: Get RX Text
        # ============================================================
        @bp.route('/api/rx_text')
        @login_required
        def api_rx_text():
            """Get current RX buffer text."""
            if not self.manager:
                return jsonify({'text': ''})

            return jsonify({
                'text': self.manager.get_rx_text()
            })

        # ============================================================
        # API: Get Logs
        # ============================================================
        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """Get plugin log entries."""
            limit = request.args.get('limit', 100, type=int)

            if not self.manager:
                return jsonify({'logs': []})

            return jsonify({
                'logs': self.manager.get_logs(limit)
            })

        # ============================================================
        # API: Log Contact
        # ============================================================
        @bp.route('/api/log_contact', methods=['POST'])
        @login_required
        def api_log_contact():
            """Log a contact to the central logbook."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data'
                    }), 400

                success = self._log_fldigi_contact(
                    callsign=data.get('callsign', ''),
                    mode=data.get('mode', 'BPSK31'),
                    frequency=data.get('frequency'),
                    band=data.get('band', ''),
                    rst_sent=data.get('rst_sent', '599'),
                    rst_rcvd=data.get('rst_rcvd', '599'),
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
        # API: Install
        # ============================================================
        @bp.route('/api/install', methods=['POST'])
        @login_required
        def api_install():
            """Trigger FLdigi installation."""
            try:
                if os.path.exists(self.installer.INSTALL_MARKER):
                    os.remove(self.installer.INSTALL_MARKER)

                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None
                    self.manager = FldigiManager(
                        config_dir=self.plugin_data_dir
                    )

                return jsonify({
                    'success': success,
                    'message': (
                        'FLdigi installed!' if success
                        else 'Installation failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

    def _process_pending_contacts(self):
        """
        Process pending contacts from FLdigi log panel.

        Gets contacts detected by the monitor thread
        and logs them to the central logbook if
        auto-logging is enabled.
        """
        if not self.manager:
            return

        if not self.manager.config.get('log_rx_contacts', True):
            return

        pending = self.manager.get_pending_contacts()

        for contact in pending:
            callsign = contact.get('callsign', '').strip()
            if not callsign:
                continue

            freq_str = contact.get('frequency', '')
            try:
                freq_mhz = float(freq_str) if freq_str else None
            except (ValueError, TypeError):
                freq_mhz = None

            self._log_fldigi_contact(
                callsign=callsign,
                mode=contact.get('mode', 'BPSK31'),
                frequency=freq_mhz,
                rst_sent=contact.get('rst_out', '599'),
                rst_rcvd=contact.get('rst_in', '599'),
                grid=contact.get('gridsquare', ''),
                notes=f"Auto-logged from FLdigi: "
                      f"{contact.get('exchange', '')}"
            )

    def _log_fldigi_contact(self, callsign, mode='BPSK31',
                             frequency=None, band=None,
                             rst_sent='599', rst_rcvd='599',
                             grid='', notes=''):
        """
        Log a FLdigi contact to the central logbook.

        Uses the base plugin log_contact() method to
        create a standardized logbook entry.

        Args:
            callsign: Contact callsign
            mode: Digital mode (BPSK31, RTTY, etc.)
            frequency: Frequency in MHz
            band: Band designation
            rst_sent: RST report sent
            rst_rcvd: RST report received
            grid: Maidenhead grid locator
            notes: Additional notes

        Returns:
            bool: True if logged successfully
        """
        try:
            if not callsign or not callsign.strip():
                return False

            # Get GPS grid if not provided
            contact_grid = grid
            if not contact_grid:
                contact_grid = self.manager.config.get(
                    'locator', ''
                ) if self.manager else ''

                gps = self.get_device('gps')
                if gps and gps.is_connected():
                    pos = gps.get_position()
                    if pos:
                        contact_grid = pos.get(
                            'grid', contact_grid
                        )

            # Determine band from frequency if not provided
            contact_band = band
            if not contact_band and frequency:
                contact_band = self._freq_to_band(frequency)

            contact_data = {
                'callsign': callsign.upper().strip(),
                'mode': mode.upper(),
                'band': contact_band or None,
                'frequency': frequency,
                'grid': contact_grid or None,
                'rst_sent': rst_sent or '599',
                'rst_rcvd': rst_rcvd or '599',
                'notes': (
                    f"FLdigi: {notes}" if notes
                    else "Logged via FLdigi"
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
        Convert frequency in MHz to band designation.

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
        ]

        for low, high, band in bands:
            if low <= freq_mhz <= high:
                return band

        return None