"""
Dashboard Routes
================
Main dashboard and navigation.

Provides:
    - Main dashboard with plugin list
    - GPS location API
    - Device status API
    - Time API
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import datetime

dashboard_bp = Blueprint(
    'dashboard', __name__, url_prefix='/dashboard'
)


@dashboard_bp.route('/')
@login_required
def index():
    """
    Main dashboard page.

    Displays:
    - All loaded plugins with descriptions and launch buttons
    - User callsign
    - Current UTC time
    - GPS location
    - Recent contacts
    - Device status
    """
    from flask import current_app
    from models.logbook import ContactLog

    # -------------------------------------------------------
    # Get plugin loader and build plugin list for display
    # -------------------------------------------------------
    plugin_loader = current_app.extensions.get('plugin_loader')

    # Get structured plugin list for dashboard cards
    plugin_list = []
    if plugin_loader:
        plugin_list = plugin_loader.get_plugin_list()

    # Raw plugin dict (kept for nav menu compatibility)
    plugins = plugin_loader.get_all_plugins() \
        if plugin_loader else {}

    # -------------------------------------------------------
    # GPS Data
    # -------------------------------------------------------
    gps_device = current_app.extensions.get('gps_device')
    gps_data = None

    if gps_device and gps_device.is_connected():
        try:
            gps_data = gps_device.get_position()
        except Exception as e:
            print(f"[Dashboard] GPS error: {e}")

    # -------------------------------------------------------
    # Recent Contacts
    # -------------------------------------------------------
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
        recent_contacts = []
        total_contacts = 0

    return render_template(
        'dashboard/index.html',
        plugins=plugins,           # For nav menu
        plugin_list=plugin_list,   # For dashboard cards
        gps_data=gps_data,
        recent_contacts=recent_contacts,
        total_contacts=total_contacts,
        current_time=datetime.utcnow()
    )


@dashboard_bp.route('/api/time')
@login_required
def get_time():
    """
    API endpoint for current UTC time.

    Returns:
        JSON: UTC and local time strings
    """
    return jsonify({
        'utc': datetime.utcnow().isoformat(),
        'local': datetime.now().isoformat()
    })


@dashboard_bp.route('/api/location')
@login_required
def get_location():
    """
    API endpoint for GPS location.

    Returns:
        JSON: GPS position data or error
    """
    from flask import current_app

    gps_device = current_app.extensions.get('gps_device')

    if not gps_device:
        return jsonify({
            'error': 'GPS device not configured'
        }), 503

    if not gps_device.is_connected():
        return jsonify({
            'error': 'GPS not connected'
        }), 503

    try:
        gps_data = gps_device.get_position()
        if gps_data:
            return jsonify(gps_data)
        else:
            return jsonify({'error': 'No GPS fix'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/devices')
@login_required
def get_devices():
    """
    API endpoint for device status.

    Returns:
        JSON: Status of GPS, radio, and SDR devices
    """
    from flask import current_app

    devices = {}

    # GPS status
    gps_device = current_app.extensions.get('gps_device')
    devices['gps'] = {
        'available': gps_device is not None,
        'connected': (
            gps_device.is_connected()
            if gps_device else False
        ),
        'name': 'GPS'
    }

    # Radio status
    radio_device = current_app.extensions.get('radio_device')
    devices['radio'] = {
        'available': radio_device is not None,
        'connected': (
            radio_device.is_connected()
            if radio_device else False
        ),
        'name': 'Radio (Hamlib)'
    }

    if radio_device and radio_device.is_connected():
        try:
            devices['radio']['info'] = radio_device.get_info()
        except Exception:
            pass

    # SDR status
    sdr_device = current_app.extensions.get('sdr_device')
    devices['sdr'] = {
        'available': sdr_device is not None,
        'connected': (
            sdr_device.is_connected()
            if sdr_device else False
        ),
        'name': 'RTL-SDR'
    }

    return jsonify(devices)


@dashboard_bp.route('/api/plugins')
@login_required
def get_plugins():
    """
    API endpoint for loaded plugin list.

    Returns:
        JSON: List of loaded plugins with metadata
    """
    from flask import current_app

    plugin_loader = current_app.extensions.get('plugin_loader')

    if not plugin_loader:
        return jsonify({'plugins': []})

    return jsonify({
        'plugins': plugin_loader.get_plugin_list()
    })
