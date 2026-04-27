"""
ISED Amateur Radio Database Downloader
========================================
Downloads and parses the Canadian amateur radio
operators database from ISED.

Source:
    https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip

File format (from readme_amat_delim.txt):
    Delimiter: semicolon (;)

    Field positions:
        0  Callsign
        1  Given Names
        2  Surname
        3  Street Address
        4  City
        5  Province
        6  Postal/ZIP Code
        7  BASIC Qualification         (A if held, else blank)
        8  5WPM Qualification          (B if held, else blank)
        9  12WPM Qualification         (C if held, else blank)
        10 ADVANCED Qualification      (D if held, else blank)
        11 Basic with Honours          (E if held, else blank)
        12 Club Name (field 1)
        13 Club Name (field 2)
        14 Club Address
        15 Club City
        16 Club Province
        17 Club Postal/ZIP Code

Threading:
    Download runs in a background thread started by
    start_download(). The Flask app is passed to the
    thread and an application context is pushed inside
    the thread so SQLAlchemy sessions work correctly.

    Progress is polled via the /api/db_status endpoint.
"""

import io
import os
import re
import sys
import json
import zipfile
import hashlib
import threading
import traceback
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    import urllib.request
    REQUESTS_AVAILABLE = False

# ------------------------------------------------------------------
# Field index constants from readme_amat_delim.txt
# ------------------------------------------------------------------
FIELD_CALLSIGN = 0
FIELD_GIVEN_NAMES = 1
FIELD_SURNAME = 2
FIELD_STREET = 3
FIELD_CITY = 4
FIELD_PROVINCE = 5
FIELD_POSTAL = 6
FIELD_QUAL_A = 7       # Basic
FIELD_QUAL_B = 8       # 5 WPM Morse
FIELD_QUAL_C = 9       # 12 WPM Morse
FIELD_QUAL_D = 10      # Advanced
FIELD_QUAL_E = 11      # Basic with Honours
FIELD_CLUB_NAME_1 = 12
FIELD_CLUB_NAME_2 = 13
FIELD_CLUB_ADDRESS = 14
FIELD_CLUB_CITY = 15
FIELD_CLUB_PROVINCE = 16
FIELD_CLUB_POSTAL = 17

# Minimum fields expected per data record
MIN_FIELDS = 7

# Semicolon delimiter as per ISED specification
DELIMITER = ';'

# Canadian callsign format for header-row detection
CALLSIGN_PATTERN = re.compile(
    r'^[A-Z0-9]{2,3}[0-9][A-Z]+$',
    re.IGNORECASE
)


