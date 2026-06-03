"""
remove_sudo.py
~~~~~~~~~~~~~~
Utility to find and remove every occurrence of the word 'sudo' from
files inside a directory tree.

Usage
-----
    python remove_sudo.py /path/to/dir                   # dry-run (preview only)
    python remove_sudo.py /path/to/dir --apply           # apply changes
    python remove_sudo.py /path/to/dir --apply --backup  # apply + keep .bak copies
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from pathlib import Path
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Matches the literal word 'sudo' (case-sensitive).
# Swap re.IGNORECASE into the flag if you want case-insensitive removal.
_SUDO_PATTERN: re.Pattern[str] = re.compile(r"\bsudo\b")

logging.basicConfig(
    format="%(levelname)s  %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class FileResult:
    path: Path
    occurrences: int
    modified: bool = False
    error: str | None = None


@dataclass
class ScanSummary:
    directory: Path
    files_scanned: int = 0
    files_with_sudo: int = 0
    files_modified: int = 0
    total_occurrences: int = 0
    results: list[FileResult] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover
        lines = [
            f"\nDirectory : {self.directory}",
            f"Scanned   : {self.files_scanned} file(s)",
            f"Found     : {self.files_with_sudo} file(s) containing 'sudo' "
            f"({self.total_occurrences} occurrence(s))",
        ]
        if self.files_modified:
            lines.append(f"Modified  : {self.files_modified} file(s)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _is_binary(path: Path, sample_size: int = 8_192) -> bool:
    """Return True if the file looks like binary data (non-text)."""
    try:
        chunk = path.read_bytes()[:sample_size]
        return b"\x00" in chunk
    except OSError:
        return False


def _count_occurrences(text: str) -> int:
    return len(_SUDO_PATTERN.findall(text))


def _strip_sudo(text: str) -> str:
    """Remove every occurrence of 'sudo' (and any trailing whitespace it left)."""
    return _SUDO_PATTERN.sub("", text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_file(
    path: Path,
    *,
    apply: bool = False,
    backup: bool = False,
) -> FileResult:
    """
    Inspect *path* for occurrences of 'sudo'.

    Parameters
    ----------
    path    : file to inspect
    apply   : when True, overwrite the file with 'sudo' removed
    backup  : when True (and apply is True), write a '<path>.bak' copy first

    Returns
    -------
    FileResult with details about what was found / done
    """
    if _is_binary(path):
        log.debug("Skipping binary file: %s", path)
        return FileResult(path=path, occurrences=0)

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return FileResult(path=path, occurrences=0, error=str(exc))

    count = _count_occurrences(original)
    result = FileResult(path=path, occurrences=count)

    if count == 0 or not apply:
        return result

    # --- apply changes ---
    try:
        if backup:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        cleaned = _strip_sudo(original)
        path.write_text(cleaned, encoding="utf-8")
        result.modified = True
        log.info("Modified (%d occurrence(s) removed): %s", count, path)
    except OSError as exc:
        log.error("Failed to write %s: %s", path, exc)
        result.error = str(exc)

    return result


def search_and_remove_sudo(
    directory: str | Path,
    *,
    recursive: bool = True,
    apply: bool = False,
    backup: bool = False,
    glob_pattern: str = "*",
) -> ScanSummary:
    """
    Walk *directory* and optionally remove 'sudo' from every text file.

    Parameters
    ----------
    directory     : root directory to scan
    recursive     : descend into sub-directories (default True)
    apply         : commit changes to disk (default False → dry-run)
    backup        : create '<file>.bak' before overwriting (requires apply=True)
    glob_pattern  : restrict which filenames are checked (e.g. '*.sh', '*.py')

    Returns
    -------
    ScanSummary with aggregated statistics
    """
    root = Path(directory).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    summary = ScanSummary(directory=root)
    walker = root.rglob(glob_pattern) if recursive else root.glob(glob_pattern)

    mode = "APPLY" if apply else "DRY-RUN"
    log.info("[%s] Scanning: %s", mode, root)

    for file_path in walker:
        if not file_path.is_file():
            continue

        summary.files_scanned += 1
        result = process_file(file_path, apply=apply, backup=backup)
        summary.results.append(result)

        if result.occurrences:
            summary.files_with_sudo += 1
            summary.total_occurrences += result.occurrences
            log.info(
                "  [%s] %s  →  %d occurrence(s)",
                "MODIFIED" if result.modified else "FOUND",
                file_path,
                result.occurrences,
            )
        if result.modified:
            summary.files_modified += 1

    log.info("%s", summary)
    return summary


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and remove 'sudo' from files in a directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default: dry-run only)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=False,
        help="Keep a .bak copy of each file before modifying it",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        default=True,
        help="Only scan the top-level directory, not sub-directories",
    )
    parser.add_argument(
        "--glob",
        dest="glob_pattern",
        default="*",
        metavar="PATTERN",
        help="Glob pattern to filter files, e.g. '*.sh' (default: '*')",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    search_and_remove_sudo(
        directory=args.directory,
        recursive=args.recursive,
        apply=args.apply,
        backup=args.backup,
        glob_pattern=args.glob_pattern,
    )
