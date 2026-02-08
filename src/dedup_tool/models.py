"""Pydantic models for the deduplication tool."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class FileFormat(str, Enum):
    """Supported file formats."""
    DOCX = "docx"
    DOC = "doc"
    MD = "md"
    TXT = "txt"
    GDOC = "gdoc"
    PDF = "pdf"


class MatchType(str, Enum):
    """Types of matches detected."""
    EXACT_NAME_FORMAT = "exact_name_format"  # Same name, same format - DELETE
    SAME_NAME_DIFF_FORMAT = "same_name_diff_format"  # Same name, diff format - KEEP
    SAME_CONTENT_DIFF_NAME = "same_content_diff_name"  # Same content - FLAG
    SIMILAR_NAME = "similar_name"  # Fuzzy match - CHECK
    UNCERTAIN = "uncertain"  # Requires manual review


class FileInfo(BaseModel):
    """Information about a discovered file."""
    path: Path
    format: FileFormat
    size_bytes: int
    modified_time: datetime
    language_suffix: Optional[str] = None  # "_en", "_zh", etc.
    base_name: str  # Name without extension and language suffix
    content_hash: Optional[str] = None
    extracted_text: Optional[str] = None
    is_gdrive_link: bool = False
    gdrive_file_id: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True


class MatchResult(BaseModel):
    """Result of comparing two files."""
    file_a: FileInfo
    file_b: FileInfo
    match_type: MatchType
    filename_similarity: float = Field(ge=0.0, le=1.0)
    content_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    llm_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    llm_reasoning: Optional[str] = None
    recommended_action: str  # "delete", "keep", "review"
    notes: str = ""


class AuditLogEntry(BaseModel):
    """Entry in the audit log."""
    timestamp: datetime
    action: str
    source_path: Path
    destination_path: Optional[Path] = None
    file_info: Optional[dict[str, Any]] = None
    reason: str


class DedupConfig(BaseModel):
    """Configuration for deduplication run."""
    dir_a: Path
    dir_b: Path
    recursive: bool = True
    threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    use_llm: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    preview_only: bool = False
    output_path: Path = Path("dedup_report.xlsx")
    to_delete_folder: Path = Path("to_delete")
    google_drive_credentials: Optional[Path] = None