class CallsignDatabaseDownloader:
    """
    Downloads and imports the ISED amateur radio database.

    Runs in a background thread. Progress is available
    via get_state() which is polled by the dashboard API.
    """

    # Official ISED download URL
    DOWNLOAD_URL = (
        'https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip'
    )

    # Batch size for SQLAlchemy bulk inserts
    BATCH_SIZE = 500

    def __init__(self):
        """Initialise downloader with idle state."""
        self._state = {
            'status': 'idle',
            'progress': 0,
            'message': '',
            'records_imported': 0,
            'total_records': 0,
            'started_at': None,
            'completed_at': None,
            'error': None,
        }
        self._lock = threading.Lock()
        self._thread = None

    # ----------------------------------------------------------
    # State management (thread-safe)
    # ----------------------------------------------------------

    def get_state(self):
        """
        Get a copy of the current download state.

        Thread-safe. Called by the dashboard API to
        report progress to the browser.

        Returns:
            dict: Copy of current state dictionary
        """
        with self._lock:
            return dict(self._state)

    def _update_state(self, **kwargs):
        """
        Update one or more state fields (thread-safe).

        Args:
            **kwargs: State field names and new values
        """
        with self._lock:
            self._state.update(kwargs)

    def is_running(self):
        """
        Check if a download thread is active.

        Returns:
            bool: True if thread is alive
        """
        return (
            self._thread is not None and
            self._thread.is_alive()
        )

    # ----------------------------------------------------------
    # Thread management
    # ----------------------------------------------------------

    def start_download(self, app):
        """
        Start the database download in a background thread.

        The Flask app instance is passed to the thread
        so it can push an application context and use
        SQLAlchemy inside the thread.

        Args:
            app: Flask application instance

        Returns:
            bool: True if thread started,
                  False if already running
        """
        if self.is_running():
            print("[CallsignDB] Download already running")
            return False

        # Reset state for new download
        self._update_state(
            status='starting',
            progress=0,
            message='Preparing download...',
            records_imported=0,
            total_records=0,
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            error=None,
        )

        # Use _get_current_object() to get the real app
        # instance rather than a proxy when inside a
        # request context
        try:
            real_app = app._get_current_object()
        except AttributeError:
            real_app = app

        self._thread = threading.Thread(
            target=self._thread_worker,
            args=(real_app,),
            daemon=True,
            name='ised-db-downloader'
        )
        self._thread.start()
        print("[CallsignDB] Download thread started")
        return True

    def _thread_worker(self, app):
        """
        Background thread worker function.

        Pushes a Flask application context so that
        SQLAlchemy models and sessions work correctly
        inside the thread.

        Args:
            app: Real Flask application instance
        """
        # Push application context for this thread
        # This is required for all SQLAlchemy operations
        with app.app_context():
            try:
                self._run_download()
            except Exception as e:
                error_msg = str(e)
                print(f"[CallsignDB] Thread error: {e}")
                traceback.print_exc()
                self._update_state(
                    status='error',
                    error=error_msg,
                    message=f'Download failed: {error_msg}'
                )

    # ----------------------------------------------------------
    # Download pipeline
    # ----------------------------------------------------------

    def _run_download(self):
        """
        Execute the complete download-parse-import pipeline.

        Steps:
            1. Download ZIP file from ISED
            2. Extract and decode semicolon-delimited text
            3. Parse records from text
            4. Import records to SQLite in batches
            5. Update DatabaseMeta with statistics
        """
        # -------------------------------------------------------
        # Step 1: Download the ZIP archive
        # -------------------------------------------------------
        print(f"[CallsignDB] Downloading: {self.DOWNLOAD_URL}")

        self._update_state(
            status='downloading',
            progress=5,
            message='Connecting to ISED Canada...'
        )

        zip_bytes = self._download_zip()

        if not zip_bytes:
            self._update_state(
                status='error',
                error='Download failed',
                message=(
                    'Could not download from ISED. '
                    'Check network connection and retry.'
                )
            )
            return

        size_kb = len(zip_bytes) / 1024
        print(f"[CallsignDB] Downloaded {size_kb:.0f} KB")
        self._update_state(
            progress=25,
            message=f'Downloaded {size_kb:.0f} KB. Extracting...'
        )

        # -------------------------------------------------------
        # Step 2: Extract text from ZIP
        # -------------------------------------------------------
        self._update_state(
            status='extracting',
            progress=28,
            message='Extracting ZIP archive...'
        )

        try:
            raw_text = self._extract_text(zip_bytes)
        except Exception as e:
            self._update_state(
                status='error',
                error=str(e),
                message=f'Extraction failed: {e}'
            )
            return

        print(
            f"[CallsignDB] Extracted "
            f"{len(raw_text):,} characters"
        )

        # -------------------------------------------------------
        # Step 3: Parse semicolon-delimited records
        # -------------------------------------------------------
        self._update_state(
            status='parsing',
            progress=32,
            message='Parsing operator records...'
        )

        records = self._parse_records(raw_text)

        if not records:
            self._update_state(
                status='error',
                error='No records parsed',
                message=(
                    'No valid records found in download. '
                    'File format may have changed.'
                )
            )
            return

        total = len(records)
        print(f"[CallsignDB] Parsed {total:,} records")

        self._update_state(
            status='importing',
            progress=40,
            total_records=total,
            message=f'Importing {total:,} operators...'
        )

        # -------------------------------------------------------
        # Step 4: Import to database in batches
        # -------------------------------------------------------
        imported = self._import_records(records)

        # -------------------------------------------------------
        # Step 5: Update metadata
        # -------------------------------------------------------
        try:
            from callsign_db.models import DatabaseMeta

            checksum = hashlib.md5(zip_bytes).hexdigest()
            now = datetime.utcnow().isoformat()

            DatabaseMeta.set('last_updated', now)
            DatabaseMeta.set('record_count', str(imported))
            DatabaseMeta.set('checksum', checksum)
            DatabaseMeta.set('source_url', self.DOWNLOAD_URL)
            DatabaseMeta.set('delimiter', 'semicolon')

            print(f"[CallsignDB] Metadata updated")

        except Exception as e:
            print(f"[CallsignDB] Metadata error: {e}")
            traceback.print_exc()

        # Mark complete
        self._update_state(
            status='complete',
            progress=100,
            records_imported=imported,
            completed_at=datetime.utcnow().isoformat(),
            message=(
                f'Successfully imported '
                f'{imported:,} operators'
            )
        )

        print(
            f"[CallsignDB] ✓ Import complete: "
            f"{imported:,} records"
        )

    # ----------------------------------------------------------
    # Download helper
    # ----------------------------------------------------------

    def _download_zip(self):
        """
        Download the ISED ZIP file.

        Uses requests if available, otherwise urllib.
        Updates progress state during streaming download.

        Returns:
            bytes: ZIP file content or None on error
        """
        headers = {'User-Agent': 'HamRadioApp/1.0 (Linux)'}

        try:
            if REQUESTS_AVAILABLE:
                response = requests.get(
                    self.DOWNLOAD_URL,
                    timeout=120,
                    stream=True,
                    headers=headers
                )
                response.raise_for_status()

                chunks = []
                downloaded = 0

                for chunk in response.iter_content(
                    chunk_size=8192
                ):
                    if chunk:
                        chunks.append(chunk)
                        downloaded += len(chunk)

                        # Scale progress 5% -> 24%
                        pct = min(
                            24,
                            5 + int(downloaded / 50000)
                        )
                        self._update_state(
                            progress=pct,
                            message=(
                                f'Downloading... '
                                f'{downloaded/1024:.0f} KB'
                            )
                        )

                return b''.join(chunks)

            else:
                # Fallback to urllib
                import urllib.request
                req = urllib.request.Request(
                    self.DOWNLOAD_URL,
                    headers=headers
                )
                with urllib.request.urlopen(
                    req, timeout=120
                ) as response:
                    return response.read()

        except Exception as e:
            print(f"[CallsignDB] Download error: {e}")
            return None

    # ----------------------------------------------------------
    # Extraction helper
    # ----------------------------------------------------------

    def _extract_text(self, zip_bytes):
        """
        Extract and decode the text file from the ZIP.

        Handles varying filenames inside the ZIP and
        tries multiple encodings (UTF-8, Latin-1, CP1252).

        Args:
            zip_bytes: Raw bytes of the ZIP archive

        Returns:
            str: Decoded text content

        Raises:
            ValueError: If no suitable file found in ZIP
        """
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            print(f"[CallsignDB] ZIP contents: {names}")

            # Find the data file
            # Exclude readme files
            target = None
            for name in names:
                lower = name.lower()
                if ('readme' not in lower and
                        'read_me' not in lower and
                        (lower.endswith('.txt') or
                         lower.endswith('.csv'))):
                    target = name
                    break

            # Fallback: any .txt file
            if not target:
                for name in names:
                    if name.lower().endswith('.txt'):
                        target = name
                        break

            if not target:
                raise ValueError(
                    f"No data file in ZIP. "
                    f"Contents: {names}"
                )

            print(f"[CallsignDB] Extracting: {target}")
            raw_bytes = zf.read(target)

        # Try encodings in order
        for encoding in ('utf-8', 'latin-1', 'cp1252'):
            try:
                text = raw_bytes.decode(encoding)
                print(
                    f"[CallsignDB] Decoded "
                    f"({encoding}): "
                    f"{len(text):,} chars"
                )
                return text
            except UnicodeDecodeError:
                continue

        # Last resort
        return raw_bytes.decode('utf-8', errors='replace')

    # ----------------------------------------------------------
    # Parsing helper
    # ----------------------------------------------------------

    def _parse_records(self, text):
        """
        Parse semicolon-delimited ISED operator records.

        Detects and skips any header row. Validates that
        each record's first field looks like a callsign.
        Pads short records to the expected field count.

        Args:
            text: Full decoded text of the data file

        Returns:
            list: List of field-value lists,
                  one per valid operator record
        """
        records = []
        lines = text.splitlines()

        if not lines:
            print("[CallsignDB] ERROR: Empty file content")
            return records

        print(f"[CallsignDB] Total lines: {len(lines):,}")

        # Detect header row
        start_line = 0
        first = lines[0].strip()
        if first:
            first_field = first.split(DELIMITER)[0].strip()
            # Header row will not look like a callsign
            if not CALLSIGN_PATTERN.match(first_field):
                print(
                    f"[CallsignDB] Skipping header: "
                    f"{first[:60]}"
                )
                start_line = 1

        # Parse data lines
        skipped = 0
        for line in lines[start_line:]:
            line = line.strip()
            if not line:
                continue

            # Split on semicolon
            fields = line.split(DELIMITER)

            # Pad to expected width
            while len(fields) < 18:
                fields.append('')

            # Validate callsign field
            callsign = fields[FIELD_CALLSIGN].strip().upper()
            if not callsign or not CALLSIGN_PATTERN.match(
                callsign
            ):
                skipped += 1
                continue

            records.append(fields)

        print(
            f"[CallsignDB] Valid records: {len(records):,} "
            f"(skipped {skipped})"
        )
        return records

    # ----------------------------------------------------------
    # Import helper
    # ----------------------------------------------------------

    def _import_records(self, records):
        """
        Import parsed records into the SQLite database.

        Clears the existing table and bulk-inserts new
        records in batches. Updates progress state
        throughout for the polling endpoint.

        Args:
            records: List of field-value lists

        Returns:
            int: Number of records successfully imported
        """
        from callsign_db.models import CanadianOperator
        from models import db

        total = len(records)
        imported = 0
        batch = []

        # Clear existing data
        print("[CallsignDB] Clearing existing records...")
        try:
            CanadianOperator.query.delete()
            db.session.commit()
            print("[CallsignDB] Existing records cleared")
        except Exception as e:
            print(f"[CallsignDB] Clear error: {e}")
            db.session.rollback()

        # Bulk insert in batches
        print("[CallsignDB] Importing records...")

        for i, fields in enumerate(records):
            try:
                operator = self._build_operator(fields)
                if operator is not None:
                    batch.append(operator)
            except Exception as e:
                print(
                    f"[CallsignDB] Build error at "
                    f"record {i}: {e}"
                )
                continue

            # Commit when batch is full
            if len(batch) >= self.BATCH_SIZE:
                try:
                    db.session.bulk_save_objects(batch)
                    db.session.commit()
                    imported += len(batch)
                    batch = []

                    # Update progress: 40% -> 95%
                    progress = 40 + int(
                        (imported / total) * 55
                    )
                    self._update_state(
                        progress=min(progress, 95),
                        records_imported=imported,
                        message=(
                            f'Importing... '
                            f'{imported:,} / {total:,}'
                        )
                    )

                except Exception as e:
                    print(
                        f"[CallsignDB] Batch error "
                        f"at {imported}: {e}"
                    )
                    traceback.print_exc()
                    db.session.rollback()
                    batch = []

        # Commit remaining records
        if batch:
            try:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                imported += len(batch)
                print(
                    f"[CallsignDB] Final batch: "
                    f"{len(batch)} records"
                )
            except Exception as e:
                print(f"[CallsignDB] Final batch error: {e}")
                traceback.print_exc()
                db.session.rollback()

        print(
            f"[CallsignDB] Import complete: "
            f"{imported:,} records"
        )
        return imported

    def _build_operator(self, fields):
        """
        Build a CanadianOperator model from a field list.

        Qualification detection:
            Field position 7  contains 'A' if Basic held
            Field position 8  contains 'B' if 5WPM held
            Field position 9  contains 'C' if 12WPM held
            Field position 10 contains 'D' if Advanced held
            Field position 11 contains 'E' if Honours held

        Args:
            fields: List of string field values,
                    padded to at least 18 elements

        Returns:
            CanadianOperator: Model instance or None if
                              callsign field is empty
        """
        from callsign_db.models import CanadianOperator

        callsign = fields[FIELD_CALLSIGN].strip().upper()
        if not callsign:
            return None

        def safe(pos):
            """Return stripped field value or None."""
            if pos >= len(fields):
                return None
            val = fields[pos].strip()
            return val if val else None

        def has_qual(pos, letter):
            """
            Check qualification field for expected letter.

            Returns True if the field at position pos
            contains the single letter code that indicates
            the qualification is held.

            Args:
                pos: Field position index
                letter: Expected letter code (A-E)

            Returns:
                bool: True if qualification is held
            """
            if pos >= len(fields):
                return False
            return fields[pos].strip().upper() == letter

        return CanadianOperator(
            callsign=callsign,
            given_names=safe(FIELD_GIVEN_NAMES),
            surname=safe(FIELD_SURNAME),
            street_address=safe(FIELD_STREET),
            city=safe(FIELD_CITY),
            province=safe(FIELD_PROVINCE),
            postal_code=safe(FIELD_POSTAL),
            qual_basic=has_qual(FIELD_QUAL_A, 'A'),
            qual_morse_5wpm=has_qual(FIELD_QUAL_B, 'B'),
            qual_morse_12wpm=has_qual(FIELD_QUAL_C, 'C'),
            qual_advanced=has_qual(FIELD_QUAL_D, 'D'),
            qual_honours=has_qual(FIELD_QUAL_E, 'E'),
            club_name_1=safe(FIELD_CLUB_NAME_1),
            club_name_2=safe(FIELD_CLUB_NAME_2),
            club_address=safe(FIELD_CLUB_ADDRESS),
            club_city=safe(FIELD_CLUB_CITY),
            club_province=safe(FIELD_CLUB_PROVINCE),
            club_postal_code=safe(FIELD_CLUB_POSTAL),
        )
