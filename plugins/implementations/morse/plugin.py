"""
Morse Code Plugin
==================
Main plugin class for CW (morse code) decode, display,
and transmission via on-screen key.

Features:
    - Real-time CW decode from RTL-SDR or radio audio
    - On-screen key: free-run mode (button held)
    - Text mode: compose then send as morse
    - Browser-based sidetone via Web Audio API
    - Adjustable WPM, Farnsworth, tone frequency
    - Logbook integration
    - Morse code reference chart

The sidetone is generated entirely in the browser using
the Web Audio API — no server-side audio required for TX.
The SDR receive runs server-side in a background thread.
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
from plugins.implementations.morse.installer import (
    MorseInstaller
)
from plugins.implementations.morse.morse_engine import (
    MorseEngine
)
from plugins.implementations.morse.sdr_receiver import (
    SDRMorseReceiver
)
from plugins.implementations.morse.forms import (
    MorseSettingsForm,
    MorseLogForm
)


class MorsePlugin(BasePlugin):
    """
    Morse Code Plugin.

    Provides CW decode from SDR, on-screen morse key,
    and logbook integration.
    """

    name = "Morse"
    description = "CW decoder, on-screen key, and morse reference"
    version = "1.0.0"
    author = "HRT - Ham Rad Team"
    url = "https://en.wikipedia.org/wiki/Morse_code"

    def __init__(self, app=None, devices=None):
        super().__init__(app, devices)

        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins', 'morse'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        self.installer = MorseInstaller()
        self.engine = None
        self.receiver = None
        self.config = self._load_config()

        self.install_complete = False
        self.install_error = None

    def _load_config(self):
        """Load plugin configuration."""
        config_file = os.path.join(
            self.plugin_data_dir, 'morse_config.json'
        )
        defaults = {
            'wpm': 20,
            'farnsworth_wpm': 0,
            'tone_hz': 700,
            'center_frequency_mhz': 7.030,
            'sdr_gain': 30,
            'sdr_device_index': 0,
            'tone_detection_threshold': 0.01,
            'radio_audio_device': None,
            'default_source': 'sdr',
            'auto_log': True,
            'callsign': '',
        }
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[Morse][PLUGIN] Config load error: {e}")
        return defaults

    def _save_config(self, config_data):
        """Save plugin configuration."""
        config_file = os.path.join(
            self.plugin_data_dir, 'morse_config.json'
        )
        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[Morse] Config save error: {e}")
            return False

    def initialize(self):
        """Initialize the Morse plugin."""
        print(f"\n[{self.name}][PLUGIN] Initializing plugin...")

        try:
            install_success = self.installer.run()
            self.install_complete = install_success

            if not install_success:
                self.install_error = (
                    "Morse plugin dependencies not "
                    "fully installed."
                )

            # Create Morse engine
            farnsworth = self.config.get(
                'farnsworth_wpm', 0
            )
            self.engine = MorseEngine(
                wpm=self.config.get('wpm', 20),
                tone_hz=self.config.get('tone_hz', 700),
                farnsworth_wpm=(
                    farnsworth if farnsworth > 0
                    else None
                )
            )

            # Update GPS grid if available
            try:
                gps = self.get_device('gps')
                if gps and gps.is_connected():
                    pos = gps.get_position()
                    if pos and not self.config.get(
                        'callsign'
                    ):
                        pass  # GPS used for grid, not call
            except Exception:
                pass

            # Create SDR receiver
            self.receiver = SDRMorseReceiver(
                self.engine,
                self.config
            )

            # Auto-start receiver in SDR mode
            if self.config.get('default_source') == 'sdr':
                success, msg = self.receiver.start()
                if success:
                    print(f"[{self.name}][PLUGIN] ✓ {msg}")
                else:
                    print(f"[{self.name}][PLUGIN] Receiver: {msg}")

            print(f"[{self.name}][PLUGIN] ✓ Plugin initialized")
            return True

        except Exception as e:
            self.install_error = str(e)
            print(f"[{self.name}][PLUGIN] ERROR: {e}")
            traceback.print_exc()
            return False

    def shutdown(self):
        """Clean shutdown."""
        print(f"[{self.name}][PLUGIN] Shutting down...")
        if self.receiver:
            self.receiver.stop()
        print(f"[{self.name}][PLUGIN] ✓ Shutdown complete")

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
            url_prefix='/plugin/morse',
            template_folder=template_dir
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """Register all plugin routes."""

        # ======================================================
        # Main page
        # ======================================================
        @bp.route('/')
        @login_required
        def index():
            """Main Morse plugin page."""
            try:
                timing = (
                    self.engine.get_timing_summary()
                    if self.engine else {}
                )
                receiver_status = (
                    self.receiver.get_status()
                    if self.receiver else {}
                )
                decoded_text = (
                    self.engine.get_decoded_text()
                    if self.engine else ''
                )
                log_form = MorseLogForm()

                # Current frequency for display
                freq_mhz = self.config.get(
                    'center_frequency_mhz', 7.030
                )

                # Radio frequency if available
                radio_freq = None
                radio = self.get_device('radio')
                if radio and radio.is_connected():
                    try:
                        rf = radio.get_frequency()
                        if rf:
                            radio_freq = rf
                    except Exception:
                        pass

                return render_template(
                    'morse/index.html',
                    plugin=self,
                    timing=timing,
                    receiver_status=receiver_status,
                    decoded_text=decoded_text,
                    freq_mhz=freq_mhz,
                    radio_freq=radio_freq,
                    log_form=log_form,
                    config=self.config,
                    install_complete=self.install_complete,
                    install_error=self.install_error,
                )

            except Exception as e:
                print(f"[{self.name}][PLUGIN] Index error: {e}")
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
            """Settings page."""
            try:
                form = MorseSettingsForm()

                if request.method == 'GET':
                    form.wpm.data = self.config.get(
                        'wpm', 20
                    )
                    form.farnsworth_wpm.data = (
                        self.config.get('farnsworth_wpm', 0)
                    )
                    form.tone_hz.data = self.config.get(
                        'tone_hz', 700
                    )
                    form.center_frequency_mhz.data = (
                        self.config.get(
                            'center_frequency_mhz', 7.030
                        )
                    )
                    form.sdr_gain.data = self.config.get(
                        'sdr_gain', 30
                    )
                    form.sdr_device_index.data = (
                        self.config.get(
                            'sdr_device_index', 0
                        )
                    )
                    form.tone_detection_threshold.data = (
                        self.config.get(
                            'tone_detection_threshold', 0.01
                        )
                    )
                    form.radio_audio_device.data = (
                        self.config.get(
                            'radio_audio_device', ''
                        ) or ''
                    )
                    form.default_source.data = (
                        self.config.get(
                            'default_source', 'sdr'
                        )
                    )
                    form.auto_log.data = self.config.get(
                        'auto_log', True
                    )
                    form.callsign.data = self.config.get(
                        'callsign',
                        getattr(current_user, 'callsign', '')
                    )

                if form.validate_on_submit():
                    new_config = {
                        'wpm': form.wpm.data,
                        'farnsworth_wpm': (
                            form.farnsworth_wpm.data or 0
                        ),
                        'tone_hz': form.tone_hz.data,
                        'center_frequency_mhz': (
                            form.center_frequency_mhz.data
                        ),
                        'sdr_gain': form.sdr_gain.data,
                        'sdr_device_index': (
                            form.sdr_device_index.data
                        ),
                        'tone_detection_threshold': (
                            form.tone_detection_threshold.data
                        ),
                        'radio_audio_device': (
                            form.radio_audio_device.data
                            or None
                        ),
                        'default_source': (
                            form.default_source.data
                        ),
                        'auto_log': form.auto_log.data,
                        'callsign': (
                            form.callsign.data.upper()
                            if form.callsign.data else ''
                        ),
                    }

                    self._save_config(new_config)

                    # Apply new settings to engine
                    if self.engine:
                        self.engine.set_wpm(
                            new_config['wpm']
                        )
                        self.engine.set_tone(
                            new_config['tone_hz']
                        )
                        fw = new_config['farnsworth_wpm']
                        self.engine.farnsworth_wpm = (
                            fw if fw > 0 else None
                        )

                    # Update receiver frequency
                    if self.receiver:
                        freq_hz = int(
                            new_config[
                                'center_frequency_mhz'
                            ] * 1e6
                        )
                        self.receiver.set_frequency(freq_hz)

                    flash('Settings saved!', 'success')
                    return redirect(
                        url_for(f'{self.name}.settings')
                    )

                return render_template(
                    'morse/settings.html',
                    plugin=self,
                    form=form,
                    config=self.config,
                    timing=(
                        self.engine.get_timing_summary()
                        if self.engine else {}
                    ),
                    receiver_status=(
                        self.receiver.get_status()
                        if self.receiver else {}
                    ),
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
        # API: Get decoded text
        # ======================================================
        @bp.route('/api/decoded')
        @login_required
        def api_decoded():
            """Get decoded CW text."""
            try:
                if not self.engine:
                    return jsonify({
                        'text': '',
                        'buffer': []
                    })
                return jsonify({
                    'text': self.engine.get_decoded_text(),
                    'buffer': (
                        self.engine.get_decode_buffer(20)
                    ),
                    'tone_detected': (
                        self.receiver.get_status().get(
                            'tone_detected', False
                        ) if self.receiver else False
                    ),
                    'signal_level': (
                        self.receiver.get_signal_level()
                        if self.receiver else 0.0
                    ),
                })
            except Exception as e:
                return jsonify({'text': '', 'error': str(e)})

        # ======================================================
        # API: Clear decoded buffer
        # ======================================================
        @bp.route('/api/clear_decode', methods=['POST'])
        @login_required
        def api_clear_decode():
            """Clear the decoded text buffer."""
            try:
                if self.engine:
                    self.engine.clear_decode_buffer()
                return jsonify({
                    'success': True,
                    'message': 'Decode buffer cleared'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        # ======================================================
        # API: Get timing for text-to-morse TX
        # ======================================================
        @bp.route('/api/encode', methods=['POST'])
        @login_required
        def api_encode():
            """
            Encode text to morse timing events.

            The browser uses these events to generate
            audio tones via the Web Audio API.
            """
            try:
                data = request.get_json() or {}
                text = data.get('text', '').strip()

                if not text:
                    return jsonify({
                        'success': False,
                        'error': 'Text required'
                    }), 400

                if not self.engine:
                    return jsonify({
                        'success': False,
                        'error': 'Engine not ready'
                    }), 503

                morse_str = self.engine.text_to_morse(text)
                timing = self.engine.text_to_timing(text)

                return jsonify({
                    'success': True,
                    'morse': morse_str,
                    'timing': timing,
                    'tone_hz': self.engine.tone_hz,
                    'total_events': len(timing),
                })

            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        # ======================================================
        # API: Receiver control
        # ======================================================
        @bp.route('/api/receiver/start', methods=['POST'])
        @login_required
        def api_receiver_start():
            """Start the SDR/audio receiver."""
            try:
                if not self.receiver:
                    return jsonify({
                        'success': False,
                        'error': 'Receiver not initialized'
                    }), 503

                success, message = self.receiver.start()
                return jsonify({
                    'success': success,
                    'message': message,
                    'status': self.receiver.get_status()
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/receiver/stop', methods=['POST'])
        @login_required
        def api_receiver_stop():
            """Stop the receiver."""
            try:
                if not self.receiver:
                    return jsonify({'success': False}), 503
                self.receiver.stop()
                return jsonify({
                    'success': True,
                    'message': 'Receiver stopped'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/receiver/source', methods=['POST'])
        @login_required
        def api_receiver_source():
            """Switch between SDR and radio source."""
            try:
                data = request.get_json() or {}
                source = data.get('source', 'sdr')

                if source not in ('sdr', 'radio'):
                    return jsonify({
                        'success': False,
                        'error': 'Invalid source'
                    }), 400

                if self.receiver:
                    self.receiver.set_source(source)
                    self._save_config(
                        {'default_source': source}
                    )

                return jsonify({
                    'success': True,
                    'source': source,
                    'message': (
                        f'Switched to {source}'
                    ),
                    'status': (
                        self.receiver.get_status()
                        if self.receiver else {}
                    )
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route(
            '/api/receiver/frequency', methods=['POST']
        )
        @login_required
        def api_set_frequency():
            """Set SDR center frequency."""
            try:
                data = request.get_json() or {}
                freq_mhz = data.get('frequency_mhz')

                if not freq_mhz:
                    return jsonify({
                        'success': False,
                        'error': 'frequency_mhz required'
                    }), 400

                freq_hz = int(float(freq_mhz) * 1e6)

                if self.receiver:
                    self.receiver.set_frequency(freq_hz)

                self._save_config(
                    {'center_frequency_mhz': float(freq_mhz)}
                )

                return jsonify({
                    'success': True,
                    'frequency_mhz': float(freq_mhz),
                    'frequency_hz': freq_hz,
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/receiver/status')
        @login_required
        def api_receiver_status():
            """Get receiver status."""
            try:
                return jsonify({
                    'receiver': (
                        self.receiver.get_status()
                        if self.receiver else {}
                    ),
                    'timing': (
                        self.engine.get_timing_summary()
                        if self.engine else {}
                    ),
                })
            except Exception as e:
                return jsonify({'error': str(e)})

        # ======================================================
        # API: Log contact
        # ======================================================
        @bp.route('/api/log_contact', methods=['POST'])
        @login_required
        def api_log_contact():
            """Log a CW contact to the central logbook."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No data'
                    }), 400

                callsign = data.get(
                    'callsign', ''
                ).strip().upper()
                if not callsign:
                    return jsonify({
                        'success': False,
                        'error': 'Callsign required'
                    }), 400

                success = self._log_cw_contact(
                    callsign=callsign,
                    frequency_mhz=data.get('frequency'),
                    rst_sent=data.get('rst_sent', '599'),
                    rst_rcvd=data.get('rst_rcvd', '599'),
                    notes=data.get('notes', '')
                )

                return jsonify({
                    'success': success,
                    'message': (
                        f'{callsign} logged!'
                        if success else 'Logging failed'
                    )
                })

            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

    def _log_cw_contact(self, callsign, frequency_mhz=None,
                         rst_sent='599', rst_rcvd='599',
                         notes=''):
        """
        Log a CW contact to the central logbook.

        Args:
            callsign: Contact callsign
            frequency_mhz: Frequency in MHz
            rst_sent: RST sent
            rst_rcvd: RST received
            notes: Additional notes

        Returns:
            bool: True if logged
        """
        try:
            if not callsign:
                return False

            # Determine band from frequency
            band = None
            if frequency_mhz:
                band = self._freq_to_band(frequency_mhz)

            contact_data = {
                'callsign': callsign,
                'mode': 'CW',
                'band': band,
                'frequency': frequency_mhz,
                'grid': None,
                'rst_sent': rst_sent or '599',
                'rst_rcvd': rst_rcvd or '599',
                'notes': (
                    f"CW: {notes}" if notes
                    else "Logged via Morse plugin"
                )
            }

            success = self.log_contact(contact_data)
            if success:
                print(
                    f"[{self.name}][PLUGIN] ✓ Logged: "
                    f"{callsign} CW"
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
        ]
        for low, high, band in bands:
            if low <= float(freq_mhz) <= high:
                return band
        return None
