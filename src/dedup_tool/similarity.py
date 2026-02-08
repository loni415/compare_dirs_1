"""Similarity matching engine for file comparison."""

from difflib import SequenceMatcher
from typing import Optional

from rapidfuzz import fuzz

from .models import FileFormat, FileInfo, MatchResult, MatchType
from .utils import normalize_filename


def compute_filename_similarity(name_a: str, name_b: str) -> float:
    """Compute fuzzy similarity between two filenames (0-1 scale).
    
    Uses rapidfuzz's token_set_ratio for robust comparison.
    """
    norm_a = normalize_filename(name_a)
    norm_b = normalize_filename(name_b)
    
    if not norm_a or not norm_b:
        return 0.0
    
    # Use token_set_ratio for word-order independence
    similarity = fuzz.token_set_ratio(norm_a, norm_b) / 100.0
    return similarity


def compute_content_similarity(text_a: str, text_b: str) -> float:
    """Compute similarity between two text contents (0-1 scale).
    
    Uses SequenceMatcher for line-by-line comparison.
    """
    if not text_a or not text_b:
        return 0.0
    
    # Normalize whitespace
    norm_a = ' '.join(text_a.split())
    norm_b = ' '.join(text_b.split())
    
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def should_keep_different_formats(
    file_a: FileInfo,
    file_b: FileInfo
) -> bool:
    """Determine if files with same name but different formats should be kept.
    
    True if:
    - Same base name (after removing language suffix)
    - Different formats
    - Same or different language suffixes (both cases keep)
    """
    # Same base name (without extension and language suffix)
    if file_a.base_name != file_b.base_name:
        return False
    
    # Different formats means KEEP
    if file_a.format != file_b.format:
        return True
    
    # Same format but different language suffix means KEEP
    if file_a.language_suffix != file_b.language_suffix:
        return True
    
    return False


def compare_files(
    file_a: FileInfo,
    file_b: FileInfo,
    threshold: float = 0.85,
    use_content: bool = False
) -> MatchResult:
    """Compare two files and determine match type.
    
    Args:
        file_a: First file info
        file_b: Second file info
        threshold: Similarity threshold for fuzzy matching
        use_content: Whether to compare extracted content
        
    Returns:
        MatchResult with recommendation
    """
    # Compute filename similarity
    filename_sim = compute_filename_similarity(file_a.path.name, file_b.path.name)
    
    # Check for exact same name and format (DELETABLE)
    same_name = file_a.path.stem == file_b.path.stem
    same_format = file_a.format == file_b.format
    
    if same_name and same_format:
        # Check if they're actually different files (different language suffix already in base_name)
        # Same exact filename = duplicate
        return MatchResult(
            file_a=file_a,
            file_b=file_b,
            match_type=MatchType.EXACT_NAME_FORMAT,
            filename_similarity=1.0,
            content_similarity=None,
            recommended_action="delete",
            notes=f"Exact duplicate: same name ({file_a.path.name}) and format ({file_a.format.value})"
        )
    
    # Check for same name but different formats (KEEP - different formats)
    if same_name and not same_format:
        return MatchResult(
            file_a=file_a,
            file_b=file_b,
            match_type=MatchType.SAME_NAME_DIFF_FORMAT,
            filename_similarity=1.0,
            content_similarity=None,
            recommended_action="keep",
            notes=f"Same content in different formats ({file_a.format.value} vs {file_b.format.value})"
        )
    
    # Check for same base name (normalized) but different language suffix
    if file_a.base_name == file_b.base_name:
        if file_a.language_suffix != file_b.language_suffix:
            return MatchResult(
                file_a=file_a,
                file_b=file_b,
                match_type=MatchType.SAME_NAME_DIFF_FORMAT,
                filename_similarity=1.0,
                content_similarity=None,
                recommended_action="keep",
                notes=f"Different language versions ({file_a.language_suffix} vs {file_b.language_suffix})"
            )
    
    # Fuzzy filename match
    if filename_sim >= threshold:
        # Similar names - need content comparison or LLM review
        content_sim = None
        notes = f"Similar filenames (confidence: {filename_sim:.2f})"
        
        if use_content and file_a.extracted_text and file_b.extracted_text:
            content_sim = compute_content_similarity(
                file_a.extracted_text,
                file_b.extracted_text
            )
            notes += f", content similarity: {content_sim:.2f}"
            
            if content_sim >= threshold:
                return MatchResult(
                    file_a=file_a,
                    file_b=file_b,
                    match_type=MatchType.SAME_CONTENT_DIFF_NAME,
                    filename_similarity=filename_sim,
                    content_similarity=content_sim,
                    recommended_action="review",
                    notes=notes + " - Likely same content, different filenames"
                )
        
        return MatchResult(
            file_a=file_a,
            file_b=file_b,
            match_type=MatchType.SIMILAR_NAME,
            filename_similarity=filename_sim,
            content_similarity=content_sim,
            recommended_action="review",
            notes=notes + " - Please review to confirm if same document"
        )
    
    # Content comparison even if filenames differ significantly
    if use_content and file_a.extracted_text and file_b.extracted_text:
        content_sim = compute_content_similarity(
            file_a.extracted_text,
            file_b.extracted_text
        )
        
        if content_sim >= threshold:
            return MatchResult(
                file_a=file_a,
                file_b=file_b,
                match_type=MatchType.SAME_CONTENT_DIFF_NAME,
                filename_similarity=filename_sim,
                content_similarity=content_sim,
                recommended_action="review",
                notes=f"Different filenames but high content similarity ({content_sim:.2f})"
            )
    
    # No significant match
    return MatchResult(
        file_a=file_a,
        file_b=file_b,
        match_type=MatchType.UNCERTAIN,
        filename_similarity=filename_sim,
        content_similarity=None,
        recommended_action="keep",
        notes="No significant match detected"
    )


def find_matches(
    files_a: list[FileInfo],
    files_b: list[FileInfo],
    threshold: float = 0.85,
    use_content: bool = False
) -> list[MatchResult]:
    """Find all matches between two file lists.
    
    Args:
        files_a: Files from directory A
        files_b: Files from directory B  
        threshold: Similarity threshold
        use_content: Whether to compare content
        
    Returns:
        List of match results
    """
    results = []
    
    # Compare each file in A with each file in B
    for file_a in files_a:
        for file_b in files_b:
            result = compare_files(file_a, file_b, threshold, use_content)
            
            # Only include significant matches or those requiring review
            if result.match_type != MatchType.UNCERTAIN or result.filename_similarity > 0.5:
                results.append(result)
    
    return results
