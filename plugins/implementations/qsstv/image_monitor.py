"""
QSSTV Image Monitor
====================
Monitors QSSTV output directory for received SSTV images
and manages the image gallery.

QSSTV saves received images to:
    ~/.config/qsstv/rx/  (default receive directory)

This monitor uses the watchdog library to detect new
image files and adds them to the plugin gallery.

Supported Image Formats:
    - PNG (primary QSSTV output)
    - JPEG (alternative output)
    - BMP (legacy format)

Image Metadata:
    Each image is stored with:
    - Filename (timestamp-based)
    - Received datetime (UTC)
    - SSTV mode (extracted from QSSTV naming)
    - File size
    - Dimensions (via Pillow)
    - Optional callsign annotation

Reference:
    QSSTV saves images named like: rx_YYYYMMDD_HHMMSS_MODE.png
"""

import os
import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

# Handle optional imports gracefully
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


class ImageEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler for new SSTV image files.

    Called by watchdog observer when files are created
    or modified in the QSSTV receive directory.
    """

    def __init__(self, callback):
        """
        Initialize handler with callback function.

        Args:
            callback: Function called with new image path
        """
        super().__init__()
        self.callback = callback
        # Track recently processed files to avoid duplicates
        self._processed = set()

    def on_created(self, event):
        """
        Handle file creation event.

        Called when a new file appears in the watched
        directory. Filters for image files only.

        Args:
            event: Watchdog FileCreatedEvent
        """
        if event.is_directory:
            return

        filepath = event.src_path
        filename = os.path.basename(filepath)

        # Check if it's an image file
        if not self._is_image_file(filename):
            return

        # Avoid processing same file twice
        if filepath in self._processed:
            return

        self._processed.add(filepath)

        # Small delay to ensure file is fully written
        time.sleep(0.5)

        try:
            self.callback(filepath)
        except Exception as e:
            print(f"[QSSTV-Monitor] Callback error: {e}")

    def on_modified(self, event):
        """
        Handle file modification event.

        Some QSSTV versions update files after writing.

        Args:
            event: Watchdog FileModifiedEvent
        """
        if not event.is_directory:
            filepath = event.src_path
            if self._is_image_file(os.path.basename(filepath)):
                if filepath not in self._processed:
                    self._processed.add(filepath)
                    time.sleep(0.5)
                    try:
                        self.callback(filepath)
                    except Exception as e:
                        print(
                            f"[QSSTV-Monitor] Modified callback: {e}"
                        )

    @staticmethod
    def _is_image_file(filename):
        """
        Check if filename is an image file.

        Args:
            filename: Filename to check

        Returns:
            bool: True if image file extension
        """
        image_extensions = {
            '.png', '.jpg', '.jpeg', '.bmp',
            '.gif', '.tiff', '.tif'
        }
        ext = os.path.splitext(filename.lower())[1]
        return ext in image_extensions


class QSStvImageMonitor:
    """
    Monitors QSSTV image directories and manages gallery.

    Watches the QSSTV receive directory for new images,
    extracts metadata, generates thumbnails, and maintains
    an index of the image gallery.
    """

    def __init__(self, rx_dir, gallery_dir):
        """
        Initialize image monitor.

        Args:
            rx_dir: QSSTV receive directory
            gallery_dir: Plugin gallery storage directory
        """
        self.rx_dir = rx_dir
        self.gallery_dir = gallery_dir
        self.thumb_dir = os.path.join(gallery_dir, 'thumbnails')
        self.index_file = os.path.join(gallery_dir, 'index.json')

        # Create required directories
        os.makedirs(self.rx_dir, exist_ok=True)
        os.makedirs(self.gallery_dir, exist_ok=True)
        os.makedirs(self.thumb_dir, exist_ok=True)

        # Watchdog components
        self._observer = None
        self._running = False

        # Image index (in-memory cache)
        self._images = []
        self._images_lock = threading.Lock()

        # Callbacks for new images
        self._new_image_callbacks = []

        # Load existing index
        self._load_index()

    def register_new_image_callback(self, callback):
        """
        Register callback for new image events.

        Args:
            callback: Function(image_data) called on new image
        """
        self._new_image_callbacks.append(callback)

    def _trigger_callbacks(self, image_data):
        """Trigger all registered callbacks."""
        for cb in self._new_image_callbacks:
            try:
                cb(image_data)
            except Exception as e:
                print(f"[QSSTV-Monitor] Callback error: {e}")

    def start(self):
        """
        Start file system monitoring.

        Uses watchdog for efficient inotify-based monitoring
        on Linux. Falls back to polling if unavailable.

        Returns:
            bool: True if monitoring started
        """
        if self._running:
            return True

        # Scan existing images first
        self._scan_existing_images()

        if WATCHDOG_AVAILABLE:
            try:
                handler = ImageEventHandler(self._on_new_image)
                self._observer = Observer()
                self._observer.schedule(
                    handler,
                    self.rx_dir,
                    recursive=False
                )
                self._observer.start()
                self._running = True
                print(
                    f"[QSSTV-Monitor] Watchdog monitoring: "
                    f"{self.rx_dir}"
                )
                return True
            except Exception as e:
                print(f"[QSSTV-Monitor] Watchdog failed: {e}")
                return self._start_polling()
        else:
            print("[QSSTV-Monitor] Using polling (install watchdog)")
            return self._start_polling()

    def _start_polling(self):
        """
        Start polling-based directory monitoring.

        Fallback when watchdog is not available.
        Checks directory every 2 seconds.

        Returns:
            bool: Always True
        """
        self._running = True

        def poll():
            """Polling loop."""
            known_files = set(os.listdir(self.rx_dir))

            while self._running:
                try:
                    current_files = set(os.listdir(self.rx_dir))
                    new_files = current_files - known_files

                    for filename in new_files:
                        filepath = os.path.join(
                            self.rx_dir, filename
                        )
                        if ImageEventHandler._is_image_file(filename):
                            time.sleep(0.5)  # Wait for write
                            self._on_new_image(filepath)

                    known_files = current_files

                except Exception as e:
                    print(f"[QSSTV-Monitor] Poll error: {e}")

                time.sleep(2)

        thread = threading.Thread(
            target=poll,
            daemon=True,
            name='qsstv-image-poll'
        )
        thread.start()
        print("[QSSTV-Monitor] Polling started")
        return True

    def stop(self):
        """Stop file system monitoring."""
        self._running = False

        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass
            self._observer = None

        print("[QSSTV-Monitor] Monitoring stopped")

    def _on_new_image(self, filepath):
        """
        Handle a newly received SSTV image.

        Extracts metadata, generates thumbnail, adds to
        gallery index, and triggers callbacks.

        Args:
            filepath: Full path to the new image file
        """
        if not os.path.exists(filepath):
            return

        print(f"[QSSTV-Monitor] New image: {filepath}")

        # Build image metadata
        image_data = self._extract_metadata(filepath)

        if not image_data:
            return

        # Generate thumbnail
        thumb_path = self._generate_thumbnail(filepath)
        if thumb_path:
            image_data['thumbnail'] = os.path.basename(thumb_path)

        # Copy to gallery if not already there
        gallery_path = os.path.join(
            self.gallery_dir,
            image_data['filename']
        )

        if not os.path.exists(gallery_path):
            try:
                shutil.copy2(filepath, gallery_path)
                image_data['gallery_path'] = gallery_path
            except Exception as e:
                print(f"[QSSTV-Monitor] Copy error: {e}")
                image_data['gallery_path'] = filepath
        else:
            image_data['gallery_path'] = gallery_path

        # Add to index
        with self._images_lock:
            # Remove duplicate if exists
            self._images = [
                img for img in self._images
                if img.get('filename') != image_data['filename']
            ]
            # Add new entry at front
            self._images.insert(0, image_data)

        # Save index
        self._save_index()

        # Trigger callbacks (for logbook integration)
        self._trigger_callbacks(image_data)

        print(
            f"[QSSTV-Monitor] ✓ Image added to gallery: "
            f"{image_data['filename']}"
        )

    def _extract_metadata(self, filepath):
        """
        Extract metadata from SSTV image file.

        Parses filename for mode and timestamp information.
        Uses Pillow for image dimensions if available.

        QSSTV filename format:
            rx_YYYYMMDD_HHMMSS_MODE.png
            or custom names

        Args:
            filepath: Path to image file

        Returns:
            dict: Image metadata or None on error
        """
        try:
            filename = os.path.basename(filepath)
            stat = os.stat(filepath)
            file_time = datetime.fromtimestamp(stat.st_mtime)

            # Parse QSSTV filename format
            mode = self._parse_mode_from_filename(filename)
            timestamp = self._parse_timestamp_from_filename(filename)

            if timestamp is None:
                timestamp = file_time

            # Get image dimensions if Pillow available
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
                'mode': mode,
                'timestamp': timestamp.isoformat(),
                'file_size': stat.st_size,
                'width': width,
                'height': height,
                'callsign': '',    # Set by user or detection
                'notes': '',
                'received': True,  # True=received, False=transmitted
                'gallery_path': None,
                'thumbnail': None
            }

        except Exception as e:
            print(f"[QSSTV-Monitor] Metadata error: {e}")
            return None

    def _parse_mode_from_filename(self, filename):
        """
        Parse SSTV mode from QSSTV filename.

        QSSTV uses filenames like:
            rx_20240415_143022_MARTIN1.png
            rx_20240415_143022_S2.png

        Args:
            filename: Image filename

        Returns:
            str: Mode string or 'Unknown'
        """
        # Remove extension
        name = os.path.splitext(filename)[0]
        parts = name.split('_')

        # QSSTV filename format: prefix_date_time_mode
        if len(parts) >= 4:
            return parts[-1].upper()
        elif len(parts) >= 2:
            return parts[-1].upper()

        return 'Unknown'

    def _parse_timestamp_from_filename(self, filename):
        """
        Parse timestamp from QSSTV filename.

        Args:
            filename: Image filename

        Returns:
            datetime: Parsed timestamp or None
        """
        name = os.path.splitext(filename)[0]
        parts = name.split('_')

        # Try to parse date and time from filename parts
        for i, part in enumerate(parts):
            if len(part) == 8 and part.isdigit():
                # Looks like YYYYMMDD
                date_str = part
                # Check next part for time
                if i + 1 < len(parts) and \
                        len(parts[i+1]) >= 6 and \
                        parts[i+1][:6].isdigit():
                    time_str = parts[i+1][:6]
                    try:
                        return datetime.strptime(
                            f"{date_str}{time_str}",
                            "%Y%m%d%H%M%S"
                        )
                    except ValueError:
                        pass

        return None

    def _generate_thumbnail(self, filepath, size=(200, 150)):
        """
        Generate a thumbnail for the SSTV image.

        Creates a smaller version of the image for
        gallery display in the web UI.

        Args:
            filepath: Source image path
            size: Thumbnail dimensions (width, height)

        Returns:
            str: Thumbnail filepath or None
        """
        if not PILLOW_AVAILABLE:
            return None

        filename = os.path.basename(filepath)
        thumb_name = f"thumb_{filename}"
        thumb_path = os.path.join(self.thumb_dir, thumb_name)

        try:
            with PILImage.open(filepath) as img:
                # Convert to RGB for JPEG thumbnail
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # Create thumbnail maintaining aspect ratio
                img.thumbnail(size, PILImage.Resampling.LANCZOS)
                img.save(thumb_path, 'JPEG', quality=75)

            return thumb_path

        except Exception as e:
            print(f"[QSSTV-Monitor] Thumbnail error: {e}")
            return None

    def _scan_existing_images(self):
        """
        Scan receive directory for existing images.

        Called on startup to catalog images received
        before the plugin was running.
        """
        try:
            if not os.path.exists(self.rx_dir):
                return

            image_files = [
                f for f in os.listdir(self.rx_dir)
                if ImageEventHandler._is_image_file(f)
            ]

            print(
                f"[QSSTV-Monitor] Found {len(image_files)} "
                f"existing images"
            )

            for filename in sorted(image_files, reverse=True)[:50]:
                filepath = os.path.join(self.rx_dir, filename)
                metadata = self._extract_metadata(filepath)

                if metadata:
                    # Generate thumbnail if missing
                    if not metadata.get('thumbnail'):
                        thumb = self._generate_thumbnail(filepath)
                        if thumb:
                            metadata['thumbnail'] = (
                                os.path.basename(thumb)
                            )

                    with self._images_lock:
                        # Only add if not already in index
                        existing = [
                            img for img in self._images
                            if img.get('filename') == filename
                        ]
                        if not existing:
                            self._images.append(metadata)

            # Sort by timestamp
            with self._images_lock:
                self._images.sort(
                    key=lambda x: x.get('timestamp', ''),
                    reverse=True
                )

            self._save_index()

        except Exception as e:
            print(f"[QSSTV-Monitor] Scan error: {e}")

    def _load_index(self):
        """Load image index from JSON file."""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r') as f:
                    self._images = json.load(f)
                print(
                    f"[QSSTV-Monitor] Loaded {len(self._images)} "
                    f"images from index"
                )
            except Exception as e:
                print(f"[QSSTV-Monitor] Index load error: {e}")
                self._images = []

    def _save_index(self):
        """Save image index to JSON file."""
        try:
            with self._images_lock:
                index_data = list(self._images)

            with open(self.index_file, 'w') as f:
                json.dump(index_data, f, indent=2, default=str)

        except Exception as e:
            print(f"[QSSTV-Monitor] Index save error: {e}")

    def get_images(self, limit=50, offset=0):
        """
        Get gallery images with pagination.

        Args:
            limit: Maximum images to return
            offset: Pagination offset

        Returns:
            list: Image metadata dictionaries
        """
        with self._images_lock:
            return list(self._images)[offset:offset + limit]

    def get_image_count(self):
        """
        Get total number of gallery images.

        Returns:
            int: Total image count
        """
        with self._images_lock:
            return len(self._images)

    def get_image_by_id(self, image_id):
        """
        Find a specific image by ID.

        Args:
            image_id: Image identifier

        Returns:
            dict: Image data or None
        """
        with self._images_lock:
            for img in self._images:
                if str(img.get('id')) == str(image_id):
                    return dict(img)
        return None

    def update_image_metadata(self, image_id, callsign=None,
                               notes=None):
        """
        Update metadata for a gallery image.

        Allows adding callsign and notes to received images
        for logbook integration.

        Args:
            image_id: Image identifier
            callsign: Optional callsign to associate
            notes: Optional notes text

        Returns:
            bool: True if updated
        """
        with self._images_lock:
            for img in self._images:
                if str(img.get('id')) == str(image_id):
                    if callsign is not None:
                        img['callsign'] = callsign.upper()
                    if notes is not None:
                        img['notes'] = notes
                    self._save_index()
                    return True
        return False

    def delete_image(self, image_id):
        """
        Delete an image from the gallery.

        Args:
            image_id: Image identifier

        Returns:
            bool: True if deleted
        """
        with self._images_lock:
            image = None
            for img in self._images:
                if str(img.get('id')) == str(image_id):
                    image = img
                    break

            if not image:
                return False

            # Remove files
            gallery_path = image.get('gallery_path')
            if gallery_path and os.path.exists(gallery_path):
                try:
                    os.remove(gallery_path)
                except Exception:
                    pass

            # Remove thumbnail
            thumb = image.get('thumbnail')
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
            self._images = [
                img for img in self._images
                if str(img.get('id')) != str(image_id)
            ]
            self._save_index()

        return True