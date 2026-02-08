#!/usr/bin/env python3
"""Test script to verify that files are not reviewed multiple times."""

import tempfile
from pathlib import Path
from datetime import datetime
from collections import Counter

from dedup_tool.models import FileInfo, FileFormat
from dedup_tool.similarity import find_matches


def create_test_file(name: str, format: FileFormat = FileFormat.TXT) -> FileInfo:
    """Create a test FileInfo object."""
    return FileInfo(
        path=Path(f"/test/{name}.{format.value}"),
        format=format,
        size_bytes=1024,
        modified_time=datetime.now(),
        language_suffix=None,
        base_name=name,
        content_hash=None,
        extracted_text=f"Test content for {name}",
        is_gdrive_link=False,
        gdrive_file_id=None
    )


def test_redundant_reviews():
    """Test that files are not reviewed multiple times."""
    
    # Create a scenario similar to the user's issue
    # Multiple files with similar names that could create redundant comparisons
    files_a = [
        create_test_file("document1"),
        create_test_file("document2"),
        create_test_file("report_q1"),
        create_test_file("report_q2"),
    ]
    
    files_b = [
        create_test_file("document1"),  # Exact match with files_a[0]
        create_test_file("document2"),  # Exact match with files_a[1]
        create_test_file("report_q1"),  # Exact match with files_a[2]
        create_test_file("report_q2"),  # Exact match with files_a[3]
    ]
    
    print(f"Testing with {len(files_a)} files in A and {len(files_b)} files in B")
    print("All files have exact matches")
    
    # Find matches
    matches = find_matches(files_a, files_b, threshold=0.85, use_content=False)
    
    print(f"Found {len(matches)} matches")
    
    # Count how many times each file appears in matches
    file_a_counts = Counter([match.file_a.path.name for match in matches])
    file_b_counts = Counter([match.file_b.path.name for match in matches])
    
    print("\nFile A appearances:")
    for name, count in file_a_counts.items():
        print(f"  {name}: {count} times")
    
    print("\nFile B appearances:")
    for name, count in file_b_counts.items():
        print(f"  {name}: {count} times")
    
    # With the old algorithm (Cartesian product), each file would appear multiple times
    # With the new algorithm, each file should appear at most once
    max_a_appearances = max(file_a_counts.values()) if file_a_counts else 0
    max_b_appearances = max(file_b_counts.values()) if file_b_counts else 0
    
    print(f"\nMax appearances for any file in A: {max_a_appearances}")
    print(f"Max appearances for any file in B: {max_b_appearances}")
    
    # Verify that no file appears more than once
    assert max_a_appearances <= 1, f"Some files in A appear more than once: {max_a_appearances}"
    assert max_b_appearances <= 1, f"Some files in B appear more than once: {max_b_appearances}"
    
    print("✓ Test passed: No redundant reviews!")
    
    # Show the matches
    for i, match in enumerate(matches):
        print(f"  {i+1}. {match.file_a.path.name} <-> {match.file_b.path.name}: {match.match_type.value}")


def test_mixed_scenario():
    """Test a mixed scenario with exact and fuzzy matches."""
    
    files_a = [
        create_test_file("annual_report_2023"),
        create_test_file("quarterly_update"),
        create_test_file("meeting_notes"),
    ]
    
    files_b = [
        create_test_file("annual_report_2023"),  # Exact match
        create_test_file("quarterly_update_v2"),  # Similar
        create_test_file("meeting_notes_final"),  # Similar
        create_test_file("budget_planning"),      # No match
    ]
    
    print(f"\nTesting mixed scenario with {len(files_a)} files in A and {len(files_b)} files in B")
    
    # Find matches
    matches = find_matches(files_a, files_b, threshold=0.7, use_content=False)
    
    print(f"Found {len(matches)} matches")
    
    # Count appearances
    file_a_counts = Counter([match.file_a.path.name for match in matches])
    file_b_counts = Counter([match.file_b.path.name for match in matches])
    
    print("\nFile A appearances:")
    for name, count in file_a_counts.items():
        print(f"  {name}: {count} times")
    
    print("\nFile B appearances:")
    for name, count in file_b_counts.items():
        print(f"  {name}: {count} times")
    
    # Show the matches
    for i, match in enumerate(matches):
        print(f"  {i+1}. {match.file_a.path.name} <-> {match.file_b.path.name}: {match.match_type.value} (sim: {match.filename_similarity:.2f})")


if __name__ == "__main__":
    test_redundant_reviews()
    test_mixed_scenario()
    print("\n✓ All tests passed!")