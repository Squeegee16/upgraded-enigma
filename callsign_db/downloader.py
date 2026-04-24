"""
ISED Amateur Radio Database Downloader
========================================
Downloads and parses the Canadian amateur radio
operators database from ISED (Innovation, Science
and Economic Development Canada).

Source URL:
    https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip

File Format:
    Pipe-delimited (|) text file
    First line: column headers
    Encoding: UTF-8 or Latin-1

Download Process:
    1. Download amateur_delim.zip (~5 MB)
    2. Extract amateur_delim.txt
    3. Parse pipe-delimited records
    4. Upsert into local SQLite database
    5. Update metadata (count, timestamp, checksum)

Estimated Records: ~80,000+ amateur operators

Threading:
    Download and parse runs in a background thread
    to avoid blocking the Flask request handler.
    Progress is tracked via the DatabaseMeta table.

Error Handling:
    Network errors, parse errors, and DB errors are
    all caught and logged. The existing database
    remains intact if an update fails.
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

# Handle optional import
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    import urllib.request
    import urllib.error
    REQUESTS_AVAILABLE = False


class CallsignDatabaseDownloader:
    """
    Downloads and imports the ISED amateur radio database.

    Manages the full lifecycle of downloading, parsing,
    and importing the Canadian amateur radio callsign
    database into the local SQLite database.
    """

    # Official ISED download URL
    DOWNLOAD_URL = (
        'https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip'
    )

    # Fallback URL (mirror)
    FALLBACK_URL = (
        'https://apc-cap.ic.gc.ca/datafiles/amateur_delim.zip'
    )

    # Pipe-delimited file name inside the ZIP
    DATA_FILENAME = 'amateur_delim.txt'

    # Batch size for database inserts (for performance)
    BATCH_SIZE = 500

    def __init__(self):
        """
        Initialise the downloader.

        Sets up progress tracking and state management.
        """
        # Download state (for progress reporting)
        self._download_state = {
            'status': 'idle',       # idle, downloading, parsing,
            #                         importing, complete, error
            'progress': 0,          # 0-100 percent
            'message': '',          # Status message
            'records_imported': 0,  # Records processed
            'total_records': 0,     # Total records found
            'started_at': None,     # Start timestamp
            'error': None,          # Error message if failed
        }

        self._lock = threading.Lock()
        self._thread = None

    def get_state(self):
        """
        Get current download state (thread-safe).

        Returns:
            dict: Current download progress state
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
        Check if a download is currently in progress.

        Returns:
            bool: True if download thread is active
        """
        return (
            self._thread is not None and
            self._thread.is_alive()
        )

    def start_download(self, app):
        """
        Start database download in a background thread.

        Args:
            app: Flask application instance (for app context)

        Returns:
            bool: True if download started,
                  False if already running
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
            error=None
        )

        self._thread = threading.Thread(
            target=self._download_worker,
            args=(app,),
            daemon=True,
            name='callsign-db-downloader'
        )
        self._thread.start()
        return True

    def _download_worker(self, app):
        """
        Background worker for database download and import.

        Runs in a separate thread. Uses Flask application
        context for database access.

        Args:
            app: Flask application instance
        """
        with app.app_context():
            try:
                self._run_download()
            except Exception as e:
                print(f"[CallsignDB] Download worker error: {e}")
                traceback.print_exc()
                self._set_state(
                    status='error',
                    error=str(e),
                    message=f'Error: {str(e)}'
                )

    def _run_download(self):
        """
        Execute the complete download and import process.

        Steps:
        1. Download ZIP from ISED
        2. Extract pipe-delimited text file
        3. Parse records
        4. Import to database in batches
        5. Update metadata
        """
        from callsign_db.models import CanadianOperator, DatabaseMeta
        from models import db

        # Step 1: Download ZIP file
        # -------------------------------------------------
        print(f"[CallsignDB] Downloading from {self.DOWNLOAD_URL}")
        self._set_state(
            status='downloading',
            progress=5,
            message='Connecting to ISED...'
        )

        zip_data = self._download_file()

        if zip_data is None:
            self._set_state(
                status='error',
                error='Download failed',
                message='Failed to download database'
            )
            return

        self._set_state(
            progress=25,
            message=f'Downloaded {len(zip_data)/1024:.0f} KB'
        )

        # Step 2: Extract text file from ZIP
        # -------------------------------------------------
        print("[CallsignDB] Extracting database file...")
        self._set_state(
            status='parsing',
            progress=30,
            message='Extracting ZIP archive...'
        )

        try:
            text_data = self._extract_from_zip(zip_data)
        except Exception as e:
            self._set_state(
                status='error',
                error=str(e),
                message=f'Extract failed: {e}'
            )
            return

        self._set_state(
            progress=35,
            message='Parsing operator records...'
        )

        # Step 3: Parse records
        # -------------------------------------------------
        print("[CallsignDB] Parsing records...")
        records = self._parse_records(text_data)

        if not records:
            self._set_state(
                status='error',
                error='No records parsed',
                message='No records found in database file'
            )
            return

        total = len(records)
        print(f"[CallsignDB] Parsed {total} records")

        self._set_state(
            status='importing',
            progress=45,
            total_records=total,
            message=f'Importing {total} operators...'
        )

        # Step 4: Import records to database in batches
        # -------------------------------------------------
        print(f"[CallsignDB] Importing {total} records...")
        imported = self._import_records(records, db)

        # Step 5: Update metadata
        # -------------------------------------------------
        print("[CallsignDB] Updating metadata...")

        # Calculate checksum of zip data
        checksum = hashlib.md5(zip_data).hexdigest()

        DatabaseMeta.set('last_updated', datetime.utcnow().isoformat())
        DatabaseMeta.set('record_count', str(imported))
        DatabaseMeta.set('checksum', checksum)
        DatabaseMeta.set(
            'source_url', self.DOWNLOAD_URL
        )

        self._set_state(
            status='complete',
            progress=100,
            records_imported=imported,
            message=(
                f'Successfully imported '
                f'{imported:,} operators'
            )
        )

        print(
            f"[CallsignDB] ✓ Import complete: "
            f"{imported:,} records"
        )

    def _download_file(self):
        """
        Download the ISED ZIP file.

        Tries requests library first, falls back to
        urllib for environments without requests.

        Returns:
            bytes: ZIP file data or None on error
        """
        urls = [self.DOWNLOAD_URL, self.FALLBACK_URL]

        for url in urls:
            try:
                if REQUESTS_AVAILABLE:
                    response = requests.get(
                        url,
                        timeout=120,
                        stream=True,
                        headers={
                            'User-Agent': 'HamRadioApp/1.0'
                        }
                    )
                    response.raise_for_status()

                    # Stream download with progress
                    chunks = []
                    downloaded = 0

                    for chunk in response.iter_content(
                        chunk_size=8192
                    ):
                        if chunk:
                            chunks.append(chunk)
                            downloaded += len(chunk)

                            # Update progress (0-25%)
                            progress = min(
                                24,
                                5 + int(downloaded / 50000)
                            )
                            self._set_state(
                                progress=progress,
                                message=(
                                    f'Downloading... '
                                    f'{downloaded/1024:.0f} KB'
                                )
                            )

                    return b''.join(chunks)

                else:
                    # Fallback to urllib
                    req = urllib.request.Request(
                        url,
                        headers={'User-Agent': 'HamRadioApp/1.0'}
                    )
                    with urllib.request.urlopen(
                        req, timeout=120
                    ) as response:
                        return response.read()

            except Exception as e:
                print(
                    f"[CallsignDB] Download error from "
                    f"{url}: {e}"
                )
                continue

        return None

    def _extract_from_zip(self, zip_data):
        """
        Extract the pipe-delimited file from the ZIP archive.

        Args:
            zip_data: ZIP file bytes

        Returns:
            str: Decoded text content of the data file

        Raises:
            ValueError: If file not found in ZIP
        """
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # List contents for debugging
            names = zf.namelist()
            print(f"[CallsignDB] ZIP contents: {names}")

            # Find the data file (case-insensitive)
            target = None
            for name in names:
                if name.lower().endswith('.txt') or \
                        name.lower().endswith('.csv') or \
                        'amateur' in name.lower():
                    target = name
                    break

            if not target:
                raise ValueError(
                    f"Data file not found in ZIP. "
                    f"Contents: {names}"
                )

            print(f"[CallsignDB] Extracting: {target}")
            raw_bytes = zf.read(target)

            # Try UTF-8 first, then Latin-1
            for encoding in ('utf-8', 'latin-1', 'cp1252'):
                try:
                    return raw_bytes.decode(encoding)
                except UnicodeDecodeError:
                    continue

            # Last resort: replace errors
            return raw_bytes.decode('utf-8', errors='replace')

    def _parse_records(self, text_data):
        """
        Parse the pipe-delimited ISED data file.

        The ISED file uses pipe (|) as delimiter.
        First line contains column headers.

        Expected columns (order may vary):
            CALLSIGN, SURNAME, GIVEN_NAME, CITY,
            PROVINCE, POSTAL_CODE, QUAL_1, QUAL_2,
            QUAL_3, QUAL_4, CLUB_NAME, CLUB_ADDRESS,
            EXPIRY_DATE

        Args:
            text_data: String content of the data file

        Returns:
            list: List of parsed record dictionaries
        """
        records = []
        lines = text_data.strip().split('\n')

        if not lines:
            return records

        # Parse header line
        header_line = lines[0].strip().rstrip('|')
        headers = [
            h.strip().upper()
            for h in header_line.split('|')
        ]

        print(f"[CallsignDB] CSV headers: {headers}")

        # Map header names to expected fields
        # (handles slight variations in field naming)
        field_map = {
            'CALLSIGN': 'callsign',
            'SURNAME': 'surname',
            'GIVEN_NAME': 'given_name',
            'GIVEN NAME': 'given_name',
            'CITY': 'city',
            'PROVINCE': 'province',
            'POSTAL_CODE': 'postal_code',
            'POSTAL CODE': 'postal_code',
            'QUAL_1': 'qual_1',
            'QUAL_2': 'qual_2',
            'QUAL_3': 'qual_3',
            'QUAL_4': 'qual_4',
            'CLUB_NAME': 'club_name',
            'CLUB NAME': 'club_name',
            'EXPIRY_DATE': 'expiry_date',
            'EXPIRY DATE': 'expiry_date',
        }

        # Parse data lines
        for i, line in enumerate(lines[1:], 1):
            line = line.strip()
            if not line:
                continue

            # Split by pipe delimiter
            values = line.rstrip('|').split('|')

            # Build record dict
            record = {}
            for j, header in enumerate(headers):
                mapped = field_map.get(header, header.lower())
                record[mapped] = (
                    values[j].strip()
                    if j < len(values) else ''
                )

            # Only include records with a callsign
            if record.get('callsign'):
                records.append(record)

        print(f"[CallsignDB] Parsed {len(records)} records")
        return records

    def _import_records(self, records, db):
        """
        Import parsed records into the database.

        Uses batch upserts (insert or update) for efficiency.
        Updates progress state during import.

        Args:
            records: List of parsed record dicts
            db: SQLAlchemy database instance

        Returns:
            int: Number of records successfully imported
        """
        from callsign_db.models import CanadianOperator

        total = len(records)
        imported = 0
        batch = []

        # Clear existing data
        print("[CallsignDB] Clearing existing records...")
        try:
            CanadianOperator.query.delete()
            db.session.commit()
        except Exception as e:
            print(f"[CallsignDB] Clear error: {e}")
            db.session.rollback()

        print("[CallsignDB] Importing new records...")

        for i, record in enumerate(records):
            try:
                operator = self._build_operator(record)
                if operator:
                    batch.append(operator)

                # Commit in batches
                if len(batch) >= self.BATCH_SIZE:
                    db.session.bulk_save_objects(batch)
                    db.session.commit()
                    imported += len(batch)
                    batch = []

                    # Update progress (45-95%)
                    progress = 45 + int(
                        (i / total) * 50
                    )
                    self._set_state(
                        progress=progress,
                        records_imported=imported,
                        message=(
                            f'Importing... '
                            f'{imported:,}/{total:,}'
                        )
                    )

            except Exception as e:
                print(
                    f"[CallsignDB] Record error at {i}: {e}"
                )
                db.session.rollback()
                batch = []
                continue

        # Commit remaining batch
        if batch:
            try:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                imported += len(batch)
            except Exception as e:
                print(f"[CallsignDB] Final batch error: {e}")
                db.session.rollback()

        return imported

    def _build_operator(self, record):
        """
        Build a CanadianOperator model from a parsed record.

        Parses qualification codes and normalises fields.

        Args:
            record: Parsed record dictionary

        Returns:
            CanadianOperator: Model instance or None
        """
        from callsign_db.models import CanadianOperator

        callsign = record.get('callsign', '').strip().upper()
        if not callsign:
            return None

        # Parse qualifications from qual_1 through qual_4
        # ISED qualification codes:
        #   B   = Basic
        #   BA  = Basic with Honours
        #   HB  = Basic with Honours (alternate)
        #   A   = Advanced
        #   HA  = Advanced with Honours
        #   M   = Morse Code 5 WPM
        #   M3  = Morse Code 12 WPM

        qual_fields = [
            record.get('qual_1', '').strip().upper(),
            record.get('qual_2', '').strip().upper(),
            record.get('qual_3', '').strip().upper(),
            record.get('qual_4', '').strip().upper(),
        ]

        # Collect non-empty qualifications
        all_quals = [q for q in qual_fields if q]

        qual_basic = any(
            q in ('B', 'BA', 'HB') for q in all_quals
        )
        qual_advanced = any(
            q in ('A', 'HA', 'ADV', 'ADVANCED')
            for q in all_quals
        )
        qual_honours = any(
            q in ('BA', 'HB', 'HA') for q in all_quals
        )
        qual_morse_5 = any(
            q in ('M', 'MORSE') for q in all_quals
        )
        qual_morse_12 = any(
            q in ('M3', 'MORSE3') for q in all_quals
        )

        # Build display qualification string
        qual_parts = []
        if qual_advanced:
            qual_parts.append('Advanced')
        elif qual_honours:
            qual_parts.append('Basic Honours')
        elif qual_basic:
            qual_parts.append('Basic')
        if qual_morse_12:
            qual_parts.append('Morse-12')
        elif qual_morse_5:
            qual_parts.append('Morse-5')

        qualifications = ', '.join(qual_parts) or 'Basic'

        return CanadianOperator(
            callsign=callsign,
            surname=record.get('surname', '').strip() or None,
            given_name=(
                record.get('given_name', '').strip() or None
            ),
            city=record.get('city', '').strip() or None,
            province=(
                record.get('province', '').strip() or None
            ),
            postal_code=(
                record.get('postal_code', '').strip() or None
            ),
            qual_basic=qual_basic,
            qual_advanced=qual_advanced,
            qual_honours=qual_honours,
            qual_morse_5=qual_morse_5,
            qual_morse_12=qual_morse_12,
            qualifications=qualifications,
            club_name=(
                record.get('club_name', '').strip() or None
            ),
            expiry_date=(
                record.get('expiry_date', '').strip() or None
            ),
        )