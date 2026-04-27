"""
Dashboard Routes
================
Fixed version with robust device status API that
always returns a valid JSON response.
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import traceback

dashboard_bp = Blueprint(
    'dashboard', __name__, url_prefix='/dashboard'
)


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard page."""
    from flask import current_app
    from models.logbook import ContactLog

    # Plugins
    plugin_loader = current_app.extensions.get('plugin_loader')
    plugin_list = []
    plugins = {}
    if plugin_loader:
        try:
            plugin_list = plugin_loader.get_plugin_list()
            plugins = plugin_loader.get_all_plugins()
        except Exception:
            pass

    # GPS
    gps_data = None
    try:
        gps_device = current_app.extensions.get('gps_device')
        if gps_device and gps_device.is_connected():
            gps_data = gps_device.get_position()
    except Exception as e:
        print(f"[Dashboard] GPS error: {e}")

    # Contacts
    recent_contacts = []
    total_contacts = 0
    try:
        recent_contacts = ContactLog.query.filter_by(
            operator_id=current_user.id
        ).order_by(
            ContactLog.timestamp.desc()
        ).limit(10).all()
        total_contacts = ContactLog.query.filter_by(
            operator_id=current_user.id
        ).count()
    except Exception as e:
        print(f"[Dashboard] Contacts error: {e}")

    # Callsign lookup
    operator_info = None
    db_stats = None
    try:
        callsign_db = current_app.extensions.get('callsign_db')
        if callsign_db:
            operator_info = callsign_db.lookup(
                current_user.callsign
            )
            db_stats = callsign_db.get_stats()
    except Exception as e:
        print(f"[Dashboard] Callsign DB error: {e}")

    return render_template(
        'dashboard/index.html',
        plugins=plugins,
        plugin_list=plugin_list,
        gps_data=gps_data,
        recent_contacts=recent_contacts,
        total_contacts=total_contacts,
        current_time=datetime.utcnow(),
        operator_info=operator_info,
        db_stats=db_stats,
    )


@dashboard_bp.route('/api/devices')
@login_required
def get_devices():
    """
    Device status API endpoint.

    Always returns a valid JSON response even if
    device queries fail. Each device is queried
    independently so one failure does not affect others.

    Returns:
        JSON: Status dict for gps, radio, and sdr devices
    """
    from flask import current_app

    devices = {}

    # -------------------------------------------------------
    # GPS Device
    # -------------------------------------------------------
    try:
        gps = current_app.extensions.get('gps_device')
        if gps is None:
            devices['gps'] = {
                'name': 'GPS',
                'available': False,
                'connected': False,
                'info': 'Not configured'
            }
        else:
            connected = False
            info_data = {}

            try:
                connected = bool(gps.is_connected())
            except Exception as e:
                print(f"[Dashboard] GPS is_connected error: {e}")

            if connected:
                try:
                    pos = gps.get_position()
                    if pos:
                        info_data = {
                            'grid': pos.get('grid', 'N/A'),
                            'latitude': round(
                                pos.get('latitude', 0), 4
                            ),
                            'longitude': round(
                                pos.get('longitude', 0), 4
                            ),
                            'satellites': pos.get(
                                'satellites', 0
                            ),
                        }
                except Exception as e:
                    print(f"[Dashboard] GPS position error: {e}")

            devices['gps'] = {
                'name': 'GPS',
                'available': True,
                'connected': connected,
                'info': info_data
            }

    except Exception as e:
        print(f"[Dashboard] GPS device block error: {e}")
        devices['gps'] = {
            'name': 'GPS',
            'available': False,
            'connected': False,
            'info': f'Error: {str(e)[:50]}'
        }

    # -------------------------------------------------------
    # Radio Device (Hamlib)
    # -------------------------------------------------------
    try:
        radio = current_app.extensions.get('radio_device')
        if radio is None:
            devices['radio'] = {
                'name': 'Radio (Hamlib)',
                'available': False,
                'connected': False,
                'info': 'Not configured'
            }
        else:
            connected = False
            info_data = {}

            try:
                connected = bool(radio.is_connected())
            except Exception as e:
                print(
                    f"[Dashboard] Radio is_connected error: {e}"
                )

            if connected:
                try:
                    radio_info = radio.get_info()
                    if radio_info:
                        freq = radio_info.get('frequency')
                        info_data = {
                            'frequency': (
                                f"{freq:.3f} MHz"
                                if freq else 'N/A'
                            ),
                            'mode': radio_info.get(
                                'mode', 'N/A'
                            ),
                        }
                except Exception as e:
                    print(
                        f"[Dashboard] Radio info error: {e}"
                    )

            devices['radio'] = {
                'name': 'Radio (Hamlib)',
                'available': True,
                'connected': connected,
                'info': info_data
            }

    except Exception as e:
        print(f"[Dashboard] Radio device block error: {e}")
        devices['radio'] = {
            'name': 'Radio (Hamlib)',
            'available': False,
            'connected': False,
            'info': f'Error: {str(e)[:50]}'
        }

    # -------------------------------------------------------
    # SDR Device (RTL-SDR)
    # -------------------------------------------------------
    try:
        sdr = current_app.extensions.get('sdr_device')
        if sdr is None:
            devices['sdr'] = {
                'name': 'RTL-SDR',
                'available': False,
                'connected': False,
                'info': 'Not configured'
            }
        else:
            connected = False
            info_data = {}

            try:
                connected = bool(sdr.is_connected())
            except Exception as e:
                print(
                    f"[Dashboard] SDR is_connected error: {e}"
                )

            if connected:
                try:
                    freq = sdr.get_frequency()
                    info_data = {
                        'frequency': (
                            f"{freq:.3f} MHz"
                            if freq else 'N/A'
                        ),
                    }
                except Exception as e:
                    print(f"[Dashboard] SDR info error: {e}")

            devices['sdr'] = {
                'name': 'RTL-SDR',
                'available': True,
                'connected': connected,
                'info': info_data
            }

    except Exception as e:
        print(f"[Dashboard] SDR device block error: {e}")
        devices['sdr'] = {
            'name': 'RTL-SDR',
            'available': False,
            'connected': False,
            'info': f'Error: {str(e)[:50]}'
        }

    # Always return valid JSON
    return jsonify(devices)


