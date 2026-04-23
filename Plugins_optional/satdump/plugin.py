"""
SatDump Plugin
===============
Main plugin class integrating SatDump satellite data
processing into the Ham Radio Web Application.

SatDump provides satellite reception and processing for:
    - NOAA weather satellites (APT, HRPT)
    - METEOR weather satellites (LRPT)
    - GOES geostationary satellites (LRIT/HRIT)
    - Meteosat (MSG, EPS)
    - FengYun Chinese weather satellites
    - ISS SSTV transmissions
    - And many more via pipeline system

Integration Points:
    - SDR device (RTL-SDR, Airspy, etc.)
    - GPS for grid locator and location
    - Central logbook for satellite passes
    - Image gallery for processed products
    - Pipeline management for automated reception

Source: https://github.com/SatDump/SatDump
Documentation: https://docs.satdump.org/

Installation:
    Copy satdump/ directory to plugins/implementations/
    First run installs SatDump and Python dependencies.
"""

import os
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request,
    redirect, url_for, flash, send_from_directory
)
from flask_login import login_required, current_user

from plugins.base import BasePlugin
from plugins.implementations.satdump.installer import (
    SatDumpInstaller
)
from plugins.implementations.satdump.satdump_manager import (
    SatDumpManager
)
from plugins.implementations.satdump.forms import (
    SatDumpSettingsForm,
    SatDumpPipelineForm,
    SatDumpOfflineForm,
    SatDumpLogProductForm
)


