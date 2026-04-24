"""
ISED Amateur Radio Database Downloader
========================================
Downloads and parses the Canadian amateur radio
operators database from ISED.

Source:
    https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip

File Format (from readme_amat_delim.txt):
    Delimiter: semicolon (;)
    Encoding: UTF-8 or Latin-1

    Field order:
        0  Callsign
        1  Given Names
        2  Surname
        3  Street Address
        4  City
        5  Province
        6  Postal/ZIP Code
        7  BASIC Qualification        (A) - contains 'A' if held
        8  5WPM Qualification         (B) - contains 'B' if held
        9  12WPM Qualification        (C) - contains 'C' if held
        10 ADVANCED Qualification     (D) - contains 'D' if held
        11 Basic with Honours         (E) - contains 'E' if held
        12 Club Name (field 1)
        13 Club Name (field 2)
        14 Club Address
        15 Club City
        16 Club Province
        17 Club Postal/ZIP Code

Qualification presence:
    The qualification fields (positions 7-11) contain the
    single letter code (A, B, C, D, or E) if the operator
    holds that qualification, or are empty/blank if not held.

    Example record (individual):
        VE3ABC;John;SMITH;123 Main St;Toronto;ON;M5V1A1;A;;D;;;;;;;

    Example record (club):
        VE3XYZ;;;123 Club St;Ottawa;ON;K1A0A1;A;;D;;A;Toronto Radio Club;TARC;
        123 Club St;Ottawa;ON;K1A0A1

Threading:
    Download runs in a background thread to avoid
    blocking the Flask request handler. Progress is
    tracked in _download_state and polled via API.
"""

import io
import os
import csv
import time
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


# -------------------------------------------------------------------
# Field position constants (matching readme_amat_delim.txt)
# -------------------------------------------------------------------
FIELD_CALLSIGN = 0
FIELD_GIVEN_NAMES = 1
FIELD_SURNAME = 2
FIELD_STREET = 3
FIELD_CITY = 4
FIELD_PROVINCE = 5
FIELD_POSTAL = 6
FIELD_QUAL_A = 7      # Basic
FIELD_QUAL_B = 8      # 5 WPM Morse
FIELD_QUAL_C = 9      # 12 WPM Morse
FIELD_QUAL_D = 10     # Advanced
FIELD_QUAL_E = 11     # Basic with Honours
FIELD_CLUB_NAME_1 = 12
FIELD_CLUB_NAME_2 = 13
FIELD_CLUB_ADDRESS = 14
FIELD_CLUB_CITY = 15
FIELD_CLUB_PROVINCE = 16
FIELD_CLUB_POSTAL = 17

# Minimum number of fields expected per record
MIN_FIELDS = 12

# Semicolon delimiter as defined in readme_amat_delim.txt
DELIMITER = ';'


