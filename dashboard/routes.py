"""
Main user dashboard.
Displays plugins + GPS + time.
"""

from flask import Blueprint, render_template
from flask_login import login_required, current_user
from gps_service import get_location
from datetime import datetime

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
def dashboard():
    gps = get_location()
    return render_template(
        "dashboard.html",
        callsign=current_user.callsign,
        time=datetime.utcnow(),
        gps=gps
    )