class SatDumpPlugin(BasePlugin):
    """
    SatDump Satellite Data Processing Plugin.

    Provides satellite reception, image processing,
    and gallery management with logbook integration.
    """

    # Plugin metadata
    name = "SatDump"
    description = (
        "Satellite data processing for weather, GOES, "
        "METEOR, and more"
    )
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://github.com/SatDump/SatDump"

    def __init__(self, app=None, devices=None):
        """
        Initialize SatDump plugin.

        Args:
            app: Flask application instance
            devices: Available device interfaces
        """
        super().__init__(app, devices)

        # Plugin data directory
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'satdump'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Core components
        self.installer = SatDumpInstaller()
        self.manager = None

        # Installation state
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize plugin on application load.

        Handles installation check, manager initialization,
        GPS integration, and auto-start if configured.

        Returns:
            bool: True if initialization successful
        """
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Check installation
            install_success = self.installer.run()

            if not install_success:
                self.install_error = (
                    "SatDump installation failed. "
                    "Install manually: "
                    "https://docs.satdump.org/building.html"
                )
                print(
                    f"[{self.name}] WARNING: {self.install_error}"
                )

            self.install_complete = install_success

            # Initialize manager
            self.manager = SatDumpManager(
                config_dir=self.plugin_data_dir,
                binary_path=self.installer.satdump_binary_path
            )

            # Update GPS locator and position
            self._update_gps_position()

            # Set callsign if not configured
            if not self.manager.config.get('callsign'):
                callsign = getattr(
                    current_user, 'callsign', ''
                )
                if callsign:
                    self.manager.save_config(
                        {'callsign': callsign}
                    )

            # Auto-start monitoring
            if self.manager.config.get('auto_listen', True):
                success, msg = self.manager.start_monitoring()
                if success:
                    print(f"[{self.name}] ✓ {msg}")
                else:
                    print(f"[{self.name}] Monitor: {msg}")

            # Auto-launch UI if configured
            if (self.manager.config.get('auto_start') and
                    self.install_complete):
                success, msg = self.manager.launch_ui()
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

        Stops all pipelines, monitoring, and UI process.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            self.manager.stop_all_pipelines()
            self.manager.stop_monitoring()

            if self.manager._status.get('ui_running'):
                self.manager.stop_ui()

        print(f"[{self.name}] ✓ Shutdown complete")

    def _update_gps_position(self):
        """
        Update position and grid from GPS device.

        Uses GPS data for the observer location which
        is important for satellite pass prediction.
        """
        try:
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos:
                    updates = {}

                    if pos.get('grid') and not \
                            self.manager.config.get('locator'):
                        updates['locator'] = pos['grid']

                    if updates:
                        self.manager.save_config(updates)
                        print(
                            f"[{self.name}] ✓ GPS position updated"
                        )
        except Exception as e:
            print(f"[{self.name}] GPS warning: {e}")

    def get_blueprint(self):
        """
        Create Flask Blueprint for SatDump UI.

        Returns:
            Blueprint: Configured blueprint with all routes
        """
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/satdump',
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
        # Static File Serving
        # ============================================================
        @bp.route('/gallery/image/<filename>')
        @login_required
        def serve_image(filename):
            """Serve gallery image."""
            gallery_dir = os.path.join(
                self.plugin_data_dir, 'gallery'
            )
            return send_from_directory(gallery_dir, filename)

        @bp.route('/gallery/thumbnail/<filename>')
        @login_required
        def serve_thumbnail(filename):
            """Serve gallery thumbnail."""
            thumb_dir = os.path.join(
                self.plugin_data_dir, 'gallery', 'thumbnails'
            )
            return send_from_directory(thumb_dir, filename)

        # ============================================================
        # Main Dashboard
        # ============================================================
        @bp.route('/')
        @login_required
        def index():
            """SatDump main dashboard."""
            status = (
                self.manager.get_status()
                if self.manager else {}
            )
            logs = (
                self.manager.get_logs(30)
                if self.manager else []
            )
            recent_products = (
                self.manager.get_products(limit=6)
                if self.manager else []
            )
            active_pipelines = (
                self.manager.get_active_pipelines()
                if self.manager else []
            )

            # Get radio frequency
            freq_mhz = None
            radio = self.get_device('radio')
            if radio and radio.is_connected():
                freq_mhz = radio.get_frequency()

            # Get SDR frequency
            sdr = self.get_device('sdr')
            sdr_freq = None
            if sdr and sdr.is_connected():
                sdr_freq = sdr.get_frequency()

            return render_template(
                'satdump/index.html',
                plugin=self,
                status=status,
                logs=logs,
                recent_products=recent_products,
                active_pipelines=active_pipelines,
                freq_mhz=freq_mhz,
                sdr_freq=sdr_freq,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=(
                    self.manager.config if self.manager else {}
                )
            )

        # ============================================================
        # Pipelines Page
        # ============================================================
        @bp.route('/pipelines', methods=['GET', 'POST'])
        @login_required
        def pipelines():
            """Pipeline management page."""
            form = SatDumpPipelineForm()
            offline_form = SatDumpOfflineForm()

            # Populate pipeline choices
            if self.manager:
                all_pipelines = (
                    self.manager.pipeline_manager
                    .get_all_pipelines()
                )
                choices = [
                    (name, f"{name} - {p.get('satellite', '')}")
                    for name, p in all_pipelines.items()
                ]
                form.pipeline.choices = choices
                offline_form.pipeline.choices = choices
            else:
                form.pipeline.choices = [('', 'No pipelines')]
                offline_form.pipeline.choices = [('', 'No pipelines')]

            if form.validate_on_submit():
                if not self.manager:
                    flash('Manager not available', 'danger')
                    return redirect(
                        url_for(f'{self.name}.pipelines')
                    )

                success, message = self.manager.start_pipeline(
                    pipeline_name=form.pipeline.data,
                    frequency_override=form.frequency_override.data,
                    sdr_override=(
                        form.sdr_override.data or None
                    ),
                    output_subdir=form.output_subdir.data,
                    extra_args_str=form.extra_args.data
                )

                if success:
                    flash(f'Pipeline started: {message}', 'success')
                    # Create logbook entry for pass start
                    self._log_satellite_pass(
                        satellite=form.pipeline.data,
                        frequency=form.frequency_override.data,
                        phase='start'
                    )
                else:
                    flash(f'Failed: {message}', 'danger')

                return redirect(
                    url_for(f'{self.name}.pipelines')
                )

            # Get pipeline categories
            categories = {}
            if self.manager:
                categories = (
                    self.manager.pipeline_manager
                    .get_satellites_by_category()
                )

            active = (
                self.manager.get_active_pipelines()
                if self.manager else []
            )

            return render_template(
                'satdump/pipelines.html',
                plugin=self,
                form=form,
                offline_form=offline_form,
                categories=categories,
                active_pipelines=active,
                status=(
                    self.manager.get_status()
                    if self.manager else {}
                ),
                all_pipelines=(
                    self.manager.pipeline_manager
                    .get_all_pipelines()
                    if self.manager else {}
                )
            )

        # ============================================================
        # Products Gallery
        # ============================================================
        @bp.route('/products')
        @login_required
        def products():
            """Satellite data products gallery."""
            page = request.args.get('page', 1, type=int)
            per_page = 12
            offset = (page - 1) * per_page
            satellite_filter = request.args.get('satellite', None)

            if self.manager:
                product_list = self.manager.get_products(
                    limit=per_page,
                    offset=offset,
                    satellite_filter=satellite_filter
                )
                total = self.manager.get_product_count(
                    satellite_filter
                )
            else:
                product_list = []
                total = 0

            total_pages = max(
                1, (total + per_page - 1) // per_page
            )

            # Add URLs to products
            for p in product_list:
                if p.get('thumbnail'):
                    p['thumbnail_url'] = url_for(
                        f'{self.name}.serve_thumbnail',
                        filename=p['thumbnail']
                    )
                if p.get('filename'):
                    p['image_url'] = url_for(
                        f'{self.name}.serve_image',
                        filename=p['filename']
                    )

            log_form = SatDumpLogProductForm()
            passes = (
                self.manager.get_passes(10)
                if self.manager else []
            )

            return render_template(
                'satdump/products.html',
                plugin=self,
                products=product_list,
                page=page,
                total_pages=total_pages,
                total=total,
                satellite_filter=satellite_filter,
                log_form=log_form,
                passes=passes,
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
            """SatDump plugin settings."""
            form = SatDumpSettingsForm()

            if request.method == 'GET' and self.manager:
                cfg = self.manager.config
                form.sdr_source.data = cfg.get(
                    'sdr_source', 'rtlsdr'
                )
                form.sdr_device_id.data = cfg.get(
                    'sdr_device_id', '0'
                )
                form.sdr_gain.data = cfg.get('sdr_gain', 30)
                form.sdr_ppm.data = cfg.get('sdr_ppm', 0)
                form.spyserver_host.data = cfg.get(
                    'spyserver_host', 'localhost'
                )
                form.spyserver_port.data = cfg.get(
                    'spyserver_port', 5555
                )
                form.output_dir.data = cfg.get(
                    'output_dir', self.manager.output_dir
                )
                form.display.data = cfg.get('display', ':0')
                form.callsign.data = cfg.get(
                    'callsign', current_user.callsign
                )
                form.locator.data = cfg.get('locator', '')
                form.auto_listen.data = cfg.get(
                    'auto_listen', True
                )
                form.log_products.data = cfg.get(
                    'log_products', True
                )
                form.auto_start.data = cfg.get(
                    'auto_start', False
                )

            if form.validate_on_submit():
                output_dir = form.output_dir.data
                os.makedirs(output_dir, exist_ok=True)

                config_data = {
                    'sdr_source': form.sdr_source.data,
                    'sdr_device_id': form.sdr_device_id.data,
                    'sdr_gain': form.sdr_gain.data,
                    'sdr_ppm': form.sdr_ppm.data,
                    'spyserver_host': form.spyserver_host.data,
                    'spyserver_port': form.spyserver_port.data,
                    'output_dir': output_dir,
                    'display': form.display.data or ':0',
                    'callsign': (
                        form.callsign.data.upper()
                        if form.callsign.data else ''
                    ),
                    'locator': (
                        form.locator.data.upper()
                        if form.locator.data else ''
                    ),
                    'auto_listen': form.auto_listen.data,
                    'log_products': form.log_products.data,
                    'auto_start': form.auto_start.data
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
                'satdump/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # API Routes
        # ============================================================
        @bp.route('/api/start_ui', methods=['POST'])
        @login_required
        def api_start_ui():
            """Launch SatDump UI."""
            if not self.manager or not self.install_complete:
                return jsonify({
                    'success': False,
                    'error': 'Not ready'
                }), 503

            success, message = self.manager.launch_ui()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/stop_ui', methods=['POST'])
        @login_required
        def api_stop_ui():
            """Stop SatDump UI."""
            if not self.manager:
                return jsonify({'success': False}), 503

            success, message = self.manager.stop_ui()
            return jsonify({
                'success': success,
                'message': message
            })

        @bp.route('/api/start_monitor', methods=['POST'])
        @login_required
        def api_start_monitor():
            """Start data monitoring."""
            if not self.manager:
                return jsonify({'success': False}), 503

            success, message = self.manager.start_monitoring()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/stop_monitor', methods=['POST'])
        @login_required
        def api_stop_monitor():
            """Stop data monitoring."""
            if not self.manager:
                return jsonify({'success': False}), 503

            success, message = self.manager.stop_monitoring()
            return jsonify({
                'success': success,
                'message': message
            })

        @bp.route('/api/stop_pipeline', methods=['POST'])
        @login_required
        def api_stop_pipeline():
            """Stop a running pipeline."""
            if not self.manager:
                return jsonify({'success': False}), 503

            data = request.get_json() or {}
            name = data.get('pipeline_name', '')

            if not name:
                return jsonify({
                    'success': False,
                    'error': 'pipeline_name required'
                }), 400

            success, message = self.manager.stop_pipeline(name)
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get SatDump plugin status."""
            if not self.manager:
                return jsonify({
                    'ui_running': False,
                    'monitoring': False
                })

            return jsonify({
                'plugin': self.manager.get_status(),
                'active_pipelines': (
                    self.manager.get_active_pipelines()
                )
            })

        @bp.route('/api/products')
        @login_required
        def api_products():
            """Get satellite products list."""
            limit = request.args.get('limit', 20, type=int)
            offset = request.args.get('offset', 0, type=int)
            satellite = request.args.get('satellite', None)

            if not self.manager:
                return jsonify({'products': [], 'total': 0})

            prods = self.manager.get_products(
                limit, offset, satellite
            )
            total = self.manager.get_product_count(satellite)

            # Add URLs
            for p in prods:
                if p.get('thumbnail'):
                    p['thumbnail_url'] = url_for(
                        f'{self.name}.serve_thumbnail',
                        filename=p['thumbnail']
                    )
                if p.get('filename'):
                    p['image_url'] = url_for(
                        f'{self.name}.serve_image',
                        filename=p['filename']
                    )

            return jsonify({'products': prods, 'total': total})

        @bp.route('/api/log_pass', methods=['POST'])
        @login_required
        def api_log_pass():
            """Log a satellite pass to logbook."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data'
                    }), 400

                success = self._log_satellite_pass(
                    satellite=data.get('satellite', ''),
                    frequency=data.get('frequency'),
                    band=data.get('band'),
                    notes=data.get('notes', ''),
                    product_id=data.get('product_id')
                )

                return jsonify({
                    'success': success,
                    'message': (
                        'Pass logged!' if success
                        else 'Logging failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @bp.route('/api/delete_product', methods=['POST'])
        @login_required
        def api_delete_product():
            """Delete a satellite product."""
            data = request.get_json() or {}
            product_id = data.get('product_id')

            if not product_id:
                return jsonify({
                    'success': False,
                    'error': 'product_id required'
                }), 400

            success = (
                self.manager.delete_product(product_id)
                if self.manager else False
            )

            return jsonify({
                'success': success,
                'message': (
                    'Deleted' if success else 'Delete failed'
                )
            })

        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """Get plugin logs."""
            limit = request.args.get('limit', 50, type=int)

            if not self.manager:
                return jsonify({'logs': []})

            return jsonify({
                'logs': self.manager.get_logs(limit)
            })

        @bp.route('/api/install', methods=['POST'])
        @login_required
        def api_install():
            """Trigger SatDump installation."""
            try:
                if os.path.exists(
                    self.installer.INSTALL_MARKER
                ):
                    os.remove(self.installer.INSTALL_MARKER)

                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None
                    self.manager = SatDumpManager(
                        config_dir=self.plugin_data_dir
                    )

                return jsonify({
                    'success': success,
                    'message': (
                        'SatDump installed!' if success
                        else 'Installation failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

    def _log_satellite_pass(self, satellite, frequency=None,
                             band=None, notes='',
                             product_id=None, phase='complete'):
        """
        Log a satellite pass to the central logbook.

        Creates a logbook entry for a satellite reception
        pass using the base plugin log_contact() method.

        Args:
            satellite: Satellite name
            frequency: Frequency in MHz
            band: Band designation
            notes: Additional notes
            product_id: Associated product ID
            phase: 'start', 'complete'

        Returns:
            bool: True if logged successfully
        """
        try:
            if not satellite:
                return False

            # Get GPS grid
            grid = self.manager.config.get('locator', '') \
                if self.manager else ''
            gps = self.get_device('gps')
            if gps and gps.is_connected():
                pos = gps.get_position()
                if pos:
                    grid = pos.get('grid', grid)

            # Determine band from frequency
            contact_band = band
            if not contact_band and frequency:
                contact_band = self._freq_to_band(frequency)

            # Build logbook entry
            # Use satellite name as callsign placeholder
            # Mode is SATELLITE for easy filtering
            contact_data = {
                'callsign': satellite.upper()[:20],
                'mode': 'SATELLITE',
                'band': contact_band or None,
                'frequency': frequency,
                'grid': grid or None,
                'rst_sent': None,
                'rst_rcvd': None,
                'notes': (
                    f"SatDump {phase}: {satellite}. "
                    f"{notes}"
                ).strip()
            }

            success = self.log_contact(contact_data)

            if success:
                print(
                    f"[{self.name}] ✓ Pass logged: {satellite}"
                )

            return success

        except Exception as e:
            print(f"[{self.name}] Log error: {e}")
            return False

    @staticmethod
    def _freq_to_band(freq_mhz):
        """
        Convert frequency to band designation.

        Args:
            freq_mhz: Frequency in MHz

        Returns:
            str: Band designation or None
        """
        if not freq_mhz:
            return None

        # Satellite frequency bands
        bands = [
            (136.0, 138.5, '2m'),       # NOAA APT, METEOR
            (144.0, 148.0, '2m'),       # Amateur sat
            (435.0, 438.0, '70cm'),     # Amateur UHF
            (1690.0, 1710.0, 'L-Band'), # NOAA HRPT, Meteosat
            (1694.0, 1698.0, 'L-Band'), # GOES LRIT
            (2200.0, 2300.0, 'S-Band'), # Various
        ]

        for low, high, band in bands:
            if low <= freq_mhz <= high:
                return band

        return None