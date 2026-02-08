# File Deduplication Tool

A Python CLI tool for intelligent file deduplication across local and Google Drive directories. Uses fuzzy matching, content analysis, and optional LLM-powered semantic comparison to identify duplicates while preserving important variants.

## Features

- **Multi-format support**: DOCX, DOC, MD, TXT, PDF, GDOC
- **Smart preservation**: Keeps files in different formats (e.g., `.docx` and `.pdf` of same document)
- **Language-aware**: Recognizes `_en` and `_zh` suffixes as distinct documents
- **Fuzzy matching**: Identifies similar filenames with confidence scores
- **LLM integration**: Optional semantic analysis via LM Studio, Ollama, or vLLM
- **Google Drive support**: Works with local Drive links or direct API access
- **Safe operations**: Moves files to `to_delete` folder instead of permanent deletion
- **Audit logging**: Full traceability with JSON audit logs
- **Preview mode**: Generate spreadsheets before making changes

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd compare_dirs_1

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
```

## Quick Start

### Basic Usage

```bash
# Preview mode - generates spreadsheet only
dedup-tool /path/to/dir1 /path/to/dir2 --preview-only

# Full deduplication with recursive scan
dedup-tool /path/to/dir1 /path/to/dir2 --recursive

# Custom threshold for fuzzy matching
dedup-tool /path/to/dir1 /path/to/dir2 --threshold 0.9
```

### With LLM Analysis

```bash
# Using Ollama (local)
dedup-tool /path/to/dir1 /path/to/dir2 --llm-provider ollama --llm-model llama2

# Using LM Studio
dedup-tool /path/to/dir1 /path/to/dir2 --llm-provider lmstudio

# Using vLLM
dedup-tool /path/to/dir1 /path/to/dir2 --llm-provider vllm --llm-model meta-llama/Llama-2-7b
```

### Google Drive Integration

```bash
# Local Google Drive folder (with .gdoc links)
dedup-tool /local/dir1 ~/GoogleDrive/MyFolder --gdrive-credentials /path/to/creds.json

# Direct Google Drive API access
dedup-tool /local/dir gdrive://FOLDER_ID --gdrive-credentials /path/to/creds.json
```

## How It Works

### Match Types

1. **Exact Name + Format** (`exact_name_format`): Same filename and extension → **DELETE**
2. **Same Name, Different Format** (`same_name_diff_format`): e.g., `doc.docx` and `doc.pdf` → **KEEP**
3. **Same Content, Different Name** (`same_content_diff_name`): Identical content → **REVIEW**
4. **Similar Name** (`similar_name`): Fuzzy match above threshold → **REVIEW**
5. **Uncertain**: No significant match → **KEEP**

### Language Suffixes

Files with `_en` and `_zh` suffixes are always treated as distinct:
- `document_en.docx` and `document_zh.docx` → **KEEP** (different languages)
- `document_en.docx` and `document_en.pdf` → **KEEP** (different formats)
- `document_en.docx` and `document_en.docx` → **DELETE** (exact duplicate)

## Configuration

### Google Drive Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a service account and download JSON credentials
3. Share your Google Drive folder with the service account email
4. Use `--gdrive-credentials` flag or set `DEDUP_GDRIVE_CREDENTIALS` environment variable

```bash
export DEDUP_GDRIVE_CREDENTIALS=/path/to/credentials.json
```

### LLM Setup

**LM Studio:**
- Start LM Studio and load a model
- Enable "Local Server" on port 1234 (default)

**Ollama:**
```bash
ollama pull llama2
ollama serve
```

**vLLM:**
```bash
python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-2-7b
```

## Command Reference

```
dedup-tool [OPTIONS] DIR_A DIR_B

Arguments:
  DIR_A  First directory to compare
  DIR_B  Second directory to compare

Options:
  -r, --recursive           Scan directories recursively [default: True]
  --preview-only            Generate report without moving files
  -t, --threshold FLOAT     Similarity threshold (0.0-1.0) [default: 0.85]
  --llm-provider CHOICE     LLM provider: lmstudio, ollama, or vllm
  --llm-url TEXT            Custom LLM API URL
  --llm-model TEXT          LLM model name
  -o, --output PATH         Output spreadsheet path [default: dedup_report.xlsx]
  --gdrive-credentials PATH Path to Google Drive service account JSON
  --to-delete-folder TEXT   Deletion folder name [default: to_delete]
  -v, --verbose             Enable verbose logging
  --help                    Show this message and exit
```

## Output Format

The generated Excel spreadsheet contains:

| Column | Description |
|--------|-------------|
| File A/B Path | Full path to each file |
| File A/B Format | File format (docx, pdf, etc.) |
| File A/B Size | File size in bytes |
| File A/B Language | Detected language suffix |
| Match Type | Classification of the match |
| Filename Similarity | Fuzzy match score (0-1) |
| Content Similarity | Text similarity score (0-1) |
| LLM Confidence | Semantic analysis score |
| Recommended Action | delete / keep / review |
| Notes | Explanation and context |

## Safety Features

1. **Preview mode** (`--preview-only`): Review all matches before action
2. **To-delete folder**: Files moved, not deleted
3. **Audit logging**: JSON log of all operations
4. **User confirmation**: Prompt before moving files
5. **Undo capability**: Restore from audit log

### Restoring Files

```python
from dedup_tool.operations import undo_deletions

restored = undo_deletions("path/to/audit_log.json")
print(f"Restored {len(restored)} files")
```

## Examples

### Example 1: Preview Before Action

```bash
# Generate preview spreadsheet
dedup-tool /home/user/documents /backup/documents --preview-only -o preview.xlsx

# Review preview.xlsx, then execute
dedup-tool /home/user/documents /backup/documents
```

### Example 2: High-Confidence Deduplication

```bash
# Only flag very similar files (threshold 0.95)
dedup-tool dir1 dir2 --threshold 0.95 --llm-provider ollama
```

### Example 3: Google Drive Cleanup

```bash
# Compare local files with Google Drive
dedup-tool /home/user/docs gdrive://1ABC123xyz --gdrive-credentials creds.json --preview-only
```

### Example 4: Non-Recursive Scan

```bash
# Only scan top-level directories
dedup-tool dir1 dir2 --no-recursive
```

## Troubleshooting

### PDF Extraction Issues

Install additional dependencies:
```bash
sudo apt-get install antiword  # For .doc files
pip install olefile            # For legacy Office formats
```

### Google Drive API Errors

- Verify service account has access to the folder
- Check that Drive API is enabled in Google Cloud Console
- Ensure credentials file is valid JSON

### LLM Connection Errors

- Verify LLM server is running on expected port
- Check firewall settings
- Use `--llm-url` to specify custom endpoint

## License

MIT License