class CallsignDatabaseDownloader:
    """
    Downloads and imports the ISED amateur radio database.

    Uses the exact semicolon-delimited format described
    in readme_amat_delim.txt with qualification codes
    A through E.
    """

    # Official ISED download URL
    DOWNLOAD_URL = (
        'https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip'
    )

    # ZIP internal filename
    DATA_FILENAME = 'amateur_delim.txt'

    # Database insert batch size for performance
    BATCH_SIZE = 500

    def __init__(self):
        """Initialise downloader with progress state."""
        self._download_state = {
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

    def get_state(self):
        """
        Get current download state (thread-safe).

        Returns:
            dict: Copy of current download state
        """
        with self._lock:
            return dict(self._download_state)

    def _set_state(self, **kwargs):
        """
        Update download state (thread-safe).

        Args:
            **kwargs: State fields to update
        """
        with self._lock:
            self._download_state.update(kwargs)

    def is_running(self):
        """
        Check if a download is in progress.

        Returns:
            bool: True if download thread is alive
        """
        return (
            self._thread is not None and
            self._thread.is_alive()
        )

    def start_download(self, app):
        """
        Start database download in a background thread.

        Args:
            app: Flask app instance (for app context)

        Returns:
            bool: True if started, False if already running
        """
        if self.is_running():
            return False

        self._set_state(
            status='starting',
            progress=0,
            message='Starting download...',
            records_imported=0,
            total_records=0,
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            error=None
        )

        self._thread = threading.Thread(
            target=self._worker,
            args=(app,),
            daemon=True,
            name='ised-db-downloader'
        )
        self._thread.start()
        return True

    def _worker(self, app):
        """
        Background worker with Flask application context.

        Args:
            app: Flask application instance
        """
        with app.app_context():
            try:
                self._run_download()
            except Exception as e:
                print(f"[CallsignDB] Worker error: {e}")
                traceback.print_exc()
                self._set_state(
                    status='error',
                    error=str(e),
                    message=f'Unexpected error: {e}'
                )

    def _run_download(self):
        """
        Execute the full download-parse-import cycle.

        Steps:
            1. Download ZIP file from ISED
            2. Extract and decode text file
            3. Parse semicolon-delimited records
            4. Validate and import to SQLite in batches
            5. Update DatabaseMeta with statistics
        """
        from callsign_db.models import DatabaseMeta
        from models import db

        # -----------------------------------------------------------
        # Step 1: Download the ZIP archive
        # -----------------------------------------------------------
        print(
            f"[CallsignDB] Downloading: {self.DOWNLOAD_URL}"
        )
        self._set_state(
            status='downloading',
            progress=5,
            message='Connecting to ISED Canada...'
        )

        zip_bytes = self._download_zip()

        if not zip_bytes:
            self._set_state(
                status='error',
                error='Download failed',
                message=(
                    'Could not download database. '
                    'Check network connection.'
                )
            )
            return

        size_kb = len(zip_bytes) / 1024
        print(f"[CallsignDB] Downloaded {size_kb:.0f} KB")

        self._set_state(
            progress=25,
            message=f'Downloaded {size_kb:.0f} KB. Extracting...'
        )

        # -----------------------------------------------------------
        # Step 2: Extract semicolon-delimited text from ZIP
        # -----------------------------------------------------------
        self._set_state(
            status='parsing',
            progress=30,
            message='Extracting archive...'
        )

        try:
            raw_text = self._extract_text(zip_bytes)
        except Exception as e:
            self._set_state(
                status='error',
                error=str(e),
                message=f'Extraction failed: {e}'
            )
            return

        # -----------------------------------------------------------
        # Step 3: Parse semicolon-delimited records
        # -----------------------------------------------------------
        self._set_state(
            progress=35,
            message='Parsing operator records...'
        )

        records = self._parse_semicolon_file(raw_text)

        if not records:
            self._set_state(
                status='error',
                error='No records parsed',
                message=(
                    'No valid records found. '
                    'File format may have changed.'
                )
            )
            return

        total = len(records)
        print(f"[CallsignDB] Parsed {total:,} records")

        self._set_state(
            status='importing',
            progress=45,
            total_records=total,
            message=f'Importing {total:,} operators...'
        )

        # -----------------------------------------------------------
        # Step 4: Import records to database
        # -----------------------------------------------------------
        imported = self._import_to_database(records, db)

        # -----------------------------------------------------------
        # Step 5: Update metadata
        # -----------------------------------------------------------
        checksum = hashlib.md5(zip_bytes).hexdigest()
        now = datetime.utcnow().isoformat()

        DatabaseMeta.set('last_updated', now)
        DatabaseMeta.set('record_count', str(imported))
        DatabaseMeta.set('checksum', checksum)
        DatabaseMeta.set('source_url', self.DOWNLOAD_URL)
        DatabaseMeta.set('format', 'semicolon_delimited_v1')

        self._set_state(
            status='complete',
            progress=100,
            records_imported=imported,
            completed_at=now,
            message=f'Successfully imported {imported:,} operators'
        )

        print(
            f"[CallsignDB] ✓ Import complete: {imported:,} records"
        )

    def _download_zip(self):
        """
        Download the ISED ZIP file.

        Returns:
            bytes: ZIP file content or None on error
        """
        try:
            if REQUESTS_AVAILABLE:
                response = requests.get(
                    self.DOWNLOAD_URL,
                    timeout=120,
                    stream=True,
                    headers={'User-Agent': 'HamRadioApp/1.0'}
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
                        # Scale progress 5% -> 25%
                        pct = min(
                            24,
                            5 + int(downloaded / 40000)
                        )
                        self._set_state(
                            progress=pct,
                            message=(
                                f'Downloading... '
                                f'{downloaded / 1024:.0f} KB'
                            )
                        )

                return b''.join(chunks)

            else:
                # Fallback: urllib
                import urllib.request
                req = urllib.request.Request(
                    self.DOWNLOAD_URL,
                    headers={'User-Agent': 'HamRadioApp/1.0'}
                )
                with urllib.request.urlopen(
                    req, timeout=120
                ) as resp:
                    return resp.read()

        except Exception as e:
            print(f"[CallsignDB] Download error: {e}")
            return None

    def _extract_text(self, zip_bytes):
        """
        Extract and decode the text file from the ZIP archive.

        Handles varying filenames inside the ZIP.
        Tries UTF-8 encoding first, then Latin-1 fallback.

        Args:
            zip_bytes: Raw ZIP file bytes

        Returns:
            str: Decoded text content

        Raises:
            ValueError: If no suitable file found in ZIP
        """
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            print(f"[CallsignDB] ZIP contains: {names}")

            # Find the data file
            target = None
            for name in names:
                lower = name.lower()
                if (lower.endswith('.txt') or
                        lower.endswith('.csv')) and \
                        'readme' not in lower:
                    target = name
                    break

            # Last resort: any .txt file
            if not target:
                for name in names:
                    if name.lower().endswith('.txt'):
                        target = name
                        break

            if not target:
                raise ValueError(
                    f"No data file found in ZIP. "
                    f"Contents: {names}"
                )

            print(f"[CallsignDB] Extracting: {target}")
            raw_bytes = zf.read(target)

        # Try multiple encodings
        for encoding in ('utf-8', 'latin-1', 'cp1252'):
            try:
                text = raw_bytes.decode(encoding)
                print(
                    f"[CallsignDB] Decoded with {encoding}. "
                    f"Size: {len(text):,} chars"
                )
                return text
            except UnicodeDecodeError:
                continue

        # Final fallback with error replacement
        return raw_bytes.decode('utf-8', errors='replace')

    def _parse_semicolon_file(self, text):
        """
        Parse the ISED semicolon-delimited operator file.

        The file uses semicolons (;) as field separators.
        The first line may or may not be a header row.

        Qualification fields (positions 7-11) contain the
        single letter code if the qualification is held,
        or are empty/blank if not held:
            Position 7  -> 'A' if Basic held, else blank
            Position 8  -> 'B' if 5WPM Morse held, else blank
            Position 9  -> 'C' if 12WPM Morse held, else blank
            Position 10 -> 'D' if Advanced held, else blank
            Position 11 -> 'E' if Basic Honours held, else blank

        Args:
            text: Full text content of the data file

        Returns:
            list: List of raw field lists (one per operator)
        """
        records = []
        lines = text.splitlines()

        if not lines:
            print("[CallsignDB] ERROR: Empty file")
            return records

        print(f"[CallsignDB] Total lines: {len(lines):,}")

        # -----------------------------------------------------------
        # Detect and skip header row
        # The first line may be a header. We detect this by
        # checking if the first field looks like a callsign
        # (starts with a letter/digit, not 'callsign' text).
        # -----------------------------------------------------------
        start_line = 0
        first_line = lines[0].strip()
        first_fields = first_line.split(DELIMITER)

        if first_fields:
            first_field = first_fields[0].strip().upper()
            # Skip header if first field is not a callsign format
            if first_field in (
                'CALLSIGN', 'CALL', 'INDICATIF', 'CALL SIGN'
            ):
                print(
                    f"[CallsignDB] Skipping header: {first_line[:80]}"
                )
                start_line = 1
            else:
                # Validate it looks like a callsign
                import re
                callsign_pattern = re.compile(
                    r'^[A-Z0-9]{2,}[0-9][A-Z]+$',
                    re.IGNORECASE
                )
                if not callsign_pattern.match(first_field):
                    print(
                        f"[CallsignDB] Skipping possible header: "
                        f"{first_line[:80]}"
                    )
                    start_line = 1

        # -----------------------------------------------------------
        # Parse data lines
        # -----------------------------------------------------------
        skipped = 0
        for line_num, line in enumerate(
            lines[start_line:], start=start_line + 1
        ):
            line = line.strip()

            # Skip blank lines
            if not line:
                continue

            # Split on semicolon
            fields = line.split(DELIMITER)

            # Pad to expected length to avoid index errors
            while len(fields) < 18:
                fields.append('')

            # Validate callsign field
            callsign = fields[FIELD_CALLSIGN].strip().upper()
            if not callsign:
                skipped += 1
                continue

            records.append(fields)

        print(
            f"[CallsignDB] Parsed {len(records):,} records "
            f"({skipped} skipped)"
        )
        return records

    def _import_to_database(self, records, db):
        """
        Import parsed records to the SQLite database.

        Clears existing data and bulk-inserts new records
        in batches for performance.

        Args:
            records: List of field lists from parser
            db: Flask-SQLAlchemy db instance

        Returns:
            int: Number of records successfully imported
        """
        from callsign_db.models import CanadianOperator

        total = len(records)
        imported = 0
        batch = []

        # -----------------------------------------------------------
        # Clear existing operator records
        # -----------------------------------------------------------
        print("[CallsignDB] Clearing existing records...")
        try:
            CanadianOperator.query.delete()
            db.session.commit()
            print("[CallsignDB] Existing records cleared")
        except Exception as e:
            print(f"[CallsignDB] Clear error: {e}")
            db.session.rollback()

        # -----------------------------------------------------------
        # Import in batches
        # -----------------------------------------------------------
        for i, fields in enumerate(records):
            operator = self._fields_to_operator(fields)

            if operator is None:
                continue

            batch.append(operator)

            # Commit batch when full
            if len(batch) >= self.BATCH_SIZE:
                try:
                    db.session.bulk_save_objects(batch)
                    db.session.commit()
                    imported += len(batch)
                    batch = []

                    # Update progress: 45% -> 95%
                    progress = 45 + int(
                        (imported / total) * 50
                    )
                    self._set_state(
                        progress=min(progress, 95),
                        records_imported=imported,
                        message=(
                            f'Importing... '
                            f'{imported:,} / {total:,}'
                        )
                    )

                except Exception as e:
                    print(
                        f"[CallsignDB] Batch error at "
                        f"{imported}: {e}"
                    )
                    db.session.rollback()
                    batch = []

        # Commit any remaining records
        if batch:
            try:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                imported += len(batch)
            except Exception as e:
                print(
                    f"[CallsignDB] Final batch error: {e}"
                )
                db.session.rollback()

        print(
            f"[CallsignDB] Import complete: "
            f"{imported:,} records"
        )
        return imported

    def _fields_to_operator(self, fields):
        """
        Convert a parsed field list to a CanadianOperator model.

        Maps field positions to model attributes according
        to the readme_amat_delim.txt specification.

        Qualification detection:
            Each qualification field (positions 7-11)
            contains the single letter code if the
            qualification is held, or is blank/empty.

            field[7] contains 'A' -> Basic held
            field[8] contains 'B' -> 5WPM Morse held
            field[9] contains 'C' -> 12WPM Morse held
            field[10] contains 'D' -> Advanced held
            field[11] contains 'E' -> Honours held

        Args:
            fields: List of string field values

        Returns:
            CanadianOperator: Model instance or None
        """
        from callsign_db.models import CanadianOperator

        # Validate callsign
        callsign = fields[FIELD_CALLSIGN].strip().upper()
        if not callsign:
            return None

        # -----------------------------------------------------------
        # Parse qualification flags from letter codes
        #
        # The field contains the letter if the qualification
        # is held, or is blank/empty if not held.
        # We use strip().upper() to normalise and then check
        # for the expected letter code.
        # -----------------------------------------------------------
        def has_qual(position, expected_letter):
            """
            Check if qualification letter is present in field.

            Args:
                position: Field index in records
                expected_letter: Expected letter code (A-E)

            Returns:
                bool: True if the qualification is held
            """
            if position >= len(fields):
                return False
            value = fields[position].strip().upper()
            # Field contains the letter code if qualification held
            return value == expected_letter

        qual_basic = has_qual(FIELD_QUAL_A, 'A')
        qual_morse_5 = has_qual(FIELD_QUAL_B, 'B')
        qual_morse_12 = has_qual(FIELD_QUAL_C, 'C')
        qual_advanced = has_qual(FIELD_QUAL_D, 'D')
        qual_honours = has_qual(FIELD_QUAL_E, 'E')

        def safe_field(position):
            """
            Safely get a field value or None if empty.

            Args:
                position: Field index

            Returns:
                str or None: Field value or None
            """
            if position >= len(fields):
                return None
            val = fields[position].strip()
            return val if val else None

        return CanadianOperator(
            callsign=callsign,
            given_names=safe_field(FIELD_GIVEN_NAMES),
            surname=safe_field(FIELD_SURNAME),
            street_address=safe_field(FIELD_STREET),
            city=safe_field(FIELD_CITY),
            province=safe_field(FIELD_PROVINCE),
            postal_code=safe_field(FIELD_POSTAL),
            # Qualification booleans
            qual_basic=qual_basic,
            qual_morse_5wpm=qual_morse_5,
            qual_morse_12wpm=qual_morse_12,
            qual_advanced=qual_advanced,
            qual_honours=qual_honours,
            # Club information
            club_name_1=safe_field(FIELD_CLUB_NAME_1),
            club_name_2=safe_field(FIELD_CLUB_NAME_2),
            club_address=safe_field(FIELD_CLUB_ADDRESS),
            club_city=safe_field(FIELD_CLUB_CITY),
            club_province=safe_field(FIELD_CLUB_PROVINCE),
            club_postal_code=safe_field(FIELD_CLUB_POSTAL),
        )
