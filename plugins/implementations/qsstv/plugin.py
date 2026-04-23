"""
QSSTV Plugin
=============
Main plugin class integrating QSSTV Slow Scan Television
into the Ham Radio Web Application.

QSSTV Features:
    - Receive SSTV images from audio input
    - Transmit SSTV images via audio output
    - Support for 30+ SSTV modes
    - DRM (Digital Radio Mondiale) support
    - Callsign overlay on transmitted images
    - Automatic image saving

Integration Points:
    - Image gallery for received SSTV images
    - Central logbook for SSTV contacts
    - GPS for grid locator
    - Hamlib radio for frequency display
    - File monitoring for automatic image detection

Source: https://github.com/ON4QZ/QSSTV
Documentation: https://users.telenet.be/on4qz/qsstv/

Installation:
    Copy qsstv/ directory to plugins/implementations/
    First run installs QSSTV and Python dependencies.
"""

import os
import base64
from datetime import datetime

from flask import (
    Blueprint, render_template, jsonify, request,
    redirect, url_for, flash, send_from_directory,
    make_response
)
from flask_login import login_required, current_user

from plugins.base import BasePlugin
from plugins.implementations.qsstv.installer import QSStvInstaller
from plugins.implementations.qsstv.qsstv_manager import QSStvManager
from plugins.implementations.qsstv.forms import (
    QSStvSettingsForm,
    QSStvTransmitForm,
    QSStvLogImageForm
)


