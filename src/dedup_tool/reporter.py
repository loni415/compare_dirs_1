"""Reporting module for generating comparison spreadsheets."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from .models import MatchResult, MatchType


def generate_spreadsheet(
    matches: list[MatchResult],
    output_path: Path,
    include_metadata: bool = True
) -> None:
    """Generate Excel spreadsheet with match results.
    
    Args:
        matches: List of match results
        output_path: Path for output Excel file
        include_metadata: Whether to include additional metadata
    """
    logger.info(f"Generating spreadsheet with {len(matches)} matches")
    
    rows = []
    for match in matches:
        row: dict[str, Any] = {
            "File A Path": str(match.file_a.path),
            "File A Format": match.file_a.format.value,
            "File A Size (bytes)": match.file_a.size_bytes,
            "File A Language": match.file_a.language_suffix or "",
            "File B Path": str(match.file_b.path),
            "File B Format": match.file_b.format.value,
            "File B Size (bytes)": match.file_b.size_bytes,
            "File B Language": match.file_b.language_suffix or "",
            "Match Type": match.match_type.value,
            "Filename Similarity": round(match.filename_similarity, 3),
            "Content Similarity": round(match.content_similarity, 3) if match.content_similarity else "",
            "LLM Confidence": round(match.llm_confidence, 3) if match.llm_confidence else "",
            "Recommended Action": match.recommended_action.upper(),
            "Notes": match.notes,
        }
        
        if include_metadata:
            row.update({
                "File A Modified": match.file_a.modified_time.isoformat(),
                "File B Modified": match.file_b.modified_time.isoformat(),
                "LLM Reasoning": match.llm_reasoning or "",
            })
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # Create Excel writer with formatting
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Matches', index=False)
        
        # Get workbook and worksheet for formatting
        workbook = writer.book
        worksheet = writer.sheets['Matches']
        
        # Adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 60)  # Cap at 60
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    logger.info(f"Spreadsheet saved to {output_path}")


def generate_summary(
    matches: list[MatchResult],
    output_path: Optional[Path] = None
) -> dict[str, Any]:
    """Generate summary statistics of matches.
    
    Args:
        matches: List of match results
        output_path: Optional path to save JSON summary
        
    Returns:
        Dictionary with summary statistics
    """
    total_matches = len(matches)
    
    by_type: dict[str, int] = {}
    by_action: dict[str, int] = {}
    
    for match in matches:
        match_type = match.match_type.value
        by_type[match_type] = by_type.get(match_type, 0) + 1
        
        action = match.recommended_action
        by_action[action] = by_action.get(action, 0) + 1
    
    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_matches_found": total_matches,
        "by_match_type": by_type,
        "by_recommended_action": by_action,
        "files_to_review": by_action.get("review", 0),
        "files_to_delete": by_action.get("delete", 0),
    }
    
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Summary saved to {output_path}")
    
    return summary


def print_summary(summary: dict[str, Any]) -> None:
    """Print formatted summary to console."""
    print("\n" + "="*60)
    print("DEDUPLICATION SUMMARY")
    print("="*60)
    print(f"Generated: {summary['generated_at']}")
    print(f"Total matches found: {summary['total_matches_found']}")
    print()
    print("By Match Type:")
    for match_type, count in summary['by_match_type'].items():
        print(f"  - {match_type}: {count}")
    print()
    print("By Recommended Action:")
    for action, count in summary['by_recommended_action'].items():
        print(f"  - {action.upper()}: {count}")
    print()
    print(f"Files requiring review: {summary['files_to_review']}")
    print(f"Files recommended for deletion: {summary['files_to_delete']}")
    print("="*60 + "\n")
