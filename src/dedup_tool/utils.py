"""Utility functions for the deduplication tool."""

import hashlib
import re
import string
from pathlib import Path
from typing import Optional


def normalize_filename(filename: str) -> str:
    """Normalize filename for comparison by removing punctuation and lowercasing."""
    # Remove extension
    name = Path(filename).stem
    # Remove language suffixes
    name = re.sub(r'_(en|zh|fr|de|es|jp|ko|ru)$', '', name, flags=re.IGNORECASE)
    # Replace underscores and hyphens with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    # Remove punctuation
    name = name.translate(str.maketrans('', '', string.punctuation))
    # Lowercase and strip
    return name.lower().strip()


def extract_language_suffix(filename: str) -> Optional[str]:
    """Extract language suffix (_en, _zh, etc.) from filename."""
    match = re.search(r'_(en|zh|fr|de|es|jp|ko|ru)$', Path(filename).stem, re.IGNORECASE)
    return match.group(1).lower() if match else None


def get_base_name(filename: str) -> str:
    """Get base name without extension and language suffix."""
    stem = Path(filename).stem
    # Remove language suffix if present
    stem = re.sub(r'_(en|zh|fr|de|es|jp|ko|ru)$', '', stem, flags=re.IGNORECASE)
    return stem


def compute_content_hash(text: str) -> str:
    """Compute MD5 hash of text content."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def truncate_text(text: str, max_length: int = 4000) -> str:
    """Truncate text for LLM prompts."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n[... {len(text) - max_length} characters truncated ...]"


def is_supported_format(filepath: Path) -> bool:
    """Check if file format is supported."""
    supported = {'.docx', '.doc', '.md', '.txt', '.gdoc', '.pdf'}
    return filepath.suffix.lower() in supported


def get_format_from_path(filepath: Path) -> str:
    """Get format string from file path."""
    return filepath.suffix.lower().lstrip('.')
