"""Safe file operations for deduplication."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import AuditLogEntry, FileInfo, MatchResult


class FileOperationError(Exception):
    """Raised when file operation fails."""
    pass


def create_to_delete_folder(base_path: Path, folder_name: str = "to_delete") -> Path:
    """Create the to_delete folder with timestamp.
    
    Args:
        base_path: Base directory for the operation
        folder_name: Name of the deletion folder
        
    Returns:
        Path to created folder
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    to_delete_path = base_path / f"{folder_name}_{timestamp}"
    to_delete_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created deletion folder: {to_delete_path}")
    return to_delete_path


def move_to_delete(
    file_info: FileInfo,
    to_delete_folder: Path,
    preserve_structure: bool = True,
    audit_log: Optional[list[AuditLogEntry]] = None
) -> Path:
    """Move a file to the to_delete folder.
    
    Args:
        file_info: File to move
        to_delete_folder: Destination folder
        preserve_structure: Whether to preserve directory structure
        audit_log: Optional list to append audit entry
        
    Returns:
        Path to new location
    """
    source = file_info.path
    
    # Handle Google Drive paths (gdrive://...)
    if str(source).startswith('gdrive://'):
        logger.warning(f"Cannot move Google Drive file: {source}")
        return source
    
    if not source.exists():
        raise FileOperationError(f"Source file does not exist: {source}")
    
    # Determine destination path
    if preserve_structure:
        # Use original filename only, not full path
        dest = to_delete_folder / source.name
    else:
        dest = to_delete_folder / source.name
    
    # Handle name collisions
    counter = 1
    original_dest = dest
    while dest.exists():
        stem = original_dest.stem
        suffix = original_dest.suffix
        dest = to_delete_folder / f"{stem}_{counter}{suffix}"
        counter += 1
    
    try:
        shutil.move(str(source), str(dest))
        logger.info(f"Moved: {source} -> {dest}")
        
        # Record in audit log
        if audit_log is not None:
            entry = AuditLogEntry(
                timestamp=datetime.now(),
                action="move_to_delete",
                source_path=source,
                destination_path=dest,
                file_info={
                    "format": file_info.format.value,
                    "size_bytes": file_info.size_bytes,
                    "language": file_info.language_suffix,
                },
                reason="Duplicate file identified by deduplication tool"
            )
            audit_log.append(entry)
        
        return dest
        
    except Exception as e:
        raise FileOperationError(f"Failed to move {source}: {e}")


def execute_deletions(
    matches: list[MatchResult],
    target_dir: Path,
    to_delete_folder: Optional[Path] = None,
    dry_run: bool = False
) -> tuple[list[Path], list[AuditLogEntry]]:
    """Execute deletions for all matches marked for deletion.
    
    Args:
        matches: List of match results
        target_dir: Directory being deduplicated (for creating to_delete folder)
        to_delete_folder: Optional pre-created deletion folder
        dry_run: If True, don't actually move files
        
    Returns:
        Tuple of (moved_files, audit_log)
    """
    moved_files: list[Path] = []
    audit_log: list[AuditLogEntry] = []
    
    if not dry_run and to_delete_folder is None:
        to_delete_folder = create_to_delete_folder(target_dir)
    
    # Get unique files to delete (from dir_b only to be safe)
    files_to_delete: set[Path] = set()
    for match in matches:
        if match.recommended_action == "delete":
            # Only delete from dir_b to avoid losing data
            files_to_delete.add(match.file_b.path)
    
    logger.info(f"{'Would move' if dry_run else 'Moving'} {len(files_to_delete)} files to deletion folder")
    
    for file_path in files_to_delete:
        if dry_run:
            logger.info(f"[DRY RUN] Would move: {file_path}")
            continue
        
        try:
            # Find the FileInfo for this path
            file_info = None
            for match in matches:
                if match.file_b.path == file_path:
                    file_info = match.file_b
                    break
            
            if file_info is None:
                logger.warning(f"No FileInfo found for {file_path}, skipping")
                continue
            
            dest = move_to_delete(file_info, to_delete_folder, audit_log=audit_log)
            moved_files.append(dest)
            
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            continue
    
    return moved_files, audit_log


def save_audit_log(
    audit_log: list[AuditLogEntry],
    output_path: Path
) -> None:
    """Save audit log to JSON file.
    
    Args:
        audit_log: List of audit entries
        output_path: Path for output JSON
    """
    entries = []
    for entry in audit_log:
        entries.append({
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action,
            "source_path": str(entry.source_path),
            "destination_path": str(entry.destination_path) if entry.destination_path else None,
            "file_info": entry.file_info,
            "reason": entry.reason,
        })
    
    with open(output_path, 'w') as f:
        json.dump(entries, f, indent=2)
    
    logger.info(f"Audit log saved to {output_path}")


def undo_deletions(audit_log_path: Path) -> list[Path]:
    """Undo deletions based on audit log.
    
    Args:
        audit_log_path: Path to audit log JSON
        
    Returns:
        List of restored files
    """
    with open(audit_log_path, 'r') as f:
        entries = json.load(f)
    
    restored: list[Path] = []
    
    for entry in entries:
        if entry["action"] != "move_to_delete":
            continue
        
        source = Path(entry["source_path"])
        dest = Path(entry["destination_path"])
        
        if not dest.exists():
            logger.warning(f"Cannot restore {dest}, file not found")
            continue
        
        # Recreate source directory if needed
        source.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.move(str(dest), str(source))
            restored.append(source)
            logger.info(f"Restored: {dest} -> {source}")
        except Exception as e:
            logger.error(f"Failed to restore {dest}: {e}")
    
    return restored
