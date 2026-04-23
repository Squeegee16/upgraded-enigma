"""
SatDump Data Monitor
=====================
Monitors SatDump output directories for new satellite
data products (images, data files).

SatDump Output Structure:
    output_dir/
        TIMESTAMP_PIPELINE/
            products/
                *.png     - Processed images
                *.jpg     - JPEG images
                *.bmp     - BMP images
                *.geotiff - Geo-referenced images
                *.csv     - Data tables
                metadata.json - Product metadata

Product Types:
    Images: APT composites, HRPT channel images,
            false-color composites, temperature maps
    Data:   Raw decoder output, calibration data,
            telemetry data

Monitoring:
    Uses watchdog for efficient inotify-based monitoring
    with polling fallback. Scans recursively for new
    files in SatDump output directory.

Reference:
    https://docs.satdump.org/products.html
"""

import os
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from collections import deque

try:
    from PIL import Image as PILImage
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class SatDumpEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler for SatDump output files.

    Monitors the output directory for new products
    created by SatDump processing pipelines.
    """

    def __init__(self, callback):
        """
        Initialize handler.

        Args:
            callback: Function(filepath) called on new product
        """
        super().__init__()
        self.callback = callback
        self._processed = set()

    def on_created(self, event):
        """
        Handle file creation events.

        Args:
            event: Watchdog event object
        """
        if event.is_directory:
            return

        filepath = event.src_path
        if filepath in self._processed:
            return

        if self._is_product_file(filepath):
            self._processed.add(filepath)
            # Delay to ensure file is fully written
            time.sleep(1.0)
            try:
                self.callback(filepath)
            except Exception as e:
                print(f"[SatDump-Monitor] Callback error: {e}")

    @staticmethod
    def _is_product_file(filepath):
        """
        Check if file is a SatDump product.

        Args:
            filepath: File path to check

        Returns:
            bool: True if product file
        """
        product_extensions = {
            '.png', '.jpg', '.jpeg', '.bmp',
            '.geotiff', '.tiff', '.tif'
        }
        ext = os.path.splitext(filepath.lower())[1]
        return ext in product_extensions


class SatDumpDataMonitor:
    """
    Monitors SatDump output for satellite data products.

    Watches the output directory for new processed images
    and data files, maintaining an index for the gallery.
    """

    def __init__(self, output_dir, gallery_dir):
        """
        Initialize data monitor.

        Args:
            output_dir: SatDump output directory
            gallery_dir: Plugin gallery storage directory
        """
        self.output_dir = output_dir
        self.gallery_dir = gallery_dir
        self.thumb_dir = os.path.join(gallery_dir, 'thumbnails')
        self.index_file = os.path.join(gallery_dir, 'products.json')

        # Create directories
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(gallery_dir, exist_ok=True)
        os.makedirs(self.thumb_dir, exist_ok=True)

        # Watchdog
        self._observer = None
        self._running = False

        # Product index
        self._products = deque(maxlen=500)
        self._products_lock = threading.Lock()

        # Callbacks
        self._new_product_callbacks = []

        # Pass tracking (active and completed)
        self._active_pass = None
        self._completed_passes = deque(maxlen=50)

        # Load existing index
        self._load_index()

    def register_callback(self, callback):
        """Register callback for new products."""
        self._new_product_callbacks.append(callback)

    def _trigger_callbacks(self, product_data):
        """Trigger registered callbacks."""
        for cb in self._new_product_callbacks:
            try:
                cb(product_data)
            except Exception as e:
                print(f"[SatDump-Monitor] Callback error: {e}")

    def start(self):
        """
        Start monitoring for new products.

        Returns:
            bool: True if started successfully
        """
        if self._running:
            return True

        # Scan existing products
        self._scan_existing()

        if WATCHDOG_AVAILABLE:
            try:
                handler = SatDumpEventHandler(
                    self._on_new_product
                )
                self._observer = Observer()
                self._observer.schedule(
                    handler,
                    self.output_dir,
                    recursive=True
                )
                self._observer.start()
                self._running = True
                print(
                    f"[SatDump-Monitor] Monitoring: "
                    f"{self.output_dir}"
                )
                return True
            except Exception as e:
                print(f"[SatDump-Monitor] Watchdog error: {e}")
                return self._start_polling()
        else:
            return self._start_polling()

    def _start_polling(self):
        """
        Start polling-based directory monitoring.

        Returns:
            bool: Always True
        """
        self._running = True

        def poll():
            """Polling monitor loop."""
            known_files = set()

            # Collect existing files
            for root, dirs, files in os.walk(self.output_dir):
                for f in files:
                    known_files.add(os.path.join(root, f))

            while self._running:
                try:
                    current_files = set()
                    for root, dirs, files in os.walk(
                        self.output_dir
                    ):
                        for f in files:
                            current_files.add(
                                os.path.join(root, f)
                            )

                    new_files = current_files - known_files
                    for filepath in new_files:
                        if SatDumpEventHandler._is_product_file(
                            filepath
                        ):
                            time.sleep(1.0)
                            self._on_new_product(filepath)

                    known_files = current_files

                except Exception as e:
                    print(f"[SatDump-Monitor] Poll error: {e}")

                time.sleep(3)

        thread = threading.Thread(
            target=poll,
            daemon=True,
            name='satdump-monitor-poll'
        )
        thread.start()
        return True

    def stop(self):
        """Stop monitoring."""
        self._running = False

        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass
            self._observer = None

    def _on_new_product(self, filepath):
        """
        Handle a new SatDump product file.

        Extracts metadata, generates thumbnail, adds
        to index, and triggers callbacks.

        Args:
            filepath: Path to new product file
        """
        if not os.path.exists(filepath):
            return

        print(f"[SatDump-Monitor] New product: {filepath}")

        # Build product metadata
        product = self._extract_metadata(filepath)
        if not product:
            return

        # Generate thumbnail
        thumb = self._generate_thumbnail(filepath)
        if thumb:
            product['thumbnail'] = os.path.basename(thumb)

        # Copy to gallery
        dest = os.path.join(
            self.gallery_dir, product['filename']
        )
        if not os.path.exists(dest):
            try:
                import shutil
                shutil.copy2(filepath, dest)
                product['gallery_path'] = dest
            except Exception as e:
                print(f"[SatDump-Monitor] Copy error: {e}")
                product['gallery_path'] = filepath

        # Add to index
        with self._products_lock:
            # Remove duplicate if exists
            self._products = deque(
                [p for p in self._products
                 if p.get('filename') != product['filename']],
                maxlen=500
            )
            self._products.appendleft(product)

        self._save_index()

        # Trigger callbacks
        self._trigger_callbacks(product)

        print(
            f"[SatDump-Monitor] ✓ Product added: "
            f"{product['filename']}"
        )

    def _extract_metadata(self, filepath):
        """
        Extract metadata from product file.

        Parses directory name for pipeline/satellite info.
        Uses Pillow for image dimensions.

        Args:
            filepath: Product file path

        Returns:
            dict: Product metadata
        """
        try:
            filename = os.path.basename(filepath)
            parent_dir = os.path.basename(
                os.path.dirname(filepath)
            )
            stat = os.stat(filepath)

            # Parse pipeline info from parent directory name
            pipeline_info = self._parse_pipeline_from_dir(
                parent_dir
            )

            # Get image dimensions
            width, height = None, None
            if PILLOW_AVAILABLE:
                try:
                    with PILImage.open(filepath) as img:
                        width, height = img.size
                except Exception:
                    pass

            return {
                'id': hash(filepath) & 0xFFFFFFFF,
                'filename': filename,
                'filepath': filepath,
                'gallery_path': None,
                'thumbnail': None,
                'parent_dir': parent_dir,
                'pipeline': pipeline_info.get('pipeline', ''),
                'satellite': pipeline_info.get('satellite', ''),
                'timestamp': datetime.fromtimestamp(
                    stat.st_mtime
                ).isoformat(),
                'file_size': stat.st_size,
                'width': width,
                'height': height,
                'product_type': self._get_product_type(filename),
                'notes': '',
                'callsign': '',
            }

        except Exception as e:
            print(f"[SatDump-Monitor] Metadata error: {e}")
            return None

    def _parse_pipeline_from_dir(self, dir_name):
        """
        Parse pipeline/satellite info from SatDump output dirname.

        SatDump creates directories named like:
        YYYYMMDD_HHMMSS_PIPELINE_ID
        or: TIMESTAMP_noaa_apt
            TIMESTAMP_meteor_m2_lrpt

        Args:
            dir_name: Directory name to parse

        Returns:
            dict: Parsed pipeline info
        """
        result = {'pipeline': 'Unknown', 'satellite': 'Unknown'}

        parts = dir_name.split('_')
        if len(parts) >= 3:
            # Skip timestamp parts (first 2 typically)
            pipeline_parts = parts[2:]
            pipeline_id = '_'.join(pipeline_parts)
            result['pipeline'] = pipeline_id

            # Map pipeline ID to satellite name
            pipeline_map = {
                'noaa_apt': 'NOAA APT',
                'meteor_m2_lrpt': 'METEOR-M2',
                'noaa_hrpt': 'NOAA HRPT',
                'goes_lrit': 'GOES',
                'fy3_mrpt': 'FengYun-3',
                'iss_sstv': 'ISS',
                'meteosat_lrit': 'Meteosat',
            }

            for key, satellite in pipeline_map.items():
                if key in pipeline_id.lower():
                    result['satellite'] = satellite
                    break

        return result

    def _get_product_type(self, filename):
        """
        Determine product type from filename.

        Args:
            filename: Product filename

        Returns:
            str: Product type description
        """
        name_lower = filename.lower()

        if 'apt' in name_lower:
            return 'APT Image'
        elif 'hrpt' in name_lower or 'avhrr' in name_lower:
            return 'HRPT Image'
        elif 'lrpt' in name_lower or 'msu' in name_lower:
            return 'LRPT Image'
        elif 'rgb' in name_lower or 'false' in name_lower:
            return 'False Color'
        elif 'temp' in name_lower or 'ir' in name_lower:
            return 'Thermal IR'
        elif 'vis' in name_lower:
            return 'Visible'
        elif 'geotiff' in name_lower or '.tiff' in name_lower:
            return 'GeoTIFF'
        else:
            return 'Satellite Image'

    def _generate_thumbnail(self, filepath, size=(250, 200)):
        """
        Generate thumbnail for product image.

        Args:
            filepath: Source image path
            size: Thumbnail dimensions

        Returns:
            str: Thumbnail path or None
        """
        if not PILLOW_AVAILABLE:
            return None

        filename = os.path.basename(filepath)
        # Use JPEG for thumbnails
        thumb_name = (
            f"thumb_{os.path.splitext(filename)[0]}.jpg"
        )
        thumb_path = os.path.join(self.thumb_dir, thumb_name)

        try:
            with PILImage.open(filepath) as img:
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                elif img.mode == 'L':
                    img = img.convert('RGB')

                img.thumbnail(size, PILImage.Resampling.LANCZOS)
                img.save(thumb_path, 'JPEG', quality=80)

            return thumb_path

        except Exception as e:
            print(f"[SatDump-Monitor] Thumbnail error: {e}")
            return None

    def _scan_existing(self):
        """Scan output directory for existing products."""
        try:
            count = 0
            for root, dirs, files in os.walk(self.output_dir):
                for filename in sorted(files, reverse=True):
                    if SatDumpEventHandler._is_product_file(
                        filename
                    ):
                        filepath = os.path.join(root, filename)
                        metadata = self._extract_metadata(filepath)

                        if metadata:
                            # Generate thumbnail if needed
                            if not metadata.get('thumbnail'):
                                thumb = self._generate_thumbnail(
                                    filepath
                                )
                                if thumb:
                                    metadata['thumbnail'] = (
                                        os.path.basename(thumb)
                                    )

                            with self._products_lock:
                                existing = [
                                    p for p in self._products
                                    if p.get('filename') ==
                                    filename
                                ]
                                if not existing:
                                    self._products.append(metadata)
                                    count += 1

            print(
                f"[SatDump-Monitor] Found {count} existing products"
            )
            self._save_index()

        except Exception as e:
            print(f"[SatDump-Monitor] Scan error: {e}")

    def _load_index(self):
        """Load product index from file."""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r') as f:
                    data = json.load(f)
                    self._products = deque(data, maxlen=500)
                print(
                    f"[SatDump-Monitor] Loaded "
                    f"{len(self._products)} products"
                )
            except Exception as e:
                print(f"[SatDump-Monitor] Index load error: {e}")

    def _save_index(self):
        """Save product index to file."""
        try:
            with self._products_lock:
                data = list(self._products)
            with open(self.index_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[SatDump-Monitor] Index save error: {e}")

    def get_products(self, limit=50, offset=0,
                     satellite_filter=None):
        """
        Get product list with optional filtering.

        Args:
            limit: Maximum products to return
            offset: Pagination offset
            satellite_filter: Filter by satellite name

        Returns:
            list: Product metadata dictionaries
        """
        with self._products_lock:
            products = list(self._products)

        if satellite_filter:
            products = [
                p for p in products
                if satellite_filter.lower() in
                p.get('satellite', '').lower()
            ]

        return products[offset:offset + limit]

    def get_product_count(self, satellite_filter=None):
        """
        Get total product count.

        Args:
            satellite_filter: Optional filter

        Returns:
            int: Product count
        """
        with self._products_lock:
            if not satellite_filter:
                return len(self._products)
            return sum(
                1 for p in self._products
                if satellite_filter.lower() in
                p.get('satellite', '').lower()
            )

    def set_active_pass(self, pass_info):
        """
        Set the currently active satellite pass.

        Args:
            pass_info: Dictionary with pass information
        """
        self._active_pass = pass_info

    def complete_pass(self):
        """
        Mark active pass as complete.

        Returns:
            dict: Completed pass info
        """
        if self._active_pass:
            self._active_pass['end_time'] = (
                datetime.utcnow().isoformat()
            )
            self._completed_passes.appendleft(
                dict(self._active_pass)
            )
            completed = dict(self._active_pass)
            self._active_pass = None
            return completed
        return None

    def get_passes(self, limit=20):
        """
        Get completed pass history.

        Returns:
            list: Completed pass records
        """
        return list(self._completed_passes)[:limit]

    def delete_product(self, product_id):
        """
        Delete a product from the index.

        Args:
            product_id: Product identifier

        Returns:
            bool: True if deleted
        """
        with self._products_lock:
            product = None
            for p in self._products:
                if str(p.get('id')) == str(product_id):
                    product = p
                    break

            if not product:
                return False

            # Remove files
            for path_key in ['gallery_path', 'filepath']:
                path = product.get(path_key)
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

            # Remove thumbnail
            thumb = product.get('thumbnail')
            if thumb:
                thumb_path = os.path.join(
                    self.thumb_dir, thumb
                )
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except Exception:
                        pass

            # Remove from index
            self._products = deque(
                [p for p in self._products
                 if str(p.get('id')) != str(product_id)],
                maxlen=500
            )
            self._save_index()

        return True