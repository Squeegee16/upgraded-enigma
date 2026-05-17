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
    Get device status with ownership information.

    Returns each device's connection status AND which
    plugin currently has it claimed/active.
    """
    from flask import current_app

    devices = {}
    dm = current_app.extensions.get('device_manager')
    dm_status = dm.get_status() if dm else {}

    # GPS
    try:
        gps = current_app.extensions.get('gps_device')
        owner_info = dm_status.get('gps', {})
        devices['gps'] = {
            'name': 'GPS',
            'available': gps is not None,
            'connected': (
                gps.is_connected() if gps else False
            ),
            'owner': owner_info.get('owner'),
            'device_available': owner_info.get(
                'available', True
            ),
        }
        if gps and gps.is_connected():
            try:
                pos = gps.get_position()
                if pos:
                    devices['gps']['info'] = {
                        'grid': pos.get('grid', 'N/A'),
                        'latitude': round(
                            pos.get('latitude', 0), 4
                        ),
                        'longitude': round(
                            pos.get('longitude', 0), 4
                        ),
                    }
            except Exception:
                pass
    except Exception as e:
        devices['gps'] = {
            'name': 'GPS',
            'available': False,
            'connected': False,
            'owner': None,
            'error': str(e)[:50]
        }

    # Radio
    try:
        radio = current_app.extensions.get('radio_device')
        owner_info = dm_status.get('radio', {})
        devices['radio'] = {
            'name': 'Radio (Hamlib)',
            'available': radio is not None,
            'connected': (
                radio.is_connected() if radio else False
            ),
            'owner': owner_info.get('owner'),
            'device_available': owner_info.get(
                'available', True
            ),
        }
        if radio and radio.is_connected():
            try:
                info = radio.get_info()
                if info:
                    freq = info.get('frequency')
                    devices['radio']['info'] = {
                        'frequency': (
                            f"{freq:.3f} MHz" if freq
                            else 'N/A'
                        ),
                        'mode': info.get('mode', 'N/A'),
                    }
            except Exception:
                pass
    except Exception as e:
        devices['radio'] = {
            'name': 'Radio (Hamlib)',
            'available': False,
            'connected': False,
            'owner': None,
            'error': str(e)[:50]
        }

    # SDR
    try:
        sdr = current_app.extensions.get('sdr_device')
        owner_info = dm_status.get('sdr', {})
        devices['sdr'] = {
            'name': 'RTL-SDR',
            'available': sdr is not None,
            'connected': (
                sdr.is_connected() if sdr else False
            ),
            'owner': owner_info.get('owner'),
            'device_available': owner_info.get(
                'available', True
            ),
        }
        if sdr and sdr.is_connected():
            try:
                freq = sdr.get_frequency()
                devices['sdr']['info'] = {
                    'frequency': (
                        f"{freq:.3f} MHz" if freq
                        else 'N/A'
                    ),
                }
            except Exception:
                pass
    except Exception as e:
        devices['sdr'] = {
            'name': 'RTL-SDR',
            'available': False,
            'connected': False,
            'owner': None,
            'error': str(e)[:50]
        }

    return jsonify(devices)


@dashboard_bp.route('/api/device_manager')
@login_required
def get_device_manager_status():
    """Get full device manager status and history."""
    from flask import current_app
    dm = current_app.extensions.get('device_manager')
    if not dm:
        return jsonify({'available': False})
    return jsonify({
        'available': True,
        'devices': dm.get_status(),
        'history': dm.get_history(10),
    })


@dashboard_bp.route(
    '/api/release_device', methods=['POST']
)
@login_required
def release_device():
    """
    Force-release a device from the dashboard.

    Called when the user confirms they want to
    disconnect a device from the current plugin.
    """
    from flask import current_app
    data = request.get_json() or {}
    device_name = data.get('device')

    if not device_name:
        return jsonify({
            'success': False,
            'error': 'device required'
        }), 400

    dm = current_app.extensions.get('device_manager')
    if not dm:
        return jsonify({
            'success': False,
            'error': 'Device manager not available'
        })

    # Force release (admin action from dashboard)
    success, message = dm.release(device_name, None)
    return jsonify({
        'success': success,
        'message': message,
        'devices': dm.get_status(),
    })

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
@dashboard_bp.route('/api/gps_detail')
@login_required
def get_gps_detail():
    """
    Detailed GPS status API endpoint.

    Returns extended GPS data including:
    - Full position with grid square
    - Satellite information
    - NMEA parser statistics
    - Fix quality details
    - UART port information

    Returns:
        JSON: Complete GPS status
    """
    from flask import current_app

    gps = current_app.extensions.get('gps_device')

    if not gps:
        return jsonify({
            'available': False,
            'error': 'GPS device not configured'
        })

    if not gps.is_connected():
        return jsonify({
            'available': True,
            'connected': False,
            'error': 'GPS not connected'
        })

    try:
        position = gps.get_position()

        if not position:
            return jsonify({
                'available': True,
                'connected': True,
                'has_fix': False,
                'source': getattr(gps, 'source', 'unknown'),
                'error': 'No position data yet'
            })

        # Add grid square precision variants if we have
        # a valid position
        if position.get('latitude') is not None:
            from devices.grid_square import (
                GridSquareCalculator
            )
            calc = GridSquareCalculator()
            lat = position['latitude']
            lon = position['longitude']

            try:
                position['grid_2'] = calc.from_latlon(
                    lat, lon, precision=2
                )
                position['grid_4'] = calc.from_latlon(
                    lat, lon, precision=4
                )
                position['grid_6'] = calc.from_latlon(
                    lat, lon, precision=6
                )
                position['grid_8'] = calc.from_latlon(
                    lat, lon, precision=8
                )
            except Exception:
                pass

        position['available'] = True
        position['connected'] = True

        return jsonify(position)

    except Exception as e:
        return jsonify({
            'available': True,
            'connected': True,
            'error': str(e)
        }), 500


@dashboard_bp.route('/api/gps_raw')
@login_required
def get_gps_raw():
    """
    Recent raw NMEA sentences for diagnostics.

    Returns:
        JSON: List of recent raw NMEA sentences
    """
    from flask import current_app

    gps = current_app.extensions.get('gps_device')

    sentences = []
    if gps and hasattr(gps, 'get_raw_sentences'):
        sentences = gps.get_raw_sentences(count=20)

    stats = {}
    if gps and hasattr(gps, 'get_stats'):
        stats = gps.get_stats()

    return jsonify({
        'sentences': sentences,
        'stats': stats
    })
