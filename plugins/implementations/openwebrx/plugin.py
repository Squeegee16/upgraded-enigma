"""
OpenWebRX Plugin
=================
Main plugin class integrating OpenWebRX SDR receiver
into the Ham Radio Web Application.

OpenWebRX provides:
    - Multi-user web-based SDR interface
    - Wide waterfall display
    - Multiple demodulation modes
    - Digital mode decoding (FT8, WSPR, APRS, etc.)
    - Real-time spectrum analysis

Source: https://fms.komkon.org/OWRX/
GitHub: https://github.com/jketterl/openwebrx

Usage:
    Copy the openwebrx/ directory to plugins/implementations/
    Dependencies will be installed automatically on first run.

Integration:
    - Detected digital mode signals can be logged to the
      central logbook via the log_contact() method.
    - GPS position is used for receiver location.
    - Radio frequency can be synced with the main radio.
"""

import os
import json
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request,
    redirect, url_for, flash
)
from flask_login import login_required, current_user

# Import base plugin class
from plugins.base import BasePlugin

# Import OpenWebRX specific modules
from plugins.implementations.openwebrx.installer import OpenWebRXInstaller
from plugins.implementations.openwebrx.openwebrx_manager import OpenWebRXManager
from plugins.implementations.openwebrx.forms import (
    OpenWebRXSettingsForm,
    SignalLogForm
)


