"""
Callsign Database Manager
==========================
High-level interface for the Canadian amateur radio
operator database.

Provides:
    - Callsign lookup (single and bulk)
    - Database statistics
    - Database status checking
    - Integration with the downloader

Usage:
    db = CallsignDatabase(app)
    operator = db.lookup('VE3XYZ')
    if operator:
        print(operator['full_name'])
        print(operator['qualifications'])
"""

from datetime import datetime


class CallsignDatabase:
    """
    Interface for Canadian amateur radio operator database.

    Wraps the SQLAlchemy model with a clean API for
    lookups and statistics.
    """

    def __init__(self, app=None):
        """
        Initialise the database interface.

        Args:
            app: Flask application instance (optional,
                 can be set later via init_app)
        """
        self.app = app
        self._downloader = None

        if app:
            self.init_app(app)

    def init_app(self, app):
        """
        Initialise with Flask application.

        Registers downloader and creates tables.

        Args:
            app: Flask application instance
        """
        from callsign_db.downloader import (
            CallsignDatabaseDownloader
        )

        self.app = app
        self._downloader = CallsignDatabaseDownloader()

        # Store reference in app extensions
        app.extensions['callsign_db'] = self

    def lookup(self, callsign):
        """
        Look up a callsign in the local database.

        Args:
            callsign: Callsign to look up (case-insensitive)

        Returns:
            dict: Operator data or None if not found
        """
        from callsign_db.models import CanadianOperator

        if not callsign:
            return None

        try:
            operator = CanadianOperator.query.filter_by(
                callsign=callsign.upper().strip()
            ).first()

            return operator.to_dict() if operator else None

        except Exception as e:
            print(f"[CallsignDB] Lookup error: {e}")
            return None

    def lookup_partial(self, partial_callsign, limit=10):
        """
        Search for callsigns matching a partial string.

        Useful for autocomplete and validation suggestions.

        Args:
            partial_callsign: Partial callsign to search
            limit: Maximum results to return

        Returns:
            list: List of matching operator dicts
        """
        from callsign_db.models import CanadianOperator

        if not partial_callsign:
            return []

        try:
            results = CanadianOperator.query.filter(
                CanadianOperator.callsign.like(
                    f"{partial_callsign.upper().strip()}%"
                )
            ).limit(limit).all()

            return [r.to_dict() for r in results]

        except Exception as e:
            print(f"[CallsignDB] Partial lookup error: {e}")
            return []

    def exists(self, callsign):
        """
        Check if a callsign exists in the database.

        Faster than lookup() as it only checks existence.

        Args:
            callsign: Callsign to check

        Returns:
            bool: True if callsign exists
        """
        from callsign_db.models import CanadianOperator

        if not callsign:
            return False

        try:
            return db.session.query(
                CanadianOperator.query.filter_by(
                    callsign=callsign.upper().strip()
                ).exists()
            ).scalar()

        except Exception as e:
            print(f"[CallsignDB] Exists check error: {e}")
            # Return True on error to avoid blocking registration
            return True

    def get_stats(self):
        """
        Get database statistics.

        Returns:
            dict: Statistics including record count,
                  last update time, and status
        """
        from callsign_db.models import DatabaseMeta

        try:
            from callsign_db.models import CanadianOperator
            record_count = CanadianOperator.query.count()
        except Exception:
            record_count = 0

        last_updated = DatabaseMeta.get('last_updated', None)
        source_url = DatabaseMeta.get(
            'source_url', 'https://apc-cap.ic.gc.ca'
        )

        # Format last updated for display
        last_updated_display = 'Never'
        last_updated_age = None

        if last_updated:
            try:
                dt = datetime.fromisoformat(last_updated)
                last_updated_display = dt.strftime(
                    '%Y-%m-%d %H:%M UTC'
                )
                age_days = (datetime.utcnow() - dt).days
                last_updated_age = age_days
            except Exception:
                last_updated_display = last_updated

        return {
            'record_count': record_count,
            'last_updated': last_updated,
            'last_updated_display': last_updated_display,
            'last_updated_age_days': last_updated_age,
            'source_url': source_url,
            'is_populated': record_count > 0,
            'needs_update': (
                last_updated_age is None or
                last_updated_age > 90
            ),
            'downloader_state': (
                self._downloader.get_state()
                if self._downloader else {}
            )
        }

    def start_update(self, app):
        """
        Start a background database update.

        Args:
            app: Flask application instance

        Returns:
            bool: True if update started
        """
        if not self._downloader:
            from callsign_db.downloader import (
                CallsignDatabaseDownloader
            )
            self._downloader = CallsignDatabaseDownloader()

        return self._downloader.start_download(app)

    def get_download_state(self):
        """
        Get current download progress state.

        Returns:
            dict: Download progress information
        """
        if not self._downloader:
            return {'status': 'idle', 'progress': 0}
        return self._downloader.get_state()

    def is_downloading(self):
        """
        Check if a download is in progress.

        Returns:
            bool: True if downloading
        """
        return (
            self._downloader is not None and
            self._downloader.is_running()
        )