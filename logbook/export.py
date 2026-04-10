"""
Logbook Export
==============
Functions for exporting contact logs in various formats.
"""

import csv
import json
from io import StringIO
from datetime import datetime
from models.logbook import ContactLog

def export_to_csv(contacts):
    """
    Export contacts to CSV format.
    
    Args:
        contacts: List of ContactLog objects
        
    Returns:
        str: CSV formatted string
    """
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Callsign', 'Mode', 'Band', 'Frequency', 'Grid',
        'Timestamp', 'RST Sent', 'RST Received', 'Notes'
    ])
    
    # Write data rows
    for contact in contacts:
        writer.writerow([
            contact.contact_callsign,
            contact.mode,
            contact.band or '',
            contact.frequency or '',
            contact.grid or '',
            contact.timestamp.isoformat() if contact.timestamp else '',
            contact.signal_report_sent or '',
            contact.signal_report_rcvd or '',
            contact.notes or ''
        ])
    
    return output.getvalue()

def export_to_json(contacts):
    """
    Export contacts to JSON format.
    
    Args:
        contacts: List of ContactLog objects
        
    Returns:
        str: JSON formatted string
    """
    data = [contact.to_dict() for contact in contacts]
    return json.dumps(data, indent=2)

def export_to_adif(contacts):
    """
    Export contacts to ADIF format.
    
    ADIF (Amateur Data Interchange Format) is the standard format
    for ham radio contact logs.
    
    Args:
        contacts: List of ContactLog objects
        
    Returns:
        str: ADIF formatted string
    """
    output = []
    
    # ADIF header
    output.append("ADIF Export from Ham Radio App")
    output.append(f"<ADIF_VER:5>3.1.4")
    output.append(f"<PROGRAMID:13>HamRadioApp")
    output.append(f"<PROGRAMVERSION:5>1.0.0")
    output.append(f"<EOH>\n")
    
    # ADIF records
    for contact in contacts:
        record = []
        
        # Callsign
        record.append(f"<CALL:{len(contact.contact_callsign)}>{contact.contact_callsign}")
        
        # Mode
        record.append(f"<MODE:{len(contact.mode)}>{contact.mode}")
        
        # Band
        if contact.band:
            record.append(f"<BAND:{len(contact.band)}>{contact.band}")
        
        # Frequency
        if contact.frequency:
            freq_str = str(contact.frequency)
            record.append(f"<FREQ:{len(freq_str)}>{freq_str}")
        
        # Grid
        if contact.grid:
            record.append(f"<GRIDSQUARE:{len(contact.grid)}>{contact.grid}")
        
        # Date and Time
        if contact.timestamp:
            qso_date = contact.timestamp.strftime("%Y%m%d")
            qso_time = contact.timestamp.strftime("%H%M%S")
            record.append(f"<QSO_DATE:8>{qso_date}")
            record.append(f"<TIME_ON:6>{qso_time}")
        
        # Signal reports
        if contact.signal_report_sent:
            record.append(f"<RST_SENT:{len(contact.signal_report_sent)}>{contact.signal_report_sent}")
        
        if contact.signal_report_rcvd:
            record.append(f"<RST_RCVD:{len(contact.signal_report_rcvd)}>{contact.signal_report_rcvd}")
        
        # Notes
        if contact.notes:
            record.append(f"<COMMENT:{len(contact.notes)}>{contact.notes}")
        
        # End of record
        record.append("<EOR>\n")
        
        output.append(" ".join(record))
    
    return "\n".join(output)

def get_export_function(format_type):
    """
    Get export function for specified format.
    
    Args:
        format_type: Export format ('csv', 'json', 'adif')
        
    Returns:
        function: Export function or None
    """
    formats = {
        'csv': export_to_csv,
        'json': export_to_json,
        'adif': export_to_adif
    }
    
    return formats.get(format_type.lower())