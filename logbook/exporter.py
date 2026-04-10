"""
Export logbook to CSV / JSON / ADIF
"""

import csv, json
from models import ContactLog

def export_csv():
    logs = ContactLog.query.all()
    output = []
    for l in logs:
        output.append([l.contact_callsign, l.mode, l.band, l.grid, l.signal_report, l.timestamp])
    return output

def export_json():
    logs = ContactLog.query.all()
    return json.dumps([{
        "callsign": l.contact_callsign,
        "mode": l.mode,
        "band": l.band,
        "grid": l.grid,
        "signal": l.signal_report,
        "timestamp": str(l.timestamp)
    } for l in logs])