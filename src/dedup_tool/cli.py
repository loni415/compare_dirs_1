"""CLI interface for the deduplication tool."""

import sys
from pathlib import Path

import click
from loguru import logger

from .discovery import discover_files
from .extractors import extract_for_comparison
from .llm_client import create_llm_client
from .models import FileInfo, MatchResult
from .operations import execute_deletions, save_audit_log
from .reporter import generate_spreadsheet, generate_summary, print_summary
from .similarity import find_matches


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = "DEBUG" if verbose else "INFO"
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )


def enhance_with_llm(
    matches: list[MatchResult],
    llm_provider: str,
    llm_url: str | None,
    llm_model: str | None,
    threshold: float
) -> list[MatchResult]:
    """Enhance matches with LLM semantic analysis."""
    logger.info(f"Initializing LLM client: {llm_provider}")
    client = create_llm_client(llm_provider, llm_url, llm_model)
    
    enhanced = []
    
    for match in matches:
        # Only process matches that need review or have similar names
        if match.recommended_action not in ["review", "delete"]:
            enhanced.append(match)
            continue
        
        # Skip if no content available
        if not match.file_a.extracted_text or not match.file_b.extracted_text:
            enhanced.append(match)
            continue
        
        try:
            confidence, reasoning = client.compare_documents(
                match.file_a,
                match.file_b,
                match.file_a.extracted_text,
                match.file_b.extracted_text
            )
            
            match.llm_confidence = confidence
            match.llm_reasoning = reasoning
            
            # Adjust recommendation based on LLM confidence
            if confidence >= threshold:
                if match.match_type.value == "similar_name":
                    match.recommended_action = "delete" if confidence > 0.9 else "review"
                    match.notes += f" | LLM: Same document (confidence: {confidence:.2f})"
            
            enhanced.append(match)
            
        except Exception as e:
            logger.error(f"LLM analysis failed for {match.file_a.path.name} vs {match.file_b.path.name}: {e}")
            enhanced.append(match)
    
    client.close()
    return enhanced


@click.command()
@click.argument('dir_a', type=click.Path(exists=False))
@click.argument('dir_b', type=click.Path(exists=False))
@click.option('--recursive', '-r', is_flag=True, default=True, help='Scan directories recursively')
@click.option('--preview-only', is_flag=True, help='Generate report without moving files')
@click.option('--threshold', '-t', default=0.85, help='Similarity threshold (0.0-1.0)', type=float)
@click.option('--llm-provider', type=click.Choice(['lmstudio', 'ollama', 'vllm']), help='LLM provider for semantic analysis')
@click.option('--llm-url', help='Custom LLM API URL')
@click.option('--llm-model', help='LLM model name')
@click.option('--output', '-o', default='dedup_report.xlsx', help='Output spreadsheet path')
@click.option('--gdrive-credentials', type=click.Path(exists=True), help='Path to Google Drive service account JSON')
@click.option('--to-delete-folder', default='to_delete', help='Name of deletion folder')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(
    dir_a: str,
    dir_b: str,
    recursive: bool,
    preview_only: bool,
    threshold: float,
    llm_provider: str | None,
    llm_url: str | None,
    llm_model: str | None,
    output: str,
    gdrive_credentials: str | None,
    to_delete_folder: str,
    verbose: bool
) -> None:
    """File deduplication tool with intelligent matching.
    
    Compare files in DIR_A and DIR_B to identify duplicates.
    
    Examples:
    
        # Preview mode - generate report only
        dedup-tool /path/to/dir1 /path/to/dir2 --preview-only
        
        # Full deduplication with recursive scan
        dedup-tool /path/to/dir1 /path/to/dir2 --recursive
        
        # Use LLM for semantic analysis
        dedup-tool /path/to/dir1 /path/to/dir2 --llm-provider ollama --llm-model llama2
        
        # Include Google Drive folder (via API)
        dedup-tool /local/dir gdrive://folder-id --gdrive-credentials /path/to/creds.json
    """
    setup_logging(verbose)
    
    logger.info("Starting deduplication tool")
    logger.info(f"Directory A: {dir_a}")
    logger.info(f"Directory B: {dir_b}")
    logger.info(f"Recursive: {recursive}")
    logger.info(f"Preview only: {preview_only}")
    
    # Validate paths (skip for gdrive:// URLs)
    if not dir_a.startswith('gdrive://') and not Path(dir_a).exists():
        click.echo(f"Error: Directory does not exist: {dir_a}", err=True)
        sys.exit(1)
    
    if not dir_b.startswith('gdrive://') and not Path(dir_b).exists():
        click.echo(f"Error: Directory does not exist: {dir_b}", err=True)
        sys.exit(1)
    
    # Determine if we need content extraction
    need_content = llm_provider is not None
    
    # Discover files
    try:
        creds_path = Path(gdrive_credentials) if gdrive_credentials else None
        files_a, files_b = discover_files(
            dir_a, dir_b,
            recursive=recursive,
            extract_content=need_content,
            gdrive_credentials=creds_path
        )
    except Exception as e:
        logger.error(f"File discovery failed: {e}")
        sys.exit(1)
    
    logger.info(f"Found {len(files_a)} files in A, {len(files_b)} files in B")
    
    if len(files_a) == 0 or len(files_b) == 0:
        logger.warning("One or both directories contain no supported files")
        sys.exit(0)
    
    # Extract content if LLM is being used
    if need_content:
        logger.info("Extracting content from files...")
        for files in [files_a, files_b]:
            for file_info in files:
                if file_info.is_gdrive_link:
                    continue  # Already extracted or will be handled
                try:
                    text, _ = extract_for_comparison(file_info.path)
                    file_info.extracted_text = text
                except Exception as e:
                    logger.warning(f"Could not extract {file_info.path}: {e}")
    
    # Find matches
    logger.info("Finding matches...")
    matches = find_matches(files_a, files_b, threshold, use_content=need_content)
    
    # Enhance with LLM if requested
    if llm_provider:
        logger.info("Enhancing with LLM analysis...")
        matches = enhance_with_llm(matches, llm_provider, llm_url, llm_model, threshold)
    
    logger.info(f"Found {len(matches)} matches")
    
    # Generate report
    output_path = Path(output)
    generate_spreadsheet(matches, output_path)
    
    summary = generate_summary(matches, output_path.with_suffix('.summary.json'))
    print_summary(summary)
    
    if preview_only:
        logger.info("Preview mode - no files moved")
        click.echo(f"\nReport saved to: {output_path}")
        click.echo("Review the spreadsheet and run without --preview-only to execute deletions")
        return
    
    # Execute deletions for exact duplicates
    delete_matches = [m for m in matches if m.recommended_action == "delete"]
    
    if not delete_matches:
        logger.info("No files marked for deletion")
        return
    
    # Confirm before deleting
    click.echo(f"\n{len(delete_matches)} file pairs marked for deletion")
    if not click.confirm("Proceed with moving files to deletion folder?"):
        logger.info("Operation cancelled by user")
        return
    
    # Execute
    target_dir = Path(dir_b) if not dir_b.startswith('gdrive://') else Path(dir_a)
    moved_files, audit_log = execute_deletions(
        matches,
        target_dir,
        dry_run=False
    )
    
    # Save audit log
    if audit_log:
        audit_path = target_dir / f"dedup_audit_{Path(output).stem}.json"
        save_audit_log(audit_log, audit_path)
        click.echo(f"Audit log saved to: {audit_path}")
    
    click.echo(f"Moved {len(moved_files)} files to deletion folder")
    click.echo(f"Report saved to: {output_path}")


if __name__ == '__main__':
    main()
