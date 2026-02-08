"""Content extraction from various file formats."""

import json
import os
from pathlib import Path
from typing import Optional

from loguru import logger

from .utils import truncate_text


class ContentExtractionError(Exception):
    """Raised when content extraction fails."""
    pass


def extract_from_txt(filepath: Path) -> str:
    """Extract text from plain text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with different encoding
        with open(filepath, 'r', encoding='latin-1') as f:
            return f.read()


def extract_from_md(filepath: Path) -> str:
    """Extract text from Markdown file."""
    return extract_from_txt(filepath)


def extract_from_docx(filepath: Path) -> str:
    """Extract text from DOCX file."""
    try:
        import docx
        doc = docx.Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return '\n\n'.join(paragraphs)
    except ImportError:
        raise ContentExtractionError("python-docx not installed")
    except Exception as e:
        raise ContentExtractionError(f"DOCX extraction failed: {e}")


def extract_from_pdf(filepath: Path) -> str:
    """Extract text from PDF file using pdfplumber."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return '\n\n'.join(text_parts)
    except ImportError:
        raise ContentExtractionError("pdfplumber not installed")
    except Exception as e:
        raise ContentExtractionError(f"PDF extraction failed: {e}")


def extract_from_doc(filepath: Path) -> str:
    """Extract text from DOC file (legacy Word format)."""
    # Try antiword first, then textract as fallback
    try:
        import subprocess
        result = subprocess.run(
            ['antiword', str(filepath)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Fallback: try to read as OLE document
    try:
        import olefile
        if olefile.isOleFile(filepath):
            ole = olefile.OleFileIO(filepath)
            # Try to extract text from WordDocument stream
            if ole.exists('WordDocument'):
                # This is a simplified extraction
                data = ole.openstream('WordDocument').read()
                ole.close()
                # Extract printable ASCII characters
                text = ''.join(chr(b) for b in data if 32 <= b < 127)
                return text
            ole.close()
    except ImportError:
        pass
    
    raise ContentExtractionError(
        "DOC extraction failed. Install antiword or convert to docx."
    )


def extract_from_gdoc_local(filepath: Path) -> tuple[str, Optional[str]]:
    """Extract from Google Drive desktop link file.
    
    Returns tuple of (text_content, gdrive_file_id)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Google Drive desktop files contain URL and file ID
        url = data.get('url', '')
        file_id = None
        
        # Extract file ID from URL
        if '/d/' in url:
            parts = url.split('/d/')
            if len(parts) > 1:
                file_id = parts[1].split('/')[0]
        
        return f"[Google Doc: {url}]", file_id
    except json.JSONDecodeError:
        raise ContentExtractionError(f"Invalid gdoc JSON: {filepath}")
    except Exception as e:
        raise ContentExtractionError(f"Gdoc link extraction failed: {e}")


def extract_content(filepath: Path) -> tuple[str, Optional[str]]:
    """Extract content from any supported file.
    
    Returns tuple of (text_content, gdrive_file_id or None)
    """
    ext = filepath.suffix.lower()
    gdrive_file_id = None
    
    logger.debug(f"Extracting content from {filepath}")
    
    if ext == '.txt':
        text = extract_from_txt(filepath)
    elif ext == '.md':
        text = extract_from_md(filepath)
    elif ext == '.docx':
        text = extract_from_docx(filepath)
    elif ext == '.pdf':
        text = extract_from_pdf(filepath)
    elif ext == '.doc':
        text = extract_from_doc(filepath)
    elif ext == '.gdoc':
        text, gdrive_file_id = extract_from_gdoc_local(filepath)
    else:
        raise ContentExtractionError(f"Unsupported format: {ext}")
    
    return text.strip(), gdrive_file_id


def extract_for_comparison(filepath: Path, max_length: int = 4000) -> tuple[str, Optional[str]]:
    """Extract content truncated for LLM comparison."""
    text, gdrive_id = extract_content(filepath)
    return truncate_text(text, max_length), gdrive_id
