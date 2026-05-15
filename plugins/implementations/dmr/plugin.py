"""
DMR Plugin Main
================
Flask plugin class for DMR (Digital Mobile Radio)
receive, transmit, and logbook integration.
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
from plugins.implementations.dmr.installer import (
    DMRInstaller
)
from plugins.implementations.dmr.dmr_engine import (
    DMREngine
)
from plugins.implementations.dmr.dmr_constants import (
    COMMON_TALKGROUPS, DMR_TIERS,
    COMMON_FREQUENCIES, CODECS,
    CHANNEL_BW_KHZ, SYMBOL_RATE,
    TDMA_SLOTS := 2,
)
from plugins.implementations.dmr.forms import (
    DMRSettingsForm,
    DMRLogForm
)


class DMRPlugin(BasePlugin):
    """
    DMR Digital Mobile Radio Plugin.

    Provides DMR Tier I/II/III receive and transmit
    with on-screen PTT and logbook integration.
    """

    name = "DMR"
    description = (
        "DMR Tier I/II/III digital voice receive, "
        "on-screen PTT, and call logging"
    )
    version = "1.0.0"
    author = "Ham Radio App Team"
    url = (
        "https://qradiolink.org/"
        "open-source-DMR-transceiver-implementation.html"
    )

    def __init__(self, app=None, devices=None):
        """Initialise DMR plugin."""
        super().__init__(app, devices)

        self.plugin_data_dir = os.path.join(
            os.environ.get('DATA_DIR', '/data'),
            'plugins', 'dmr'
        )
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        self.installer = DMRInstaller()
        self.engine = None
        self.config = self._load_config()

        self.install_complete = False
        self.install_error = None

        # Call tracking for auto-logging
        self._active_call_start = None

    def _load_config(self):
        """Load plugin configuration."""
        config_file = os.path.join(
            self.plugin_data_dir, 'dmr_config.json'
        )
        defaults = {
            'center_frequency_mhz': 438.0,
            'source': 'sdr',
            'sdr_gain': 40,
            'sdr_device_index': 0,
            'tier': 2,
            'color_code': 1,
            'timeslot': 1,
            'talkgroup': 9990,
            'source_id': 3000000,
            'network_type': 'BrandMeister',
            'repeater_callsign': '',
            'radio_audio_device': None,
            'audio_output_device': None,
            'ptt_port': '',
            'tx_power': 4,
            'mic_gain': 100,
            'squelch_level': 0,
            'callsign': '',
            'auto_log_calls': True,
            'log_min_duration_s': 2,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                print(f"[DMR] Config load error: {e}")

        return defaults

    def _save_config(self, config_data):
        """Save plugin configuration."""
        config_file = os.path.join(
            self.plugin_data_dir, 'dmr_config.json'
        )
        try:
            self.config.update(config_data)
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"[DMR] Config save error: {e}")
            return False

    def initialize(self):
        """Initialize the DMR plugin."""
        print(f"\n[{self.name}] Initializing plugin...")

        try:
            install_success = self.installer.run()
            self.install_complete = install_success

            # Create DMR engine
            self.engine = DMREngine(self.config)

            # Register call callback for auto-logging
            self.engine.register_call_callback(
                self._on_call_event
            )

            # Set callsign from user if not set
            if not self.config.get('callsign'):
                try:
                    cs = getattr(
                        current_user, 'callsign', ''
                    )
                    if cs:
                        self._save_config({'callsign': cs})
                except RuntimeError:
                    pass

            # Auto-start receiver
            success, msg = self.engine.start_receive()
            if success:
                print(f"[{self.name}] ✓ {msg}")
            else:
                print(f"[{self.name}] Receive: {msg}")

            print(f"[{self.name}] ✓ Plugin initialized")
            return True

        except Exception as e:
            self.install_error = str(e)
            print(f"[{self.name}] ERROR: {e}")
            traceback.print_exc()
            return False

    def shutdown(self):
        """Clean shutdown."""
        print(f"[{self.name}] Shutting down...")
        if self.engine:
            self.engine.stop_receive()
            if self.engine._transmitting:
                self.engine.stop_transmit()
        print(f"[{self.name}] ✓ Shutdown complete")

    def _on_call_event(self, event_type, call_data):
        """
        Handle call start/end events from the engine.

        Auto-logs qualifying calls to the logbook.

        Args:
            event_type: 'start' or 'end'
            call_data: DMRFrame dict
        """
        if event_type == 'start':
            self._active_call_start = datetime.utcnow()

        elif event_type == 'end':
            if not self.config.get(
                'auto_log_calls', True
            ):
                return

            if not self._active_call_start:
                return

            duration = (
                datetime.utcnow() -
                self._active_call_start
            ).total_seconds()

            min_dur = self.config.get(
                'log_min_duration_s', 2
            )

            if duration >= min_dur:
                callsign = call_data.get(
                    'source_alias', ''
                ) or f"ID:{call_data.get('source_id', '?')}"

                self._log_dmr_call(
                    callsign=callsign,
                    source_id=call_data.get('source_id'),
                    talkgroup=call_data.get('talkgroup'),
                    timeslot=call_data.get('timeslot'),
                    frequency=self.config.get(
                        'center_frequency_mhz'
                    ),
                    rssi=call_data.get('rssi'),
                    ber=call_data.get('ber'),
                    notes=f"Auto-logged | Duration: "
                          f"{duration:.1f}s"
                )

            self._active_call_start = None

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
            url_prefix='/plugin/dmr',
            template_folder=template_dir
        )

        self._register_routes(bp)
        return bp

    def _register_routes(self, bp):
        """Register all plugin routes."""

        @bp.route('/')
        @login_required
        def index():
            """DMR main page."""
            try:
                status = (
                    self.engine.get_status()
                    if self.engine else {}
                )
                frames = (
                    self.engine.get_frames(limit=30)
                    if self.engine else []
                )
                logs = (
                    self.engine.get_logs(30)
                    if self.engine else []
                )
                log_form = DMRLogForm()

                # Talkgroup name lookup
                tg = self.config.get('talkgroup', 9990)
                tg_name = COMMON_TALKGROUPS.get(tg, '')

                # Radio device info
                radio_info = {}
                radio = self.get_device('radio')
                if radio and radio.is_connected():
                    try:
                        radio_info = radio.get_info()
                    except Exception:
                        pass

                return render_template(
                    'dmr/index.html',
                    plugin=self,
                    status=status,
                    frames=frames,
                    logs=logs,
                    log_form=log_form,
                    radio_info=radio_info,
                    config=self.config,
                    talkgroups=COMMON_TALKGROUPS,
                    tg_name=tg_name,
                    dmr_tiers=DMR_TIERS,
                    install_complete=self.install_complete,
                    install_error=self.install_error,
                    # Protocol reference constants
                    CHANNEL_BW_KHZ=CHANNEL_BW_KHZ,
                    SYMBOL_RATE=SYMBOL_RATE,
                    CODECS=CODECS,
                    COMMON_FREQUENCIES=COMMON_FREQUENCIES,
                )

            except Exception as e:
                print(f"[{self.name}] Index error: {e}")
                traceback.print_exc()
                return render_template(
                    'errors/500.html', error=str(e)
                ), 500

        @bp.route('/settings', methods=['GET', 'POST'])
        @login_required
        def settings():
            """Settings page."""
            try:
                form = DMRSettingsForm()

                if request.method == 'GET':
                    form.center_frequency_mhz.data = (
                        self.config.get(
                            'center_frequency_mhz', 438.0
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
                    form.tier.data = str(
                        self.config.get('tier', 2)
                    )
                    form.color_code.data = self.config.get(
                        'color_code', 1
                    )
                    form.timeslot.data = str(
                        self.config.get('timeslot', 1)
                    )
                    form.talkgroup.data = self.config.get(
                        'talkgroup', 9990
                    )
                    form.source_id.data = self.config.get(
                        'source_id', 3000000
                    )
                    form.network_type.data = (
                        self.config.get(
                            'network_type', 'BrandMeister'
                        )
                    )
                    form.repeater_callsign.data = (
                        self.config.get(
                            'repeater_callsign', ''
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
                    form.ptt_port.data = self.config.get(
                        'ptt_port', ''
                    )
                    form.tx_power.data = self.config.get(
                        'tx_power', 4
                    )
                    form.mic_gain.data = self.config.get(
                        'mic_gain', 100
                    )
                    form.squelch_level.data = (
                        self.config.get('squelch_level', 0)
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
                    form.log_min_duration_s.data = (
                        self.config.get(
                            'log_min_duration_s', 2
                        )
                    )

                if form.validate_on_submit():
                    new_config = {
                        'center_frequency_mhz': (
                            form.center_frequency_mhz.data
                        ),
                        'source': form.source.data,
                        'sdr_gain': form.sdr_gain.data,
                        'sdr_device_index': (
                            form.sdr_device_index.data
                        ),
                        'tier': int(form.tier.data),
                        'color_code': form.color_code.data,
                        'timeslot': int(form.timeslot.data),
                        'talkgroup': form.talkgroup.data,
                        'source_id': form.source_id.data,
                        'network_type': (
                            form.network_type.data
                        ),
                        'repeater_callsign': (
                            form.repeater_callsign.data
                            or ''
                        ),
                        'radio_audio_device': (
                            form.radio_audio_device.data
                            or None
                        ),
                        'audio_output_device': (
                            form.audio_output_device.data
                            or None
                        ),
                        'ptt_port': (
                            form.ptt_port.data or ''
                        ),
                        'tx_power': form.tx_power.data,
                        'mic_gain': form.mic_gain.data,
                        'squelch_level': (
                            form.squelch_level.data
                        ),
                        'callsign': (
                            form.callsign.data.upper()
                            if form.callsign.data else ''
                        ),
                        'auto_log_calls': (
                            form.auto_log_calls.data
                        ),
                        'log_min_duration_s': (
                            form.log_min_duration_s.data
                        ),
                    }

                    self._save_config(new_config)

                    # Apply to engine
                    if self.engine:
                        self.engine.config = self.config
                        self.engine.set_frequency(
                            new_config[
                                'center_frequency_mhz'
                            ]
                        )
                        self.engine.set_color_code(
                            new_config['color_code']
                        )
                        self.engine.set_timeslot(
                            new_config['timeslot']
                        )
                        self.engine.set_talkgroup(
                            new_config['talkgroup']
                        )

                    flash('Settings saved!', 'success')
                    return redirect(
                        url_for(f'{self.name}.settings')
                    )

                status = (
                    self.engine.get_status()
                    if self.engine else {}
                )

                return render_template(
                    'dmr/settings.html',
                    plugin=self,
                    form=form,
                    status=status,
                    config=self.config,
                    talkgroups=COMMON_TALKGROUPS,
                    dmr_tiers=DMR_TIERS,
                    common_frequencies=COMMON_FREQUENCIES,
                    codecs=CODECS,
                    decoder_info=(
                        self.installer.get_decoder_info()
                        if self.installer else {}
                    ),
                )

            except Exception as e:
                print(
                    f"[{self.name}] Settings error: {e}"
                )
                traceback.print_exc()
                return render_template(
                    'errors/500.html', error=str(e)
                ), 500

        # ======================================================
        # API routes
        # ======================================================

        @bp.route('/api/status')
        @login_required
        def api_status():
            """Get DMR engine status."""
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
                    'limit', 30, type=int
                )
                ts = request.args.get(
                    'timeslot', None, type=int
                )
                if not self.engine:
                    return jsonify({'frames': []})
                return jsonify({
                    'frames': self.engine.get_frames(
                        limit=limit, timeslot=ts
                    ),
                    'active_call': (
                        self.engine.get_active_call()
                    ),
                })
            except Exception as e:
                return jsonify({
                    'frames': [], 'error': str(e)
                })

        @bp.route('/api/start_rx', methods=['POST'])
        @login_required
        def api_start_rx():
            """Start receive."""
            try:
                if not self.engine:
                    return jsonify({
                        'success': False,
                        'error': 'Engine not ready'
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

        @bp.route('/api/ptt_start', methods=['POST'])
        @login_required
        def api_ptt_start():
            """Start PTT transmit."""
            try:
                if not self.engine:
                    return jsonify({
                        'success': False,
                        'error': 'Engine not ready'
                    }), 503
                success, message = (
                    self.engine.start_transmit()
                )
                return jsonify({
                    'success': success,
                    'message': message
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/ptt_stop', methods=['POST'])
        @login_required
        def api_ptt_stop():
            """Stop PTT transmit."""
            try:
                if not self.engine:
                    return jsonify({'success': False}), 503
                success, message = (
                    self.engine.stop_transmit()
                )
                return jsonify({
                    'success': success,
                    'message': message
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/set_source', methods=['POST'])
        @login_required
        def api_set_source():
            """Switch between SDR and radio source."""
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

        @bp.route('/api/set_frequency', methods=['POST'])
        @login_required
        def api_set_frequency():
            """Set SDR center frequency."""
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

        @bp.route('/api/set_channel', methods=['POST'])
        @login_required
        def api_set_channel():
            """Set DMR channel parameters."""
            try:
                data = request.get_json() or {}
                updates = {}

                if 'color_code' in data:
                    cc = int(data['color_code'])
                    if 0 <= cc <= 15:
                        if self.engine:
                            self.engine.set_color_code(cc)
                        updates['color_code'] = cc

                if 'timeslot' in data:
                    ts = int(data['timeslot'])
                    if ts in (1, 2):
                        if self.engine:
                            self.engine.set_timeslot(ts)
                        updates['timeslot'] = ts

                if 'talkgroup' in data:
                    tg = int(data['talkgroup'])
                    if self.engine:
                        self.engine.set_talkgroup(tg)
                    updates['talkgroup'] = tg

                if updates:
                    self._save_config(updates)

                return jsonify({
                    'success': True,
                    'updates': updates,
                    'status': (
                        self.engine.get_status()
                        if self.engine else {}
                    )
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

        @bp.route('/api/log_contact', methods=['POST'])
        @login_required
        def api_log_contact():
            """Log a DMR contact."""
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

                success = self._log_dmr_call(
                    callsign=callsign,
                    source_id=data.get('dmr_id'),
                    talkgroup=data.get('talkgroup'),
                    timeslot=data.get('timeslot', 1),
                    frequency=data.get('frequency'),
                    rst_sent=data.get('rst_sent', '59'),
                    rst_rcvd=data.get('rst_rcvd', '59'),
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

        @bp.route('/api/sync_radio', methods=['POST'])
        @login_required
        def api_sync_radio():
            """Sync frequency from configured radio."""
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
                    'message': (
                        f'Synced: {freq:.4f} MHz'
                    )
                })
            except Exception as e:
                return jsonify({
                    'success': False, 'error': str(e)
                }), 500

    def _log_dmr_call(
        self, callsign, source_id=None,
        talkgroup=None, timeslot=1,
        frequency=None, rst_sent='59', rst_rcvd='59',
        rssi=None, ber=None, notes=''
    ):
        """
        Log a DMR call to the central logbook.

        Args:
            callsign: Contact callsign or ID string
            source_id: Source DMR radio ID
            talkgroup: Talk group number
            timeslot: TDMA timeslot (1 or 2)
            frequency: Frequency in MHz
            rst_sent: RST sent
            rst_rcvd: RST received
            rssi: Signal strength dBm
            ber: Bit error rate %
            notes: Additional notes

        Returns:
            bool: True if logged
        """
        try:
            if not callsign:
                return False

            freq = frequency or self.config.get(
                'center_frequency_mhz'
            )
            band = self._freq_to_band(freq) if freq else None

            tg = talkgroup or self.config.get('talkgroup')
            tg_name = COMMON_TALKGROUPS.get(tg, '')

            note_parts = ['DMR']
            if source_id:
                note_parts.append(f'ID:{source_id}')
            if tg:
                note_parts.append(
                    f'TG:{tg}'
                    + (f'({tg_name})' if tg_name else '')
                )
            if timeslot:
                note_parts.append(f'TS:{timeslot}')
            if rssi is not None:
                note_parts.append(f'RSSI:{rssi}dBm')
            if ber is not None:
                note_parts.append(f'BER:{ber:.1f}%')
            if notes:
                note_parts.append(notes)

            cc = self.config.get('color_code', 1)
            tier = self.config.get('tier', 2)
            note_parts.append(f'CC:{cc}')
            note_parts.append(f'Tier:{tier}')

            contact_data = {
                'callsign': callsign.upper(),
                'mode': 'DMR',
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
                    f"{callsign} DMR TG:{tg}"
                )

            return success

        except Exception as e:
            print(f"[{self.name}] Log error: {e}")
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
        bands = [
            (144.0, 148.0, '2m'),
            (222.0, 225.0, '1.25m'),
            (420.0, 450.0, '70cm'),
            (902.0, 928.0, '33cm'),
            (1240.0, 1300.0, '23cm'),
            (146.0, 148.0, '2m'),
            (151.0, 155.0, 'VHF'),
            (450.0, 512.0, 'UHF'),
        ]
        for low, high, band in bands:
            if low <= f <= high:
                return band
        return None
