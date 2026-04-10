"""
Dashboard Routes
================
Main dashboard and navigation.
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    """
    Main dashboard page.
    
    Displays:
    - Available plugins
    - User callsign
    - Current time (UTC)
    - GPS location (if available)
    - Recent contacts
    """
    from flask import current_app
    from models.logbook import ContactLog
    
    # Get plugin loader
    plugin_loader = current_app.extensions.get('plugin_loader')
    plugins = plugin_loader.get_all_plugins() if plugin_loader else {}
    
    # Get GPS device for location
    gps_device = current_app.extensions.get('gps_device')
    gps_data = None
    
    if gps_device and gps_device.is_connected():
        gps_data = gps_device.get_position()
    
    # Get recent contacts (last 10)
    recent_contacts = ContactLog.query.filter_by(
        operator_id=current_user.id
    ).order_by(ContactLog.timestamp.desc()).limit(10).all()
    
    # Get contact statistics
    total_contacts = ContactLog.query.filter_by(operator_id=current_user.id).count()
    
    return render_template(
        'dashboard/index.html',
        plugins=plugins,
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
        JSON with current time
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
        JSON with GPS data
    """
    from flask import current_app
    
    gps_device = current_app.extensions.get('gps_device')
    
    if not gps_device:
        return jsonify({'error': 'GPS device not available'}), 503
    
    if not gps_device.is_connected():
        return jsonify({'error': 'GPS not connected'}), 503
    
    gps_data = gps_device.get_position()
    
    if gps_data:
        return jsonify(gps_data)
    else:
        return jsonify({'error': 'No GPS fix'}), 503

@dashboard_bp.route('/api/devices')
@login_required
def get_devices():
    """
    API endpoint for device status.
    
    Returns:
        JSON with device connection status
    """
    from flask import current_app
    
    devices = {}
    
    # GPS
    gps_device = current_app.extensions.get('gps_device')
    devices['gps'] = {
        'available': gps_device is not None,
        'connected': gps_device.is_connected() if gps_device else False
    }
    
    # Radio
    radio_device = current_app.extensions.get('radio_device')
    devices['radio'] = {
        'available': radio_device is not None,
        'connected': radio_device.is_connected() if radio_device else False
    }
    
    if radio_device and radio_device.is_connected():
        devices['radio']['info'] = radio_device.get_info()
    
    # SDR
    sdr_device = current_app.extensions.get('sdr_device')
    devices['sdr'] = {
        'available': sdr_device is not None,
        'connected': sdr_device.is_connected() if sdr_device else False
    }
    
    return jsonify(devices)