@dashboard_bp.route('/api/time')
@login_required
def get_time():
    """Get current UTC time."""
    return jsonify({
        'utc': datetime.utcnow().isoformat(),
        'local': datetime.now().isoformat()
    })


@dashboard_bp.route('/api/location')
@login_required
def get_location():
    """Get GPS position."""
    from flask import current_app
    try:
        gps = current_app.extensions.get('gps_device')
        if not gps:
            return jsonify({'error': 'GPS not configured'}), 503
        if not gps.is_connected():
            return jsonify({'error': 'GPS not connected'}), 503
        pos = gps.get_position()
        if pos:
            return jsonify(pos)
        return jsonify({'error': 'No GPS fix'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/callsign_lookup/<callsign>')
@login_required
def callsign_lookup(callsign):
    """Look up a callsign in the ISED database."""
    from flask import current_app
    try:
        callsign_db = current_app.extensions.get('callsign_db')
        if not callsign_db:
            return jsonify({'found': False, 'error': 'DB unavailable'})
        operator = callsign_db.lookup(callsign)
        if operator:
            return jsonify({'found': True, 'operator': operator})
        return jsonify({'found': False, 'callsign': callsign.upper()})
    except Exception as e:
        return jsonify({'found': False, 'error': str(e)})


@dashboard_bp.route('/api/db_update', methods=['POST'])
@login_required
def db_update():
    """Start ISED database download."""
    from flask import current_app
    try:
        callsign_db = current_app.extensions.get('callsign_db')
        if not callsign_db:
            return jsonify({'success': False, 'error': 'DB unavailable'}), 503
        if callsign_db.is_downloading():
            return jsonify({'success': False, 'error': 'Already downloading'})
        started = callsign_db.start_update(
            current_app._get_current_object()
        )
        return jsonify({
            'success': started,
            'message': 'Update started' if started else 'Failed'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@dashboard_bp.route('/api/db_status')
@login_required
def db_status():
    """Get ISED database download status."""
    from flask import current_app
    try:
        callsign_db = current_app.extensions.get('callsign_db')
        if not callsign_db:
            return jsonify({'available': False})
        return jsonify({
            'available': True,
            'state': callsign_db.get_download_state(),
            'stats': callsign_db.get_stats()
        })
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})


@dashboard_bp.route('/api/plugins')
@login_required
def get_plugins():
    """Get loaded plugin list."""
    from flask import current_app
    try:
        loader = current_app.extensions.get('plugin_loader')
        if not loader:
            return jsonify({'plugins': []})
        return jsonify({'plugins': loader.get_plugin_list()})
    except Exception as e:
        return jsonify({'plugins': [], 'error': str(e)})