class OpenWebRXPlugin(BasePlugin):
    """
    OpenWebRX SDR Receiver Plugin.

    Integrates OpenWebRX web-based SDR receiver into the
    Ham Radio Application. Provides signal monitoring,
    digital mode decoding, and logbook integration.
    """

    # Plugin metadata
    name = "OpenWebRX"
    description = "Multi-user web-based SDR receiver with digital mode decoding"
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://fms.komkon.org/OWRX/"

    def __init__(self, app=None, devices=None):
        """
        Initialize OpenWebRX plugin.

        Args:
            app: Flask application instance
            devices: Dictionary of available device interfaces
        """
        super().__init__(app, devices)

        # Plugin data directory for persistent storage
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'openwebrx'
        )

        # Ensure data directory exists
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Installer instance
        self.installer = OpenWebRXInstaller()

        # Manager instance (initialized after install check)
        self.manager = None

        # Installation state
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """Initialize OpenWebRX plugin for sidecar deployment."""
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Run installation check
            install_success = self.installer.run()

            if not install_success:
                self.install_error = (
                    "OpenWebRX installation check failed. "
                    "Ensure the openwebrx Docker service "
                    "is running."
                )

            self.install_complete = install_success

            # Detect deployment method
            # Check if running in Docker with sidecar
            openwebrx_url = os.environ.get(
                'OPENWEBRX_URL', ''
            )
            install_info = self.installer.get_install_info()
            install_method = install_info.get(
                'method', 'sidecar'
            )

            if openwebrx_url or os.path.exists('/.dockerenv'):
                # Docker deployment - use sidecar mode
                install_method = 'sidecar'
                print(
                    f"[{self.name}] Docker sidecar mode: "
                    f"{openwebrx_url or 'http://openwebrx:8073'}"
                )

            # Initialise manager
            self.manager = OpenWebRXManager(
                config_dir=self.plugin_data_dir,
                install_method=install_method,
                http_port=8073
            )

            # GPS integration
            self._update_gps_position()

            # Radio frequency sync
            self._sync_radio_frequency()

            # Check if OpenWebRX is already running
            if self.manager.is_available():
                self.install_complete = True
                self.install_error = None
                print(
                    f"[{self.name}] ✓ OpenWebRX is "
                    f"accessible at "
                    f"{self.manager.base_url}"
                )

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
        Clean shutdown of the plugin.
        Stops OpenWebRX if running.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            status = self.manager.get_status()
            if status.get('running'):
                success, message = self.manager.stop()
                print(f"[{self.name}] Stop: {message}")

        print(f"[{self.name}] ✓ Shutdown complete")

    def _update_gps_position(self):
        """
        Update receiver GPS position from GPS device.

        Reads current GPS position and updates the
        OpenWebRX receiver configuration.
        """
        try:
            gps_device = self.get_device('gps')

            if gps_device and gps_device.is_connected():
                position = gps_device.get_position()

                if position:
                    # Update manager config with GPS position
                    self.manager.save_config({
                        'receiver_gps': {
                            'lat': round(position.get('latitude', 0), 6),
                            'lon': round(position.get('longitude', 0), 6)
                        },
                        'receiver_asl': int(position.get('altitude', 0))
                    })

                    print(f"[{self.name}] ✓ GPS position updated: "
                          f"{position.get('grid', 'Unknown')}")

        except Exception as e:
            print(f"[{self.name}] GPS update warning: {e}")

    def _sync_radio_frequency(self):
        """
        Sync initial SDR frequency with main radio if available.

        Gets current radio frequency and uses it as the
        initial OpenWebRX tuning frequency.
        """
        try:
            radio_device = self.get_device('radio')

            if radio_device and radio_device.is_connected():
                freq_mhz = radio_device.get_frequency()

                if freq_mhz:
                    freq_hz = int(freq_mhz * 1_000_000)
                    self.manager.save_config({
                        'initial_frequency': freq_hz
                    })
                    print(f"[{self.name}] ✓ Radio frequency synced: "
                          f"{freq_mhz} MHz")

        except Exception as e:
            print(f"[{self.name}] Radio sync warning: {e}")

    def get_blueprint(self):
        """
        Create and return the Flask Blueprint.

        Creates routes for the OpenWebRX plugin UI,
        API endpoints, and logbook integration.

        Returns:
            Blueprint: Configured Flask blueprint
        """
        # Blueprint with plugin template folder
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/openwebrx',
            template_folder=os.path.join(
                os.path.dirname(__file__),
                'templates'
            )
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """
        Register all plugin routes on the blueprint.

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
            OpenWebRX main plugin page.

            Shows status, embedded receiver, and
            recent signal detections.
            """
            if not self.manager:
                return render_template(
                    'openwebrx/index.html',
                    plugin=self,
                    status={},
                    signals=[],
                    logs=[],
                    install_complete=self.install_complete,
                    install_error=self.install_error,
                    config={}
                )

            status = self.manager.get_status()
            signals = self.manager.get_detected_signals(20)
            logs = self.manager.get_logs(50)

            return render_template(
                'openwebrx/index.html',
                plugin=self,
                status=status,
                signals=signals,
                logs=logs,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=self.manager.config
            )

        # ============================================================
        # Settings Route
        # ============================================================
        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """
            OpenWebRX settings and configuration page.
            """
            form = OpenWebRXSettingsForm()

            # Pre-populate with current config
            if request.method == 'GET' and self.manager:
                cfg = self.manager.config
                form.http_port.data = cfg.get('http_port', 8073)
                form.receiver_name.data = cfg.get(
                    'receiver_name', current_user.callsign
                )
                form.receiver_location.data = cfg.get('receiver_location', '')
                form.receiver_asl.data = cfg.get('receiver_asl', 0)
                form.receiver_admin.data = cfg.get('receiver_admin',
                                                   current_user.callsign)
                form.sdr_type.data = cfg.get('sdr_type', 'rtlsdr')
                form.sdr_device_index.data = cfg.get('sdr_device_index', 0)
                form.gain.data = cfg.get('gain', 30)
                form.ppm.data = cfg.get('ppm', 0)
                form.initial_frequency.data = cfg.get(
                    'initial_frequency', 145000000
                )
                form.initial_modulation.data = cfg.get(
                    'initial_modulation', 'nfm'
                )
                form.log_signals.data = cfg.get('log_signals', True)
                form.min_signal_strength.data = cfg.get(
                    'min_signal_strength', -70
                )
                form.auto_start.data = cfg.get('auto_start', False)

            if form.validate_on_submit():
                config_data = {
                    'http_port': form.http_port.data,
                    'receiver_name': form.receiver_name.data,
                    'receiver_location': form.receiver_location.data or '',
                    'receiver_asl': form.receiver_asl.data or 0,
                    'receiver_admin': form.receiver_admin.data or '',
                    'sdr_type': form.sdr_type.data,
                    'sdr_device_index': form.sdr_device_index.data or 0,
                    'gain': form.gain.data,
                    'ppm': form.ppm.data or 0,
                    'initial_frequency': form.initial_frequency.data,
                    'initial_modulation': form.initial_modulation.data,
                    'log_signals': form.log_signals.data,
                    'min_signal_strength': form.min_signal_strength.data,
                    'auto_start': form.auto_start.data
                }

                if self.manager and self.manager.save_config(config_data):
                    # Regenerate OpenWebRX config file
                    self.manager.generate_openwebrx_config()
                    flash('Settings saved! Restart OpenWebRX to apply.', 'success')
                else:
                    flash('Error saving settings.', 'danger')

                return redirect(url_for(f'{self.name}.settings'))

            return render_template(
                'openwebrx/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # Signal Contacts Route
        # ============================================================
        @bp.route('/contacts')
        @login_required
        def contacts():
            """
            View signals detected by OpenWebRX.

            Shows decoded digital mode signals and allows
            logging them to the central logbook.
            """
            signals = self.manager.get_detected_signals(50) \
                if self.manager else []

            form = SignalLogForm()

            return render_template(
                'openwebrx/contacts.html',
                plugin=self,
                signals=signals,
                form=form,
                status=self.manager.get_status() if self.manager else {}
            )

        # ============================================================
        # API Routes
        # ============================================================
        @bp.route('/api/start', methods=['POST'])
        @login_required
        def api_start():
            """API endpoint to start OpenWebRX."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Manager not initialized'
                }), 503

            if not self.install_complete:
                return jsonify({
                    'success': False,
                    'error': 'OpenWebRX not installed'
                }), 503

            success, message = self.manager.start()

            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status(),
                'url': self.manager.get_web_url()
            })

        @bp.route('/api/stop', methods=['POST'])
        @login_required
        def api_stop():
            """API endpoint to stop OpenWebRX."""
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

        @bp.route('/api/status')
        @login_required
        def api_status():
            """API endpoint for OpenWebRX status."""
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
            """API endpoint for recent plugin logs."""
            limit = request.args.get('limit', 100, type=int)

            if not self.manager:
                return jsonify({'logs': []})

            return jsonify({'logs': self.manager.get_logs(limit)})

        @bp.route('/api/signals')
        @login_required
        def api_signals():
            """API endpoint for detected signals."""
            limit = request.args.get('limit', 50, type=int)

            if not self.manager:
                return jsonify({'signals': []})

            return jsonify({
                'signals': self.manager.get_detected_signals(limit)
            })

        @bp.route('/api/log_signal', methods=['POST'])
        @login_required
        def api_log_signal():
            """
            API endpoint to log a detected signal to the logbook.

            Accepts signal data and creates a contact log entry
            in the central logbook system.
            """
            try:
                data = request.get_json()

                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data provided'
                    }), 400

                # Build contact data for central logbook
                success = self._log_signal_contact(
                    callsign=data.get('callsign', 'UNKNOWN'),
                    frequency=data.get('frequency'),
                    mode=data.get('mode', 'DIGITAL'),
                    signal_report=data.get('signal_report', ''),
                    notes=data.get('notes', '')
                )

                return jsonify({
                    'success': success,
                    'message': 'Signal logged' if success else 'Logging failed'
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @bp.route('/api/install', methods=['POST'])
        @login_required
        def api_install():
            """API endpoint to trigger or retry installation."""
            try:
                # Remove old marker to force reinstall
                if os.path.exists(self.installer.INSTALL_MARKER):
                    os.remove(self.installer.INSTALL_MARKER)

                # Run installer
                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None

                    # Reinitialize manager
                    install_info = self.installer.get_install_info()
                    self.manager = OpenWebRXManager(
                        config_dir=self.plugin_data_dir,
                        install_method=install_info.get('method', 'docker'),
                        http_port=8073
                    )

                return jsonify({
                    'success': success,
                    'message': 'Installation complete' if success
                    else 'Installation failed'
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @bp.route('/api/sync_frequency', methods=['POST'])
        @login_required
        def api_sync_frequency():
            """
            Sync OpenWebRX frequency with main radio.

            Gets current frequency from Hamlib radio
            and updates OpenWebRX tuning.
            """
            try:
                self._sync_radio_frequency()
                return jsonify({
                    'success': True,
                    'frequency': self.manager.config.get('initial_frequency')
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

    def _log_signal_contact(self, callsign, frequency, mode,
                             signal_report='', notes=''):
        """
        Log a detected signal as a contact in the central logbook.

        Uses the base plugin log_contact() method to create
        a standardized log entry.

        Args:
            callsign: Callsign of detected station
            frequency: Signal frequency in MHz
            mode: Modulation/digital mode
            signal_report: SNR or signal strength report
            notes: Additional notes

        Returns:
            bool: True if logged successfully
        """
        try:
            # Get frequency to band mapping
            band = self._frequency_to_band(frequency) if frequency else None

            # Get GPS grid if available
            grid = None
            gps_device = self.get_device('gps')
            if gps_device and gps_device.is_connected():
                position = gps_device.get_position()
                if position:
                    grid = position.get('grid')

            # Build standardized contact data
            contact_data = {
                'callsign': callsign.upper().strip(),
                'mode': mode.upper(),
                'band': band,
                'frequency': frequency,
                'grid': grid,
                'rst_sent': signal_report or None,
                'rst_rcvd': signal_report or None,
                'notes': f"OpenWebRX detection: {notes}" if notes
                else "OpenWebRX signal detection"
            }

            # Log via base class method (central logbook)
            success = self.log_contact(contact_data)

            if success:
                print(f"[{self.name}] ✓ Signal logged: "
                      f"{callsign} on {frequency} MHz {mode}")
            else:
                print(f"[{self.name}] WARNING: Could not log {callsign}")

            return success

        except Exception as e:
            print(f"[{self.name}] Error logging signal: {e}")
            return False

    @staticmethod
    def _frequency_to_band(freq_mhz):
        """
        Convert frequency to amateur band designation.

        Args:
            freq_mhz: Frequency in MHz

        Returns:
            str: Band designation or None
        """
        if not freq_mhz:
            return None

        # Amateur band frequency ranges
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
            (902.0, 928.0, '33cm'),
            (1240.0, 1300.0, '23cm'),
        ]

        for low, high, band in bands:
            if low <= freq_mhz <= high:
                return band

        return None