class QSStvPlugin(BasePlugin):
    """
    QSSTV Slow Scan Television Plugin.

    Provides SSTV image reception, transmission, and
    gallery management with logbook integration.
    """

    # Plugin metadata
    name = "QSSTV"
    description = "Slow Scan Television (SSTV) via QSSTV"
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = "https://github.com/ON4QZ/QSSTV"

    def __init__(self, app=None, devices=None):
        """
        Initialize QSSTV plugin.

        Args:
            app: Flask application instance
            devices: Available device interfaces
        """
        super().__init__(app, devices)

        # Plugin data directory for persistent storage
        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins',
            'qsstv'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # Core components
        self.installer = QSStvInstaller()
        self.manager = None

        # Installation state
        self.install_complete = False
        self.install_error = None

    def initialize(self):
        """
        Initialize plugin on application load.

        Handles first-run installation, initializes
        manager, starts image monitoring, and
        integrates GPS data.

        Returns:
            bool: True if initialization successful
        """
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            # Run installation check
            install_success = self.installer.run()

            if not install_success:
                self.install_error = (
                    "QSSTV installation failed. "
                    "Install manually: "
                    "https://github.com/ON4QZ/QSSTV"
                )
                print(
                    f"[{self.name}] WARNING: {self.install_error}"
                )

            self.install_complete = install_success

            # Initialize manager
            self.manager = QSStvManager(
                config_dir=self.plugin_data_dir,
                binary_path=self.installer.qsstv_binary_path
            )

            # Update GPS locator
            self._update_gps_locator()

            # Set callsign from current user if not configured
            if not self.manager.config.get('callsign'):
                callsign = getattr(
                    current_user, 'callsign', ''
                )
                if callsign:
                    self.manager.save_config(
                        {'callsign': callsign}
                    )

            # Register new image callback for logbook
            self.manager.register_image_callback(
                self._on_new_sstv_image
            )

            # Auto-start image monitoring
            if self.manager.config.get('auto_monitor', True):
                success, msg = self.manager.start_monitoring()
                if success:
                    print(f"[{self.name}] ✓ {msg}")
                else:
                    print(f"[{self.name}] Monitor: {msg}")

            # Auto-launch QSSTV if configured
            if (self.manager.config.get('auto_start') and
                    self.install_complete):
                success, msg = self.manager.start_qsstv()
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

        Stops monitoring and QSSTV process if running.
        """
        print(f"[{self.name}] Shutting down...")

        if self.manager:
            self.manager.stop_monitoring()

            if self.manager._status.get('process_running'):
                self.manager.stop_qsstv()

        print(f"[{self.name}] ✓ Shutdown complete")

    def _update_gps_locator(self):
        """
        Update grid locator from GPS device.
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

    def _on_new_sstv_image(self, image_data):
        """
        Callback for new SSTV received images.

        Called by image monitor when QSSTV saves
        a new received image. Optionally creates a
        logbook entry if auto-logging is enabled.

        Args:
            image_data: Image metadata dictionary
        """
        if not self.manager:
            return

        if self.manager.config.get('log_received_images', True):
            # Only auto-log if callsign is known
            callsign = image_data.get('callsign', '').strip()

            if callsign:
                # Get current frequency from radio
                freq_mhz = None
                radio = self.get_device('radio')
                if radio and radio.is_connected():
                    freq_mhz = radio.get_frequency()

                if freq_mhz is None:
                    # Use default SSTV frequency
                    default_freq = self.manager.config.get(
                        'default_frequency', 14230000
                    )
                    freq_mhz = default_freq / 1_000_000

                self._log_sstv_contact(
                    callsign=callsign,
                    mode=image_data.get('mode', 'SSTV'),
                    frequency=freq_mhz,
                    notes=(
                        f"SSTV image received: "
                        f"{image_data.get('filename', '')}"
                    )
                )

    def get_blueprint(self):
        """
        Create Flask Blueprint for QSSTV UI.

        Returns:
            Blueprint: Configured blueprint with all routes
        """
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/qsstv',
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
        # Serve gallery images
        # ============================================================
        @bp.route('/gallery/image/<filename>')
        @login_required
        def serve_image(filename):
            """Serve gallery image files."""
            gallery_dir = os.path.join(
                self.plugin_data_dir, 'gallery'
            )
            return send_from_directory(gallery_dir, filename)

        @bp.route('/gallery/thumbnail/<filename>')
        @login_required
        def serve_thumbnail(filename):
            """Serve thumbnail images."""
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
            """QSSTV main plugin dashboard."""
            status = (
                self.manager.get_status()
                if self.manager else {}
            )
            logs = (
                self.manager.get_logs(30)
                if self.manager else []
            )

            # Get recent images for dashboard preview
            recent_images = (
                self.manager.get_images(limit=6)
                if self.manager else []
            )

            # Get radio frequency for display
            freq_mhz = None
            radio = self.get_device('radio')
            if radio and radio.is_connected():
                freq_mhz = radio.get_frequency()

            return render_template(
                'qsstv/index.html',
                plugin=self,
                status=status,
                logs=logs,
                recent_images=recent_images,
                freq_mhz=freq_mhz,
                install_complete=self.install_complete,
                install_error=self.install_error,
                config=(
                    self.manager.config if self.manager else {}
                )
            )

        # ============================================================
        # Gallery Page
        # ============================================================
        @bp.route('/gallery')
        @login_required
        def gallery():
            """SSTV image gallery page."""
            page = request.args.get('page', 1, type=int)
            per_page = 12
            offset = (page - 1) * per_page

            images = (
                self.manager.get_images(
                    limit=per_page,
                    offset=offset
                ) if self.manager else []
            )

            total = (
                self.manager.get_image_count()
                if self.manager else 0
            )

            total_pages = (total + per_page - 1) // per_page

            log_form = QSStvLogImageForm()

            return render_template(
                'qsstv/gallery.html',
                plugin=self,
                images=images,
                page=page,
                total_pages=total_pages,
                total=total,
                log_form=log_form,
                status=(
                    self.manager.get_status()
                    if self.manager else {}
                )
            )

        # ============================================================
        # Transmit Page
        # ============================================================
        @bp.route('/transmit', methods=['GET', 'POST'])
        @login_required
        def transmit():
            """SSTV image transmission page."""
            form = QSStvTransmitForm()

            if form.validate_on_submit():
                if not self.manager:
                    flash('Manager not available', 'danger')
                    return redirect(
                        url_for(f'{self.name}.transmit')
                    )

                # Save uploaded image
                image_file = form.image.data
                if image_file:
                    import werkzeug
                    filename = werkzeug.utils.secure_filename(
                        image_file.filename
                    )
                    upload_path = os.path.join(
                        self.plugin_data_dir,
                        'uploads',
                        filename
                    )
                    os.makedirs(
                        os.path.dirname(upload_path),
                        exist_ok=True
                    )
                    image_file.save(upload_path)

                    # Prepare for transmission
                    success, message, dest = (
                        self.manager.prepare_tx_image(
                            upload_path,
                            form.mode.data
                        )
                    )

                    if success:
                        flash(
                            f'Image prepared for TX: {message}. '
                            f'Load it in QSSTV to transmit.',
                            'success'
                        )
                    else:
                        flash(
                            f'TX preparation failed: {message}',
                            'danger'
                        )

            modes = (
                self.manager.SSTV_MODES
                if self.manager else {}
            )

            return render_template(
                'qsstv/transmit.html',
                plugin=self,
                form=form,
                modes=modes,
                status=(
                    self.manager.get_status()
                    if self.manager else {}
                ),
                config=(
                    self.manager.config if self.manager else {}
                )
            )

        # ============================================================
        # Settings Page
        # ============================================================
        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """QSSTV plugin settings page."""
            form = QSStvSettingsForm()

            if request.method == 'GET' and self.manager:
                cfg = self.manager.config
                form.display.data = cfg.get('display', ':0')
                form.default_mode.data = cfg.get(
                    'default_mode', 'Martin M1'
                )
                form.default_frequency.data = cfg.get(
                    'default_frequency', 14230000
                )
                form.callsign.data = cfg.get(
                    'callsign', current_user.callsign
                )
                form.locator.data = cfg.get('locator', '')
                form.auto_start.data = cfg.get(
                    'auto_start', False
                )
                form.auto_monitor.data = cfg.get(
                    'auto_monitor', True
                )
                form.log_received_images.data = cfg.get(
                    'log_received_images', True
                )
                form.max_gallery_images.data = cfg.get(
                    'max_gallery_images', 100
                )

            if form.validate_on_submit():
                config_data = {
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
                    'auto_monitor': form.auto_monitor.data,
                    'log_received_images': (
                        form.log_received_images.data
                    ),
                    'max_gallery_images': (
                        form.max_gallery_images.data
                    )
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
                'qsstv/settings.html',
                plugin=self,
                form=form,
                install_complete=self.install_complete,
                install_error=self.install_error
            )

        # ============================================================
        # API: Start QSSTV
        # ============================================================
        @bp.route('/api/start', methods=['POST'])
        @login_required
        def api_start():
            """Launch QSSTV process."""
            if not self.manager or not self.install_complete:
                return jsonify({
                    'success': False,
                    'error': 'Not ready'
                }), 503

            success, message = self.manager.start_qsstv()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        # ============================================================
        # API: Stop QSSTV
        # ============================================================
        @bp.route('/api/stop', methods=['POST'])
        @login_required
        def api_stop():
            """Stop QSSTV process."""
            if not self.manager:
                return jsonify({
                    'success': False,
                    'error': 'Not initialized'
                }), 503

            success, message = self.manager.stop_qsstv()
            return jsonify({
                'success': success,
                'message': message
            })

        # ============================================================
        # API: Start/Stop Monitoring
        # ============================================================
        @bp.route('/api/start_monitor', methods=['POST'])
        @login_required
        def api_start_monitor():
            """Start image file monitoring."""
            if not self.manager:
                return jsonify({
                    'success': False
                }), 503

            success, message = self.manager.start_monitoring()
            return jsonify({
                'success': success,
                'message': message,
                'status': self.manager.get_status()
            })

        @bp.route('/api/stop_monitor', methods=['POST'])
        @login_required
        def api_stop_monitor():
            """Stop image file monitoring."""
            if not self.manager:
                return jsonify({
                    'success': False
                }), 503

            success, message = self.manager.stop_monitoring()
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
            """Get QSSTV plugin status."""
            if not self.manager:
                return jsonify({
                    'process_running': False
                })

            return jsonify(self.manager.get_status())

        # ============================================================
        # API: Get Images
        # ============================================================
        @bp.route('/api/images')
        @login_required
        def api_images():
            """Get gallery images list."""
            limit = request.args.get('limit', 20, type=int)
            offset = request.args.get('offset', 0, type=int)

            if not self.manager:
                return jsonify({'images': [], 'total': 0})

            images = self.manager.get_images(limit, offset)
            total = self.manager.get_image_count()

            # Add URL paths for serving
            for img in images:
                if img.get('thumbnail'):
                    img['thumbnail_url'] = url_for(
                        f'{self.name}.serve_thumbnail',
                        filename=img['thumbnail']
                    )
                if img.get('filename'):
                    img['image_url'] = url_for(
                        f'{self.name}.serve_image',
                        filename=img['filename']
                    )

            return jsonify({
                'images': images,
                'total': total
            })

        # ============================================================
        # API: Log Image Contact
        # ============================================================
        @bp.route('/api/log_contact', methods=['POST'])
        @login_required
        def api_log_contact():
            """Log an SSTV image as a contact."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data'
                    }), 400

                callsign = data.get('callsign', '').strip()
                if not callsign:
                    return jsonify({
                        'success': False,
                        'error': 'Callsign required'
                    }), 400

                # Update image metadata with callsign
                image_id = data.get('image_id')
                if image_id and self.manager:
                    self.manager.update_image(
                        image_id,
                        callsign=callsign,
                        notes=data.get('notes', '')
                    )

                success = self._log_sstv_contact(
                    callsign=callsign,
                    mode=data.get('mode', 'SSTV'),
                    frequency=data.get('frequency'),
                    band=data.get('band'),
                    rst_rcvd=data.get('rst_rcvd', '59'),
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
        # API: Delete Image
        # ============================================================
        @bp.route('/api/delete_image', methods=['POST'])
        @login_required
        def api_delete_image():
            """Delete an image from gallery."""
            try:
                data = request.get_json()
                image_id = data.get('image_id') if data else None

                if not image_id:
                    return jsonify({
                        'success': False,
                        'error': 'image_id required'
                    }), 400

                success = (
                    self.manager.delete_image(image_id)
                    if self.manager else False
                )

                return jsonify({
                    'success': success,
                    'message': (
                        'Image deleted' if success
                        else 'Delete failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        # ============================================================
        # API: Logs
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
            """Trigger QSSTV installation."""
            try:
                if os.path.exists(self.installer.INSTALL_MARKER):
                    os.remove(self.installer.INSTALL_MARKER)

                success = self.installer.run()

                if success:
                    self.install_complete = True
                    self.install_error = None
                    self.manager = QSStvManager(
                        config_dir=self.plugin_data_dir
                    )

                return jsonify({
                    'success': success,
                    'message': (
                        'QSSTV installed!' if success
                        else 'Installation failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

    def _log_sstv_contact(self, callsign, mode='SSTV',
                           frequency=None, band=None,
                           rst_rcvd='59', notes=''):
        """
        Log an SSTV contact to the central logbook.

        Uses base plugin log_contact() for standardized
        logbook entry creation.

        Args:
            callsign: Contact callsign
            mode: SSTV mode string
            frequency: Frequency in MHz
            band: Band designation
            rst_rcvd: Signal report received
            notes: Additional notes

        Returns:
            bool: True if logged successfully
        """
        try:
            if not callsign or not callsign.strip():
                return False

            # Get GPS grid if available
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

            # Map SSTV mode to standard format
            sstv_mode = mode.upper()
            if len(sstv_mode) > 10:
                # Shorten long mode names for logbook
                sstv_mode = 'SSTV'

            contact_data = {
                'callsign': callsign.upper().strip(),
                'mode': sstv_mode,
                'band': contact_band or None,
                'frequency': frequency,
                'grid': grid or None,
                'rst_sent': '59',
                'rst_rcvd': rst_rcvd or '59',
                'notes': (
                    f"QSSTV SSTV: {notes}" if notes
                    else "Logged via QSSTV"
                )
            }

            success = self.log_contact(contact_data)

            if success:
                print(
                    f"[{self.name}] ✓ Logged: "
                    f"{callsign} SSTV"
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

        bands = [
            (1.8, 2.0, '160m'),
            (3.5, 4.0, '80m'),
            (7.0, 7.3, '40m'),
            (14.0, 14.35, '20m'),
            (21.0, 21.45, '15m'),
            (28.0, 29.7, '10m'),
            (50.0, 54.0, '6m'),
            (144.0, 148.0, '2m'),
        ]

        for low, high, band in bands:
            if low <= freq_mhz <= high:
                return band

        return None