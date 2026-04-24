"""
Dashboard Routes
================
Main dashboard and navigation.

Provides:
    - Main dashboard with plugin list
    - GPS location API
    - Device status API
    - Time API
    - Updated with Canadian callsign database integration.
"""

from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime

dashboard_bp = Blueprint(
    'dashboard', __name__, url_prefix='/dashboard'
)


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard with callsign database operator info."""
    from models.logbook import ContactLog

    # Plugin list
    plugin_loader = current_app.extensions.get('plugin_loader')
    plugin_list = []
    plugins = {}
    if plugin_loader:
        plugin_list = plugin_loader.get_plugin_list()
        plugins = plugin_loader.get_all_plugins()

    # GPS data
    gps_device = current_app.extensions.get('gps_device')
    gps_data = None
    if gps_device and gps_device.is_connected():
        try:
            gps_data = gps_device.get_position()
        except Exception:
            pass

    # Recent contacts
    try:
        recent_contacts = ContactLog.query.filter_by(
            operator_id=current_user.id
        ).order_by(
            ContactLog.timestamp.desc()
        ).limit(10).all()
        total_contacts = ContactLog.query.filter_by(
            operator_id=current_user.id
        ).count()
    except Exception:
        recent_contacts = []
        total_contacts = 0

    # -------------------------------------------------------
    # Look up current user's callsign in ISED database
    # -------------------------------------------------------
    operator_info = None
    callsign_db = current_app.extensions.get('callsign_db')

    if callsign_db:
        try:
            operator_info = callsign_db.lookup(
                current_user.callsign
            )
        except Exception as e:
            print(f"[Dashboard] Callsign lookup error: {e}")

    # -------------------------------------------------------
    # Database statistics for update button display
    # -------------------------------------------------------
    db_stats = None
    if callsign_db:
        try:
            db_stats = callsign_db.get_stats()
        except Exception:
            pass

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


# ---------------------------------------------------------------
# Callsign Database API Routes
# ---------------------------------------------------------------

@dashboard_bp.route('/api/callsign_lookup/<callsign>')
@login_required
def callsign_lookup(callsign):
    """
    API endpoint for callsign database lookup.

    Args:
        callsign: Callsign to look up

    Returns:
        JSON: Operator data or not-found message
    """
    callsign_db = current_app.extensions.get('callsign_db')

    if not callsign_db:
        return jsonify({
            'found': False,
            'error': 'Callsign database not available'
        })

    operator = callsign_db.lookup(callsign)

    if operator:
        return jsonify({
            'found': True,
            'operator': operator
        })
    else:
        return jsonify({
            'found': False,
            'callsign': callsign.upper(),
            'message': 'Callsign not found in database'
        })


@dashboard_bp.route('/api/callsign_search')
@login_required
def callsign_search():
    """
    API endpoint for partial callsign search (autocomplete).

    Query params:
        q: Partial callsign to search

    Returns:
        JSON: List of matching operators
    """
    from flask import request

    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'results': []})

    callsign_db = current_app.extensions.get('callsign_db')
    if not callsign_db:
        return jsonify({'results': []})

    results = callsign_db.lookup_partial(query, limit=10)
    return jsonify({'results': results})


@dashboard_bp.route('/api/db_update', methods=['POST'])
@login_required
def db_update():
    """
    API endpoint to trigger ISED database download.

    Starts the database download in the background.
    Poll /api/db_status for progress.

    Returns:
        JSON: Start status
    """
    callsign_db = current_app.extensions.get('callsign_db')

    if not callsign_db:
        return jsonify({
            'success': False,
            'error': 'Callsign database not configured'
        }), 503

    if callsign_db.is_downloading():
        state = callsign_db.get_download_state()
        return jsonify({
            'success': False,
            'error': 'Download already in progress',
            'state': state
        })

    started = callsign_db.start_update(current_app._get_current_object())

    if started:
        return jsonify({
            'success': True,
            'message': 'Database update started'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to start update'
        })


@dashboard_bp.route('/api/db_status')
@login_required
def db_status():
    """
    API endpoint for database download progress.

    Returns:
        JSON: Current download state and database stats
    """
    callsign_db = current_app.extensions.get('callsign_db')

    if not callsign_db:
        return jsonify({
            'available': False,
            'state': {'status': 'unavailable'}
        })

    return jsonify({
        'available': True,
        'state': callsign_db.get_download_state(),
        'stats': callsign_db.get_stats()
    })


# ---------------------------------------------------------------
# Existing API routes
# ---------------------------------------------------------------
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
    """Get GPS location."""
    gps_device = current_app.extensions.get('gps_device')
    if not gps_device:
        return jsonify({'error': 'GPS not configured'}), 503
    if not gps_device.is_connected():
        return jsonify({'error': 'GPS not connected'}), 503
    try:
        gps_data = gps_device.get_position()
        if gps_data:
            return jsonify(gps_data)
        return jsonify({'error': 'No GPS fix'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/devices')
@login_required
def get_devices():
    """Get device status."""
    devices = {}
    for key, label in [
        ('gps_device', 'GPS'),
        ('radio_device', 'Radio'),
        ('sdr_device', 'RTL-SDR')
    ]:
        dev = current_app.extensions.get(key)
        devices[key.replace('_device', '')] = {
            'available': dev is not None,
            'connected': dev.is_connected() if dev else False,
            'name': label
        }
    return jsonify(devices)


@dashboard_bp.route('/api/plugins')
@login_required
def get_plugins():
    """Get loaded plugin list."""
    plugin_loader = current_app.extensions.get('plugin_loader')
    if not plugin_loader:
        return jsonify({'plugins': []})
    return jsonify({'plugins': plugin_loader.get_plugin_list()})
