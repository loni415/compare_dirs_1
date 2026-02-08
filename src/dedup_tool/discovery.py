"""File discovery module for local and Google Drive files."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import FileFormat, FileInfo
from .utils import (
    compute_content_hash,
    extract_language_suffix,
    get_base_name,
    get_format_from_path,
    is_supported_format,
)


class FileDiscoveryError(Exception):
    """Raised when file discovery fails."""
    pass


def scan_local_directory(
    directory: Path,
    recursive: bool = True,
    extract_content: bool = False
) -> list[FileInfo]:
    """Scan local directory for supported files.
    
    Args:
        directory: Root directory to scan
        recursive: Whether to scan subdirectories
        extract_content: Whether to extract text content from files
        
    Returns:
        List of FileInfo objects
    """
    files = []
    pattern = "**/*" if recursive else "*"
    
    logger.info(f"Scanning directory: {directory} (recursive={recursive})")
    
    for filepath in directory.glob(pattern):
        if not filepath.is_file():
            continue
            
        if not is_supported_format(filepath):
            continue
            
        try:
            stat = filepath.stat()
            file_format = FileFormat(get_format_from_path(filepath))
            lang_suffix = extract_language_suffix(filepath.name)
            base_name = get_base_name(filepath.name)
            
            file_info = FileInfo(
                path=filepath,
                format=file_format,
                size_bytes=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                language_suffix=lang_suffix,
                base_name=base_name,
                is_gdrive_link=(file_format == FileFormat.GDOC),
            )
            
            # Extract content if requested (for comparison)
            if extract_content and file_format != FileFormat.GDOC:
                try:
                    from .extractors import extract_content
                    text, gdrive_id = extract_content(filepath)
                    file_info.extracted_text = text
                    file_info.content_hash = compute_content_hash(text)
                except Exception as e:
                    logger.warning(f"Could not extract content from {filepath}: {e}")
            
            files.append(file_info)
            logger.debug(f"Found file: {filepath}")
            
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            continue
    
    logger.info(f"Found {len(files)} files in {directory}")
    return files


def resolve_gdrive_links(
    files: list[FileInfo],
    credentials_path: Optional[Path] = None
) -> list[FileInfo]:
    """Resolve Google Drive links to actual content via API.
    
    Args:
        files: List of FileInfo objects (may contain gdoc links)
        credentials_path: Path to Google Drive API credentials
        
    Returns:
        Updated list with gdoc content resolved
    """
    gdoc_files = [f for f in files if f.is_gdrive_link]
    if not gdoc_files:
        return files
        
    if not credentials_path:
        logger.warning("Google Drive credentials not provided, skipping gdoc resolution")
        return files
        
    logger.info(f"Resolving {len(gdoc_files)} Google Drive links...")
    
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=credentials)
        
        for file_info in gdoc_files:
            try:
                # Extract file ID from local link file
                with open(file_info.path, 'r') as f:
                    link_data = json.load(f)
                
                url = link_data.get('url', '')
                file_id = None
                if '/d/' in url:
                    parts = url.split('/d/')
                    if len(parts) > 1:
                        file_id = parts[1].split('/')[0]
                
                if not file_id:
                    logger.warning(f"Could not extract file ID from {file_info.path}")
                    continue
                
                # Export document as plain text
                request = service.files().export_media(
                    fileId=file_id,
                    mimeType='text/plain'
                )
                content = request.execute().decode('utf-8')
                
                file_info.extracted_text = content
                file_info.content_hash = compute_content_hash(content)
                file_info.gdrive_file_id = file_id
                logger.debug(f"Resolved gdoc: {file_info.path.name}")
                
            except Exception as e:
                logger.error(f"Failed to resolve {file_info.path}: {e}")
                continue
                
    except ImportError:
        logger.error("Google API libraries not installed")
    except Exception as e:
        logger.error(f"Google Drive API error: {e}")
    
    return files


def list_gdrive_directory(
    folder_id: str,
    credentials_path: Path,
    recursive: bool = False
) -> list[FileInfo]:
    """List files directly from Google Drive via API.
    
    Args:
        folder_id: Google Drive folder ID
        credentials_path: Path to service account credentials
        recursive: Whether to list files in subfolders
        
    Returns:
        List of FileInfo objects
    """
    logger.info(f"Listing Google Drive folder: {folder_id}")
    
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=credentials)
        
        files = []
        page_token = None
        
        # Supported MIME types mapping
        mime_to_format = {
            'application/vnd.google-apps.document': FileFormat.GDOC,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': FileFormat.DOCX,
            'application/msword': FileFormat.DOC,
            'application/pdf': FileFormat.PDF,
            'text/plain': FileFormat.TXT,
            'text/markdown': FileFormat.MD,
        }
        
        while True:
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                pageToken=page_token
            ).execute()
            
            items = results.get('files', [])
            
            for item in items:
                mime_type = item.get('mimeType', '')
                
                # Handle folders if recursive
                if mime_type == 'application/vnd.google-apps.folder' and recursive:
                    subfiles = list_gdrive_directory(
                        item['id'], credentials_path, recursive
                    )
                    files.extend(subfiles)
                    continue
                
                # Skip unsupported formats
                if mime_type not in mime_to_format:
                    continue
                
                file_format = mime_to_format[mime_type]
                name = item['name']
                lang_suffix = extract_language_suffix(name)
                base_name = get_base_name(name)
                
                file_info = FileInfo(
                    path=Path(f"gdrive://{folder_id}/{name}"),
                    format=file_format,
                    size_bytes=int(item.get('size', 0)),
                    modified_time=datetime.fromisoformat(
                        item['modifiedTime'].replace('Z', '+00:00')
                    ),
                    language_suffix=lang_suffix,
                    base_name=base_name,
                    is_gdrive_link=True,
                    gdrive_file_id=item['id'],
                )
                files.append(file_info)
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        
        logger.info(f"Found {len(files)} files in Google Drive folder {folder_id}")
        return files
        
    except Exception as e:
        logger.error(f"Failed to list Google Drive directory: {e}")
        raise FileDiscoveryError(f"Google Drive API error: {e}")


def discover_files(
    dir_a: Path | str,
    dir_b: Path | str,
    recursive: bool = True,
    extract_content: bool = False,
    gdrive_credentials: Optional[Path] = None
) -> tuple[list[FileInfo], list[FileInfo]]:
    """Discover files in both directories.
    
    Args:
        dir_a: First directory path or gdrive://folder-id
        dir_b: Second directory path or gdrive://folder-id
        recursive: Whether to scan recursively
        extract_content: Whether to extract text content
        gdrive_credentials: Path to Google Drive credentials
        
    Returns:
        Tuple of (files_in_a, files_in_b)
    """
    def _discover(path: Path | str) -> list[FileInfo]:
        path_str = str(path)
        
        if path_str.startswith('gdrive://'):
            if not gdrive_credentials:
                raise FileDiscoveryError(
                    "Google Drive credentials required for gdrive:// paths"
                )
            folder_id = path_str.replace('gdrive://', '').split('/')[0]
            return list_gdrive_directory(folder_id, gdrive_credentials, recursive)
        else:
            files = scan_local_directory(Path(path), recursive, extract_content)
            # Try to resolve gdoc links if credentials provided
            if gdrive_credentials:
                files = resolve_gdrive_links(files, gdrive_credentials)
            return files
    
    files_a = _discover(dir_a)
    files_b = _discover(dir_b)
    
    return files_a, files_b
