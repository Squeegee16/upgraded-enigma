"""
OpenWebRX Plugin
=================
Main plugin class integrating OpenWebRX SDR receiver
into the Ham Radio Web Application.

Architecture:
    OpenWebRX runs as a Docker sidecar container
    (jketterl/openwebrx:stable). This plugin:

    1. Embeds the OpenWebRX web interface in an iframe
    2. Communicates with OpenWebRX via HTTP API
    3. Polls for decoded digital mode signals
    4. Logs qualifying signals to the central logbook
    5. Provides a settings page for configuration
    6. Shows a contacts/spots page with log button

    The OpenWebRX container is started and managed by
    docker-compose.yml, not by this plugin.

Source: https://github.com/jketterl/openwebrx
"""

import os
import json
import traceback
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request,
    redirect, url_for, flash
)
from flask_login import login_required, current_user

from plugins.base import BasePlugin
from plugins.implementations.openwebrx.installer import (
    OpenWebRXInstaller
)
from plugins.implementations.openwebrx.openwebrx_manager import (
    OpenWebRXManager
)
from plugins.implementations.openwebrx.forms import (
    OpenWebRXSettingsForm,
    OpenWebRXLogForm
)


class OpenWebRXPlugin(BasePlugin):
    """
    OpenWebRX SDR Receiver Plugin.

    Provides web-based SDR access via OpenWebRX with
    signal logging and logbook integration.
    """

    name = "OpenWebRX"
    description = (
        "Web-based SDR receiver with digital mode "
        "decoding and signal logging"
    )
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://github.com/jketterl/openwebrx"

    def __init__(self, app=None, devices=None):
        """Initialise OpenWebRX plugin."""
        super().__init__(app, devices)

        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins', 'openwebrx'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        self.installer = OpenWebRXInstaller()
        self.manager = None

        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize the OpenWebRX plugin.

        Checks Python dependencies, creates the manager,
        updates GPS position, syncs radio frequency,
        and starts spot polling.

        Returns:
            bool: True if initialization successful
        """
        print(f"\n[{self.name}][PLUGIN] Initializing plugin...")

        try:
            # Install Python dependencies
            install_success = self.installer.run()
            self.install_complete = install_success

            # Create manager
            self.manager = OpenWebRXManager(
                config_dir=self.plugin_data_dir
            )

            # Update GPS locator if available
            self._update_gps_locator()

            # Set callsign from user if not configured
            if not self.manager.config.get('callsign'):
                try:
                    cs = getattr(
                        current_user, 'callsign', ''
                    )
                    if cs:
                        self.manager.save_config(
                            {'callsign': cs}
                        )
                except RuntimeError:
                    pass  # Outside request context

            # Check OpenWebRX availability
            if self.manager.is_available():
                print(
                    f"[{self.name}][PLUGIN] ✓ OpenWebRX "
                    f"accessible at "
                    f"{self.manager.base_url}"
                )
                self.install_complete = True
                self.install_error = None

                # Start spot polling
                if self.manager.config.get(
                    'log_ft8', True
                ) or self.manager.config.get(
                    'log_wspr', True
                ):
                    self.manager.start_polling()
            else:
                print(
                    f"[{self.name}][PLUGIN] INFO: OpenWebRX "
                    f"not reachable at "
                    f"{self.manager.base_url}"
                )
                print(
                    f"[{self.name}][PLUGIN] INFO: Ensure the "
                    f"openwebrx Docker service is running:"
                    f" docker compose up -d openwebrx"
                )

            print(f"[{self.name}][PLUGIN] ✓ Plugin initialized")
            return True

        except Exception as e:
            self.install_error = str(e)
            print(f"[{self.name}] ERROR: {e}")
            traceback.print_exc()
            return False

    def shutdown(self):
        """Clean shutdown."""
        print(f"[{self.name}][PLUGIN] Shutting down...")
        if self.manager:
            self.manager.stop_polling()
        print(f"[{self.name}][PLUGIN] ✓ Shutdown complete")

    def _update_gps_locator(self):
        """Update grid locator from GPS device."""
        try:
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos and pos.get('grid'):
                    if not self.manager.config.get(
                        'locator'
                    ):
                        self.manager.save_config(
                            {'locator': pos['grid']}
                        )
                        print(
                            f"[{self.name}][PLUGIN] ✓ Grid: "
                            f"{pos['grid']}"
                        )
        except Exception as e:
            print(f"[{self.name}][PLUGIN] GPS warning: {e}")

    def get_blueprint(self):
        """Create Flask Blueprint."""
        plugin_dir = os.path.dirname(
            os.path.abspath(__file__)
        )
        template_dir = os.path.join(
            plugin_dir, 'templates'
        )

        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/openwebrx',
            template_folder=template_dir
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """Register all plugin routes."""

        # ======================================================
        # Main page — embedded OpenWebRX receiver
        # ======================================================
        @bp.route('/')
        @login_required
        def index():
            """
            Main OpenWebRX plugin page.

            Shows the embedded OpenWebRX interface plus
            recent signal spots and quick controls.
            """
            try:
                status = (
                    self.manager.get_full_status()
                    if self.manager else {}
                )
                spots = (
                    self.manager.get_spots(limit=20)
                    if self.manager else []
                )
                log_form = OpenWebRXLogForm()

                # Radio device info for display
                radio_info = {}
                radio = self.get_device('radio')
                if radio and radio.is_connected():
                    try:
                        radio_info = radio.get_info()
                    except Exception:
                        pass

                # GPS position
                gps_data = {}
                gps = self.get_device('gps')
                if gps and gps.is_connected():
                    try:
                        pos = gps.get_position()
                        if pos:
                            gps_data = pos
                    except Exception:
                        pass

                return render_template(
                    'openwebrx/index.html',
                    plugin=self,
                    status=status,
                    spots=spots,
                    log_form=log_form,
                    radio_info=radio_info,
                    gps_data=gps_data,
                    config=self.manager.config
                    if self.manager else {},
                    install_complete=self.install_complete,
                    install_error=self.install_error,
                )

            except Exception as e:
                print(
                    f"[{self.name}] Index error: {e}"
                )
                traceback.print_exc()
                return render_template(
                    'errors/500.html', error=str(e)
                ), 500

        # ======================================================
        # Contacts / Spots page
        # ======================================================
        @bp.route('/contacts')
        @login_required
        def contacts():
            """
            Signal spots and contact logging page.

            Shows all collected signal spots from OpenWebRX
            with one-click logging to the central logbook.
            """
            try:
                mode_filter = request.args.get(
                    'mode', None
                )
                spots = (
                    self.manager.get_spots(
                        limit=200,
                        mode_filter=mode_filter
                    )
                    if self.manager else []
                )

                # Get logged contacts from logbook
                from models.logbook import ContactLog
                logged_contacts = (
                    ContactLog.query.filter_by(
                        operator_id=current_user.id
                    ).filter(
                        ContactLog.notes.like(
                            '%OpenWebRX%'
                        )
                    ).order_by(
                        ContactLog.timestamp.desc()
                    ).limit(50).all()
                )

                log_form = OpenWebRXLogForm()
                status = (
                    self.manager.get_full_status()
                    if self.manager else {}
                )

                return render_template(
                    'openwebrx/contacts.html',
                    plugin=self,
                    spots=spots,
                    logged_contacts=logged_contacts,
                    log_form=log_form,
                    mode_filter=mode_filter,
                    status=status,
                    config=self.manager.config
                    if self.manager else {},
                )

            except Exception as e:
                print(
                    f"[{self.name}] Contacts error: {e}"
                )
                traceback.print_exc()
                return render_template(
                    'errors/500.html', error=str(e)
                ), 500

        # ======================================================
        # Settings page
        # ======================================================
        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """Settings and configuration page."""
            try:
                form = OpenWebRXSettingsForm()

                if request.method == 'GET' and \
                        self.manager:
                    cfg = self.manager.config
                    form.openwebrx_url.data = cfg.get(
                        'openwebrx_url',
                        'http://openwebrx:8073'
                    )
                    form.http_port.data = cfg.get(
                        'http_port', 8073
                    )
                    form.receiver_name.data = cfg.get(
                        'receiver_name', 'Ham Radio SDR'
                    )
                    form.callsign.data = cfg.get(
                        'callsign',
                        getattr(
                            current_user, 'callsign', ''
                        )
                    )
                    form.locator.data = cfg.get(
                        'locator', ''
                    )
                    form.log_ft8.data = cfg.get(
                        'log_ft8', True
                    )
                    form.log_wspr.data = cfg.get(
                        'log_wspr', True
                    )
                    form.log_aprs.data = cfg.get(
                        'log_aprs', True
                    )
                    form.log_other.data = cfg.get(
                        'log_other', False
                    )
                    form.min_snr_log.data = cfg.get(
                        'min_snr_log', -20
                    )
                    form.poll_interval.data = cfg.get(
                        'poll_interval', 15
                    )

                if form.validate_on_submit():
                    new_config = {
                        'openwebrx_url': (
                            form.openwebrx_url.data
                        ),
                        'http_port': form.http_port.data,
                        'receiver_name': (
                            form.receiver_name.data or
                            'Ham Radio SDR'
                        ),
                        'callsign': (
                            form.callsign.data.upper()
                            if form.callsign.data
                            else ''
                        ),
                        'locator': (
                            form.locator.data.upper()
                            if form.locator.data
                            else ''
                        ),
                        'log_ft8': form.log_ft8.data,
                        'log_wspr': form.log_wspr.data,
                        'log_aprs': form.log_aprs.data,
                        'log_other': form.log_other.data,
                        'min_snr_log': (
                            form.min_snr_log.data
                        ),
                        'poll_interval': (
                            form.poll_interval.data
                        ),
                    }

                    if form.admin_password.data:
                        new_config['admin_password'] = (
                            form.admin_password.data
                        )

                    if self.manager and \
                            self.manager.save_config(
                                new_config
                            ):
                        # Restart polling with new settings
                        self.manager.stop_polling()
                        if (
                            new_config['log_ft8'] or
                            new_config['log_wspr'] or
                            new_config['log_aprs']
                        ):
                            self.manager.start_polling()

                        flash(
                            '[PLUGIN] Settings saved!', 'success'
                        )
                    else:
                        flash(
                            '[PLUGIN] Error saving settings',
                            'danger'
                        )

                    return redirect(
                        url_for(
                            f'{self.name}.settings'
                        )
                    )

                status = (
                    self.manager.get_full_status()
                    if self.manager else {}
                )

                return render_template(
                    'openwebrx/settings.html',
                    plugin=self,
                    form=form,
                    status=status,
                    config=self.manager.config
                    if self.manager else {},
                    install_complete=self.install_complete,
                    install_error=self.install_error,
                )

            except Exception as e:
                print(
                    f"[{self.name}][PLUGIN] Settings error: {e}"
                )
                traceback.print_exc()
                return render_template(
                    'errors/500.html', error=str(e)
                ), 500

        # ======================================================
        # API: Status
        # ======================================================
        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get OpenWebRX status."""
            try:
                if not self.manager:
                    return jsonify({
                        'available': False,
                        'error': 'Manager not initialized'
                    })
                return jsonify(
                    self.manager.get_full_status()
                )
            except Exception as e:
                return jsonify({
                    'available': False,
                    'error': str(e)
                })

        # ======================================================
        # API: Get spots
        # ======================================================
        @bp.route('/api/spots')
        @login_required
        def api_spots():
            """Get signal spots."""
            try:
                limit = request.args.get(
                    'limit', 50, type=int
                )
                mode = request.args.get('mode', None)

                if not self.manager:
                    return jsonify({'spots': []})

                spots = self.manager.get_spots(
                    limit=limit,
                    mode_filter=mode
                )
                return jsonify({
                    'spots': spots,
                    'count': len(spots)
                })
            except Exception as e:
                return jsonify({
                    'spots': [], 'error': str(e)
                })

        # ======================================================
        # API: Clear spots
        # ======================================================
        @bp.route('/api/clear_spots', methods=['POST'])
        @login_required
        def api_clear_spots():
            """Clear accumulated spots."""
            try:
                if self.manager:
                    self.manager.clear_spots()
                return jsonify({
                    'success': True,
                    'message': 'Spots cleared'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        # ======================================================
        # API: Log a spot as a contact
        # ======================================================
        @bp.route('/api/log_contact', methods=['POST'])
        @login_required
        def api_log_contact():
            """Log a signal spot to the central logbook."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data provided'
                    }), 400

                callsign = data.get(
                    'callsign', ''
                ).strip().upper()
                if not callsign:
                    return jsonify({
                        'success': False,
                        'error': 'Callsign required'
                    }), 400

                frequency = data.get('frequency')
                mode = data.get('mode', 'FT8')
                snr = data.get('snr', '')
                grid = data.get('grid', '')
                band = data.get('band', '')
                notes = data.get('notes', '')

                success = self._log_signal_contact(
                    callsign=callsign,
                    frequency=frequency,
                    mode=mode,
                    snr=snr,
                    grid=grid,
                    band=band,
                    notes=notes
                )

                return jsonify({
                    'success': success,
                    'message': (
                        f'{callsign} logged!'
                        if success
                        else 'Logging failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        # ======================================================
        # API: Start/stop spot polling
        # ======================================================
        @bp.route(
            '/api/polling/start', methods=['POST']
        )
        @login_required
        def api_start_polling():
            """Start spot polling."""
            try:
                if not self.manager:
                    return jsonify({
                        'success': False
                    }), 503
                started = self.manager.start_polling()
                return jsonify({
                    'success': True,
                    'message': (
                        'Polling started'
                        if started
                        else 'Already polling'
                    )
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/polling/stop', methods=['POST'])
        @login_required
        def api_stop_polling():
            """Stop spot polling."""
            try:
                if self.manager:
                    self.manager.stop_polling()
                return jsonify({
                    'success': True,
                    'message': 'Polling stopped'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        # ======================================================
        # API: Sync frequency with radio
        # ======================================================
        @bp.route(
            '/api/sync_frequency', methods=['POST']
        )
        @login_required
        def api_sync_frequency():
            """Sync OpenWebRX frequency from radio."""
            try:
                radio = self.get_device('radio')
                if not radio or not radio.is_connected():
                    return jsonify({
                        'success': False,
                        'error': (
                            'Radio not connected. '
                            'Check radio device settings.'
                        )
                    })

                freq_mhz = radio.get_frequency()
                if not freq_mhz:
                    return jsonify({
                        'success': False,
                        'error': 'Could not read frequency'
                    })

                return jsonify({
                    'success': True,
                    'frequency_mhz': freq_mhz,
                    'frequency_hz': int(
                        freq_mhz * 1_000_000
                    ),
                    'message': (
                        f'Radio frequency: '
                        f'{freq_mhz:.3f} MHz'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        # ======================================================
        # API: Logs
        # ======================================================
        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """Get plugin log entries."""
            try:
                limit = request.args.get(
                    'limit', 50, type=int
                )
                if not self.manager:
                    return jsonify({'logs': []})
                return jsonify({
                    'logs': self.manager.get_logs(limit)
                })
            except Exception as e:
                return jsonify({
                    'logs': [], 'error': str(e)
                })

    def _log_signal_contact(
        self, callsign, frequency=None, mode='FT8',
        snr='', grid='', band='', notes=''
    ):
        """
        Log a detected signal to the central logbook.

        Args:
            callsign: Decoded callsign
            frequency: Signal frequency in MHz
            mode: Digital mode (FT8, WSPR, etc.)
            snr: Signal-to-noise ratio
            grid: Maidenhead grid locator
            band: Band designation
            notes: Additional notes

        Returns:
            bool: True if logged successfully
        """
        try:
            if not callsign:
                return False

            # Determine band from frequency if not given
            contact_band = band
            if not contact_band and frequency:
                contact_band = self._freq_to_band(
                    float(frequency)
                )

            # Build notes string
            note_parts = ['OpenWebRX']
            if snr:
                note_parts.append(f'SNR:{snr}dB')
            if grid:
                note_parts.append(f'Grid:{grid}')
            if notes:
                note_parts.append(notes)

            contact_data = {
                'callsign': callsign.upper().strip(),
                'mode': mode.upper(),
                'band': contact_band or None,
                'frequency': (
                    float(frequency)
                    if frequency else None
                ),
                'grid': grid or None,
                'rst_sent': None,
                'rst_rcvd': snr or None,
                'notes': ' | '.join(note_parts)
            }

            success = self.log_contact(contact_data)

            if success:
                print(
                    f"[{self.name}] ✓ Logged: "
                    f"{callsign} {mode}"
                )

            return success

        except Exception as e:
            print(f"[{self.name}][PLUGIN] Log error: {e}")
            return False

    @staticmethod
    def _freq_to_band(freq_mhz):
        """Convert frequency to band designation."""
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
            (1240.0, 1300.0, '23cm'),
        ]
        for low, high, band in bands:
            if low <= float(freq_mhz) <= high:
                return band
        return None
