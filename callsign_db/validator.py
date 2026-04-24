"""
Callsign Validator
===================
Validates amateur radio callsigns with optional
lookup against the Canadian ISED database.

Validation Levels:
    1. Format validation (regex) - always performed
    2. Database lookup - performed when database
       is populated and VALIDATE_CALLSIGNS is True

Canadian Callsign Formats:
    VE1-VE9 XXX    - Regular amateur callsigns
    VA1-VA7 XX     - Amateur callsigns (newer series)
    VY0-VY2 XXX    - Northern Canada
    VO1-VO2 XX     - Newfoundland/Labrador
    VE1-VE9 XXXX   - Club or special callsigns
    CG/CF/CH...    - Special event and reciprocal
    XM-XO...       - Experimental

General Callsign Format (international):
    1-3 alphanumeric + digit + 1-4 letters
    e.g., W1AW, VE3XYZ, G4ABC, JA1ABC
"""

import re
from typing import Optional, Tuple


class CallsignValidator:
    """
    Validates amateur radio callsigns.

    Provides format validation via regex and optional
    database validation against the ISED database.
    """

    # General international callsign regex
    # Covers most national formats
    CALLSIGN_REGEX = re.compile(
        r'^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$',
        re.IGNORECASE
    )

    # Canadian callsign prefixes
    CANADIAN_PREFIXES = (
        'VE', 'VA', 'VY', 'VO',
        'VE1', 'VE2', 'VE3', 'VE4', 'VE5',
        'VE6', 'VE7', 'VE8', 'VE9',
        'VA2', 'VA3', 'VA4', 'VA5', 'VA6', 'VA7',
        'VY0', 'VY1', 'VY2',
        'VO1', 'VO2',
        'CF', 'CG', 'CH', 'CI', 'CJ', 'CK',
        'XM', 'XN', 'XO',
    )

    @classmethod
    def is_valid_format(cls, callsign):
        """
        Validate callsign format using regex.

        Args:
            callsign: Callsign string to validate

        Returns:
            bool: True if format is valid
        """
        if not callsign:
            return False
        return bool(
            cls.CALLSIGN_REGEX.match(callsign.upper().strip())
        )

    @classmethod
    def is_canadian(cls, callsign):
        """
        Check if a callsign appears to be Canadian.

        Uses prefix matching to determine if the callsign
        is likely a Canadian amateur radio callsign.

        Args:
            callsign: Callsign to check

        Returns:
            bool: True if callsign starts with Canadian prefix
        """
        if not callsign:
            return False

        upper = callsign.upper().strip()
        return any(
            upper.startswith(prefix)
            for prefix in cls.CANADIAN_PREFIXES
        )

    @classmethod
    def validate(cls, callsign, check_database=True):
        """
        Validate a callsign with optional database lookup.

        Performs format validation first. If the callsign
        is valid and database check is requested, queries
        the local ISED database.

        Args:
            callsign: Callsign to validate
            check_database: Whether to check the database

        Returns:
            tuple: (is_valid, operator_data, error_message)
                - is_valid: True if callsign is valid
                - operator_data: Dict from DB or None
                - error_message: Error string or None
        """
        # Step 1: Format validation
        if not cls.is_valid_format(callsign):
            return (
                False,
                None,
                'Invalid callsign format'
            )

        upper_callsign = callsign.upper().strip()

        # Step 2: Database lookup (if enabled and Canadian)
        if check_database and cls.is_canadian(upper_callsign):
            try:
                from flask import current_app
                callsign_db = current_app.extensions.get(
                    'callsign_db'
                )

                if callsign_db:
                    stats = callsign_db.get_stats()

                    # Only check DB if it has records
                    if stats.get('is_populated'):
                        operator = callsign_db.lookup(
                            upper_callsign
                        )

                        if operator:
                            return (True, operator, None)
                        else:
                            # Callsign not in database
                            return (
                                False,
                                None,
                                f'{upper_callsign} not found '
                                f'in Canadian operator database'
                            )
                    else:
                        # DB empty - skip DB check
                        return (True, None, None)

            except RuntimeError:
                # Outside app context - skip DB check
                return (True, None, None)
            except Exception as e:
                print(f"[Validator] DB error: {e}")
                # Don't block on DB error
                return (True, None, None)

        # Valid format, not checking DB
        return (True, None, None)