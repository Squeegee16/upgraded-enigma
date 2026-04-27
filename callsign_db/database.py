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
    Interface for the ISED Canadian callsign database.

    Provides lookup, search, statistics, and update
    management via the downloader.
    """

    def __init__(self, app=None):
        """
        Initialise the database interface.

        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        self._downloader = None

        if app:
            self.init_app(app)

    def init_app(self, app):
        """
        Initialise with a Flask application instance.

        Stores the database reference in app.extensions
        and creates the downloader instance.

        Args:
            app: Flask application instance
        """
        from callsign_db.downloader import (
            CallsignDatabaseDownloader
        )

        self.app = app
        self._downloader = CallsignDatabaseDownloader()

        # Register in app extensions for access
        # from anywhere that has the app context
        app.extensions['callsign_db'] = self

        print("[CallsignDB] ✓ Database interface registered")

    def lookup(self, callsign):
        """
        Look up a callsign in the local ISED database.

        Args:
            callsign: Callsign string (case-insensitive)

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

    def lookup_partial(self, partial, limit=10):
        """
        Search for callsigns matching a partial string.

        Used for autocomplete and quick search.

        Args:
            partial: Partial callsign string
            limit: Maximum results to return

        Returns:
            list: List of matching operator dicts
        """
        from callsign_db.models import CanadianOperator

        if not partial or len(partial) < 2:
            return []

        try:
            results = CanadianOperator.query.filter(
                CanadianOperator.callsign.like(
                    f"{partial.upper().strip()}%"
                )
            ).limit(limit).all()
            return [r.to_dict() for r in results]
        except Exception as e:
            print(f"[CallsignDB] Partial lookup error: {e}")
            return []

    def get_stats(self):
        """
        Get database statistics and status information.

        Returns:
            dict: Statistics including record count,
                  last update time, and download state
        """
        from callsign_db.models import DatabaseMeta

        # Get record count
        try:
            from callsign_db.models import CanadianOperator
            record_count = CanadianOperator.query.count()
        except Exception:
            record_count = 0

        # Get metadata
        last_updated = DatabaseMeta.get('last_updated')
        source_url = DatabaseMeta.get(
            'source_url',
            'https://apc-cap.ic.gc.ca'
        )

        # Format last updated display
        last_updated_display = 'Never'
        last_updated_age = None

        if last_updated:
            try:
                dt = datetime.fromisoformat(last_updated)
                last_updated_display = dt.strftime(
                    '%Y-%m-%d %H:%M UTC'
                )
                last_updated_age = (
                    datetime.utcnow() - dt
                ).days
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
                if self._downloader else {
                    'status': 'idle',
                    'progress': 0
                }
            )
        }

    def start_update(self, app):
        """
        Start a background database update.

        Creates a new downloader if needed and starts
        the download thread.

        Args:
            app: Flask application instance

        Returns:
            bool: True if update thread started
        """
        if not self._downloader:
            from callsign_db.downloader import (
                CallsignDatabaseDownloader
            )
            self._downloader = CallsignDatabaseDownloader()

        print("[CallsignDB] Starting database update...")
        return self._downloader.start_download(app)

    def get_download_state(self):
        """
        Get current download progress state.

        Returns:
            dict: Current download state
        """
        if not self._downloader:
            return {
                'status': 'idle',
                'progress': 0,
                'message': 'No downloader initialised'
            }
        return self._downloader.get_state()

    def is_downloading(self):
        """
        Check if a download is in progress.

        Returns:
            bool: True if download thread is active
        """
        return (
            self._downloader is not None and
            self._downloader.is_running()
        )
