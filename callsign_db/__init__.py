"""
Canadian Amateur Radio Callsign Database
=========================================
Manages the ISED (Innovation, Science and Economic
Development Canada) amateur radio operators database.

Source:
    https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip

Database Fields (from ISED pipe-delimited file):
    CALLSIGN     - Amateur radio callsign
    SURNAME      - Operator surname
    GIVEN_NAME   - Operator given name(s)
    CITY         - City of licence
    PROVINCE     - Province/Territory code
    POSTAL_CODE  - Postal code
    QUAL_1       - Basic qualification
    QUAL_2       - Advanced qualification (optional)
    QUAL_3       - Basic with Honours (optional)
    QUAL_4       - Additional qualification (optional)
    CLUB_NAME    - Club name (if club callsign)
    CLUB_ADDRESS - Club address (if applicable)
    EXPIRY_DATE  - Licence expiry date

Qualification Codes:
    B   - Basic
    BA  - Basic with Honours
    A   - Advanced
    M   - Morse Code (5 WPM)
    M3  - Morse Code (12 WPM)
    HB  - Basic with Honours (combined)
    HA  - Advanced with Honours

Usage:
    from callsign_db import CallsignDatabase
    db = CallsignDatabase()
    operator = db.lookup('VE3XYZ')

Author: Ham Radio App Team
Version: 1.0.0
"""

from callsign_db.database import CallsignDatabase
from callsign_db.downloader import CallsignDatabaseDownloader
from callsign_db.validator import CallsignValidator

__all__ = [
    'CallsignDatabase',
    'CallsignDatabaseDownloader',
    'CallsignValidator'
]