"""
Callsign Validator
===================
Validates callsign format and optionally checks the
ISED Canadian operator database.

Qualification Reference (from readme_amat_delim.txt):
    A  Basic qualification
    B  5 WPM Morse code
    C  12 WPM Morse code
    D  Advanced qualification
    E  Basic with Honours
"""

import re


class CallsignValidator:
    """
    Validates amateur radio callsigns.

    Two-level validation:
        1. Regex format check (always performed)
        2. ISED database lookup (Canadian callsigns only,
           when database is populated and validation enabled)
    """

    # General international callsign format regex
    CALLSIGN_REGEX = re.compile(
        r'^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$',
        re.IGNORECASE
    )

    # Canadian callsign prefixes (VE, VA, VY, VO series)
    CANADIAN_PREFIXES = (
        'VE', 'VA', 'VY', 'VO',
        'CF', 'CG', 'CH', 'CI', 'CJ', 'CK',
        'XM', 'XN', 'XO',
    )

    # Qualification code to label mapping
    QUAL_LABELS = {
        'A': 'Basic',
        'B': '5 WPM Morse',
        'C': '12 WPM Morse',
        'D': 'Advanced',
        'E': 'Basic with Honours',
    }

    @classmethod
    def is_valid_format(cls, callsign):
        """
        Validate callsign against regex format.

        Args:
            callsign: Callsign string to validate

        Returns:
            bool: True if format is valid
        """
        if not callsign:
            return False
        return bool(
            cls.CALLSIGN_REGEX.match(
                callsign.upper().strip()
            )
        )

    @classmethod
    def is_canadian(cls, callsign):
        """
        Check if callsign uses a Canadian prefix.

        Args:
            callsign: Callsign to check

        Returns:
            bool: True if callsign is Canadian format
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
        Full callsign validation with optional DB lookup.

        Args:
            callsign: Callsign string to validate
            check_database: Whether to query local ISED DB

        Returns:
            tuple: (is_valid, operator_dict_or_None, error_str)
        """
        # Level 1: Format check
        if not cls.is_valid_format(callsign):
            return (
                False,
                None,
                'Invalid callsign format'
            )

        upper = callsign.upper().strip()

        # Level 2: Database check for Canadian callsigns
        if check_database and cls.is_canadian(upper):
            try:
                from flask import current_app
                callsign_db = current_app.extensions.get(
                    'callsign_db'
                )

                if callsign_db:
                    stats = callsign_db.get_stats()

                    if stats.get('is_populated'):
                        operator = callsign_db.lookup(upper)

                        if operator:
                            return (True, operator, None)
                        else:
                            return (
                                False,
                                None,
                                f'{upper} not found in '
                                f'ISED Canadian database'
                            )
                    else:
                        # DB not populated - pass through
                        return (True, None, None)

            except RuntimeError:
                # Outside Flask context
                return (True, None, None)
            except Exception as e:
                print(f"[Validator] DB check error: {e}")
                # Non-fatal - allow registration
                return (True, None, None)

        return (True, None, None)
