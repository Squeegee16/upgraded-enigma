"""
P25 Survey Plugin Main
=======================
Flask plugin class for P25 survey and monitoring.
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
from plugins.implementations.p25survey.installer import (
    P25SurveyInstaller
)
from plugins.implementations.p25survey.p25_engine import (
    P25SurveyEngine
)
from plugins.implementations.p25survey.p25_constants import (
    P25_PHASES, TRUNKING_TYPES, VOCODERS,
    P25_BANDS, COMMON_P25_FREQS, NAC_SPECIAL,
    SCAN_STATES, ENCRYPTION_ALGOS
)
from plugins.implementations.p25survey.forms import (
    P25SettingsForm,
    P25LogForm
)


class P25SurveyPlugin(BasePlugin):
    """
    P25 Survey Plugin.

    Monitors and decodes P25 Phase 1/2 digital radio
    systems with survey scanning and logbook integration.

    Based on: https://github.com/blantonl/p25-survey
    """

    name = "P25Survey"
    description = (
        "P25 Phase 1/2 scanner, survey tool, "
        "and talkgroup monitor"
    )
    version = "1.0.0"
    author = "HRT - Ham Rad Team"
    url = "https://github.com/blantonl/p25-survey"

    def __init__(self, app=None, devices=None):
        """Initialise P25 Survey plugin."""
        super().__init__(app, devices)

        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins', 'p25survey'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        self.installer = P25SurveyInstaller()
        self.engine = None
        self.config = self._load_config()

        self.install_complete = False
        self.install_error = None
        self._channel = {
            'frequency': None,
            'talkgroup': None,
            'nac': 0,
            'phase': 1,
            'mode': 'conventional',
        }
        self._active_call_start = None

    def _load_config(self):
        """
        Load plugin configuration.

        Default talkgroup: 302 (Canada Wide) on TS1.
        """
        config_file = os.path.join(
            self.plugin_data_dir, 'p25_config.json'
        )

        defaults = {
            'center_frequency_mhz': 851.0125,
            'source': 'sdr',
            'sdr_gain': 40,
            'sdr_device_index': 0,
            'op25_port': 8080,
            'nac': '0',              # 0 = receive all
            'phase': 1,
            'scan_mode': 'conventional',
            'survey_frequencies': [],
            'dwell_time_ms': 1000,
            'radio_audio_device': None,
            'audio_output_device': None,
            'callsign': '',
            'auto_log_calls': True,
            'log_encrypted': True,
            'log_min_duration_s': 2,
            # Canada Wide defaults
            'talkgroup': 302,        # Canada Wide
            'timeslot': 1,           # TS1
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(
                    f"[P25Survey] Config load error: {e}"
                )

        return defaults

    def _save_config(self, config_data):
        """Save plugin configuration."""
        config_file = os.path.join(
            self.plugin_data_dir, 'p25_config.json'
        )
        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[P25][PLUGIN] Save error: {e}")
            return False

    def initialize(self):
        """Initialize the P25 Survey plugin."""
        print(f"\n[{self.name}][PLUGIN] Initializing...")

        try:
            install_success = self.installer.run()
            self.install_complete = install_success

            # Create engine
            self.engine = P25SurveyEngine(self.config)

            # Set callsign
            if not self.config.get('callsign'):
                try:
                    cs = getattr(
                        current_user, 'callsign', ''
                    )
                    if cs:
                        self._save_config({'callsign': cs})
                except RuntimeError:
                    pass

            # Auto-start receive
            success, msg = self.engine.start_receive()
            if success:
                print(f"[{self.name}][PLUGIN] ✓ {msg}")
            else:
                print(f"[{self.name}][PLUGIN] RX: {msg}")

            print(f"[{self.name}][PLUGIN] ✓ Initialized")
            return True

        except Exception as e:
            self.install_error = str(e)
            print(f"[{self.name}][PLUGIN] ERROR: {e}")
            traceback.print_exc()
            return False

    def shutdown(self):
        """Clean shutdown."""
        print(f"[{self.name}] Shutting down...")
        if self.engine:
            self.engine.stop_receive()
        print(f"[{self.name}][PLUGIN] ✓ Shutdown")

    def get_blueprint(self):
        """Create Flask Blueprint."""
        plugin_dir = os.path.dirname(
            os.path.abspath(__file__)
        )
        bp = Blueprint(
            self.name,
            __name__,
            url_prefix='/plugin/p25survey',
            template_folder=os.path.join(
                plugin_dir, 'templates'
            )
        )
        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """Register all plugin routes."""

        @bp.route('/')
        @login_required
        def index():
            """P25 Survey main page."""
            try:
                status = (
                    self.engine.get_status()
                    if self.engine else {}
                )
                frames = (
                    self.engine.get_frames(limit=40)
                    if self.engine else []
                )
                systems = (
                    self.engine.get_systems()
                    if self.engine else []
                )
                logs = (
                    self.engine.get_logs(30)
                    if self.engine else []
                )
                log_form = P25LogForm()

                radio_info = {}
                radio = self.get_device('radio')
                if radio and radio.is_connected():
                    try:
                        radio_info = radio.get_info()
                    except Exception:
                        pass

                # Pre-compute signal bar widths
                rssi_raw = status.get('rssi') or -120
                try:
                    rssi_raw = float(rssi_raw)
                except (TypeError, ValueError):
                    rssi_raw = -120.0

                ber_raw = status.get('ber_avg') or 0.0
                try:
                    ber_raw = float(ber_raw)
                except (TypeError, ValueError):
                    ber_raw = 0.0

                rssi_pct = max(
                    0, min(100,
                        round((rssi_raw + 120) / 60 * 100, 1)
                    )
                )
                ber_pct = max(
                    0, min(100,
                        round(100 - ber_raw * 10, 1)
                    )
                )

                return render_template(
                    'p25survey/index.html',
                    plugin=self,
                    status=status,
                    frames=frames,
                    systems=systems,
                    logs=logs,
                    log_form=log_form,
                    radio_info=radio_info,
                    config=self.config,
                    nac_special=NAC_SPECIAL,
                    p25_phases=P25_PHASES,
                    trunking_types=TRUNKING_TYPES,
                    encryption_algos=ENCRYPTION_ALGOS,
                    scan_states=SCAN_STATES,
                    install_complete=self.install_complete,
                    install_error=self.install_error,
                    # Pre-computed bar widths
                    rssi_pct=rssi_pct,
                    ber_pct=ber_pct,
                )

            except Exception as e:
                print(
                    f"[{self.name}][PLUGIN] Index error: {e}"
                )
                traceback.print_exc()
                return render_template(
                    'errors/500.html', error=str(e)
                ), 500

        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """Settings page."""
            try:
                form = P25SettingsForm()

                if request.method == 'GET':
                    form.center_frequency_mhz.data = (
                        self.config.get(
                            'center_frequency_mhz',
                            851.0125
                        )
                    )
                    form.source.data = self.config.get(
                        'source', 'sdr'
                    )
                    form.sdr_gain.data = self.config.get(
                        'sdr_gain', 40
                    )
                    form.sdr_device_index.data = (
                        self.config.get(
                            'sdr_device_index', 0
                        )
                    )
                    form.op25_port.data = self.config.get(
                        'op25_port', 8080
                    )
                    form.nac.data = self.config.get(
                        'nac', '0'
                    )
                    form.phase.data = str(
                        self.config.get('phase', 1)
                    )
                    form.scan_mode.data = self.config.get(
                        'scan_mode', 'conventional'
                    )
                    freqs = self.config.get(
                        'survey_frequencies', []
                    )
                    form.survey_frequencies.data = (
                        '\n'.join(str(f) for f in freqs)
                    )
                    form.dwell_time_ms.data = (
                        self.config.get(
                            'dwell_time_ms', 1000
                        )
                    )
                    form.radio_audio_device.data = (
                        self.config.get(
                            'radio_audio_device', ''
                        ) or ''
                    )
                    form.audio_output_device.data = (
                        self.config.get(
                            'audio_output_device', ''
                        ) or ''
                    )
                    form.callsign.data = self.config.get(
                        'callsign',
                        getattr(
                            current_user, 'callsign', ''
                        )
                    )
                    form.auto_log_calls.data = (
                        self.config.get(
                            'auto_log_calls', True
                        )
                    )
                    form.log_encrypted.data = (
                        self.config.get(
                            'log_encrypted', True
                        )
                    )
                    form.log_min_duration_s.data = (
                        self.config.get(
                            'log_min_duration_s', 2
                        )
                    )

                if form.validate_on_submit():
                    # Parse survey frequencies
                    freq_text = (
                        form.survey_frequencies.data or ''
                    )
                    survey_freqs = []
                    for line in freq_text.splitlines():
                        line = line.strip()
                        if line:
                            try:
                                survey_freqs.append(
                                    float(line)
                                )
                            except ValueError:
                                pass

                    new_config = {
                        'center_frequency_mhz': (
                            form.center_frequency_mhz.data
                        ),
                        'source': form.source.data,
                        'sdr_gain': form.sdr_gain.data,
                        'sdr_device_index': (
                            form.sdr_device_index.data
                        ),
                        'op25_port': form.op25_port.data,
                        'nac': form.nac.data or '0',
                        'phase': int(form.phase.data),
                        'scan_mode': form.scan_mode.data,
                        'survey_frequencies': survey_freqs,
                        'dwell_time_ms': (
                            form.dwell_time_ms.data
                        ),
                        'radio_audio_device': (
                            form.radio_audio_device.data
                            or None
                        ),
                        'audio_output_device': (
                            form.audio_output_device.data
                            or None
                        ),
                        'callsign': (
                            form.callsign.data.upper()
                            if form.callsign.data else ''
                        ),
                        'auto_log_calls': (
                            form.auto_log_calls.data
                        ),
                        'log_encrypted': (
                            form.log_encrypted.data
                        ),
                        'log_min_duration_s': (
                            form.log_min_duration_s.data
                        ),
                    }

                    self._save_config(new_config)

                    if self.engine:
                        self.engine.config = self.config
                        self.engine.set_frequency(
                            new_config[
                                'center_frequency_mhz'
                            ]
                        )
                        self.engine.set_nac(
                            new_config['nac']
                        )
                        self.engine.set_scan_mode(
                            new_config['scan_mode']
                        )
                        if survey_freqs:
                            self.engine\
                                .update_survey_frequencies(
                                    survey_freqs
                                )

                    flash('[PLUGIN] Settings saved!', 'success')
                    return redirect(
                        url_for(f'{self.name}.settings')
                    )

                decoder_info = (
                    self.installer.get_decoder_info()
                    if self.installer else {}
                )
                status = (
                    self.engine.get_status()
                    if self.engine else {}
                )

                return render_template(
                    'p25survey/settings.html',
                    plugin=self,
                    form=form,
                    status=status,
                    config=self.config,
                    p25_phases=P25_PHASES,
                    p25_bands=P25_BANDS,
                    common_freqs=COMMON_P25_FREQS,
                    vocoders=VOCODERS,
                    decoder_info=decoder_info,
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
        # API Routes
        # ======================================================

        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get engine status."""
            try:
                if not self.engine:
                    return jsonify({
                        'running': False,
                        'error': 'Engine not ready'
                    })
                return jsonify(self.engine.get_status())
            except Exception as e:
                return jsonify({'error': str(e)})

        @bp.route('/api/frames')
        @login_required
        def api_frames():
            """Get recent decoded frames."""
            try:
                limit = request.args.get(
                    'limit', 50, type=int
                )
                nac = request.args.get(
                    'nac', None, type=int
                )
                if not self.engine:
                    return jsonify({'frames': []})
                return jsonify({
                    'frames': self.engine.get_frames(
                        limit=limit,
                        nac_filter=nac
                    ),
                    'active_call': (
                        self.engine.get_active_call()
                    ),
                })
            except Exception as e:
                return jsonify({
                    'frames': [], 'error': str(e)
                })

        @bp.route('/api/systems')
        @login_required
        def api_systems():
            """Get discovered P25 systems."""
            try:
                if not self.engine:
                    return jsonify({'systems': []})
                systems = self.engine.get_systems()
                return jsonify({
                    'systems': systems,
                    'count': len(systems)
                })
            except Exception as e:
                return jsonify({
                    'systems': [], 'error': str(e)
                })

        @bp.route('/api/clear_systems', methods=['POST'])
        @login_required
        def api_clear_systems():
            """Clear discovered systems."""
            try:
                if self.engine:
                    self.engine.clear_systems()
                return jsonify({
                    'success': True,
                    'message': 'Systems cleared'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/start_rx', methods=['POST'])
        @login_required
        def api_start_rx():
            """Start receive."""
            try:
                if not self.engine:
                    return jsonify({
                        'success': False
                    }), 503
                success, message = (
                    self.engine.start_receive()
                )
                return jsonify({
                    'success': success,
                    'message': message,
                    'status': self.engine.get_status()
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/stop_rx', methods=['POST'])
        @login_required
        def api_stop_rx():
            """Stop receive."""
            try:
                if not self.engine:
                    return jsonify({'success': False}), 503
                self.engine.stop_receive()
                return jsonify({
                    'success': True,
                    'message': 'Receive stopped'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route(
            '/api/set_frequency', methods=['POST']
        )
        @login_required
        def api_set_frequency():
            """Set receive frequency."""
            try:
                data = request.get_json() or {}
                freq = data.get('frequency_mhz')
                if not freq:
                    return jsonify({
                        'success': False,
                        'error': 'frequency_mhz required'
                    }), 400
                freq = float(freq)
                if self.engine:
                    self.engine.set_frequency(freq)
                self._save_config(
                    {'center_frequency_mhz': freq}
                )
                return jsonify({
                    'success': True,
                    'frequency_mhz': freq
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/set_source', methods=['POST'])
        @login_required
        def api_set_source():
            """Switch source."""
            try:
                data = request.get_json() or {}
                source = data.get('source', 'sdr')
                if source not in ('sdr', 'radio'):
                    return jsonify({
                        'success': False,
                        'error': 'Invalid source'
                    }), 400
                if self.engine:
                    self.engine.set_source(source)
                self._save_config({'source': source})
                return jsonify({
                    'success': True,
                    'source': source,
                    'status': (
                        self.engine.get_status()
                        if self.engine else {}
                    )
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/set_mode', methods=['POST'])
        @login_required
        def api_set_mode():
            """Set scan mode."""
            try:
                data = request.get_json() or {}
                mode = data.get('mode', 'conventional')
                if self.engine:
                    self.engine.set_scan_mode(mode)
                self._save_config({'scan_mode': mode})
                return jsonify({
                    'success': True,
                    'mode': mode
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/sync_radio', methods=['POST'])
        @login_required
        def api_sync_radio():
            """Sync frequency from radio."""
            try:
                radio = self.get_device('radio')
                if not radio or not radio.is_connected():
                    return jsonify({
                        'success': False,
                        'error': 'Radio not connected'
                    })
                freq = radio.get_frequency()
                if not freq:
                    return jsonify({
                        'success': False,
                        'error': 'Cannot read frequency'
                    })
                if self.engine:
                    self.engine.set_frequency(freq)
                self._save_config(
                    {'center_frequency_mhz': freq}
                )
                return jsonify({
                    'success': True,
                    'frequency_mhz': freq,
                    'message': f'Synced: {freq:.4f} MHz'
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route(
            '/api/log_contact', methods=['POST']
        )
        @login_required
        def api_log_contact():
            """Log a P25 contact."""
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

                success = self._log_p25_contact(
                    callsign=callsign,
                    talkgroup=data.get('talkgroup'),
                    nac=data.get('nac'),
                    frequency=data.get('frequency'),
                    rst_sent=data.get('rst_sent', '59'),
                    rst_rcvd=data.get('rst_rcvd', '59'),
                    notes=data.get('notes', '')
                )

                return jsonify({
                    'success': success,
                    'message': (
                        f'{callsign} logged!'
                        if success else '[P25][PLUGIN] Logging failed'
                    )
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/logs')
        @login_required
        def api_logs():
            """Get plugin logs."""
            try:
                limit = request.args.get(
                    'limit', 50, type=int
                )
                if not self.engine:
                    return jsonify({'logs': []})
                return jsonify({
                    'logs': self.engine.get_logs(limit)
                })
            except Exception as e:
                return jsonify({
                    'logs': [], 'error': str(e)
                })

    def _log_p25_contact(
        self, callsign, talkgroup=None, nac=None,
        frequency=None, rst_sent='59', rst_rcvd='59',
        notes='', rssi=None, ber=None,
        encrypted=False, phase=1
    ):
        """
        Log a P25 contact to the central logbook.

        Args:
            callsign: Contact callsign or unit ID
            talkgroup: P25 talkgroup ID
            nac: Network Access Code (hex string)
            frequency: Frequency in MHz
            rst_sent: RST sent
            rst_rcvd: RST received
            notes: Additional notes
            rssi: Signal strength
            ber: Bit error rate
            encrypted: Is call encrypted
            phase: P25 Phase (1 or 2)

        Returns:
            bool: True if logged successfully
        """
        try:
            if not callsign:
                return False

            freq = frequency or self.config.get(
                'center_frequency_mhz'
            )
            band = self._freq_to_band(freq) if freq else None

            note_parts = [f'P25 Phase{phase}']

            if nac:
                note_parts.append(f'NAC:{nac}')

            if talkgroup:
                note_parts.append(f'TG:{talkgroup}')

            if encrypted:
                note_parts.append('ENCRYPTED')

            if rssi is not None:
                note_parts.append(f'RSSI:{rssi}dBm')

            if ber is not None:
                note_parts.append(f'BER:{ber:.1f}%')

            if notes:
                note_parts.append(notes)

            contact_data = {
                'callsign': callsign.upper(),
                'mode': f'P25',
                'band': band,
                'frequency': freq,
                'grid': None,
                'rst_sent': rst_sent or '59',
                'rst_rcvd': rst_rcvd or '59',
                'notes': ' | '.join(note_parts)
            }

            success = self.log_contact(contact_data)

            if success:
                print(
                    f"[{self.name}] ✓ Logged: "
                    f"{callsign} P25 TG:{talkgroup}"
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
        try:
            f = float(freq_mhz)
        except (TypeError, ValueError):
            return None

        if 136.0 <= f <= 174.0:
            return 'VHF'
        elif 380.0 <= f <= 512.0:
            return 'UHF'
        elif 763.0 <= f <= 776.0:
            return '700 MHz'
        elif 806.0 <= f <= 870.0:
            return '800 MHz'
        elif 896.0 <= f <= 941.0:
            return '900 MHz'
        return None
