# Project Overview

This is a Python-based remote diagnostics tool for instrument log analysis. The main application (`instrument_log_qa.py`) provides intelligent error pattern matching and solution suggestions using Azure AI Search and OpenAI embeddings for ULF (Universal Log Format) files.

## Key Architecture Components

### Core Classes

- **`LogEntry`**: Represents a single log entry with timestamp, level, instrument_id, message, plus additional fields:
  - `message_id`: Unique identifier for the log message
  - `channel`: Communication channel where the log originated
  - `log_type`: Type classification of the log entry
  - `full_log_text`: Complete original log line text
  - `get_text_to_embed()`: Generates normalized text for embedding creation

### Data Flow

1. ULF log files are parsed using regex patterns to extract structured data
2. Log entries are normalized to remove variable data (GUIDs, IPs, file paths, etc.)
3. Text embeddings are generated for each error/warning entry using Azure OpenAI
4. Vector similarity search is performed against a knowledge base of known error patterns
5. Similar error patterns are returned with confidence scores

### Azure Integration

- **Azure AI Search**: Stores indexed error patterns with vector embeddings
- **Azure OpenAI**: Generates text embeddings using `text-embedding-3-small` model
- **Search Index**: `log-file-errors` contains error patterns, solutions, and metadata

## Common Development Commands

### Running the Application

```bash
python instrument_log_qa.py
```

### Installing Dependencies

```bash
pip install -r requirements.txt
```

### Environment Setup

1. Edit `.env` file with your actual Azure credentials and file paths:

```bash
# Azure Search Configuration
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_KEY=your-azure-search-key-here
SEARCH_INDEX_NAME=log-file-errors

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-openai-service.openai.azure.com/openai/deployments/text-embedding-3-small
AZURE_OPENAI_KEY=your-azure-openai-key-here

# LOG_FILE is the current log under processing. It's errors and warnings are matched against the signture store (Azure AI Search)
LOG_FILE=path/to/your/logfile.ulf

# SAMPLE_FILES_FOLDER is the folder containg logs. These were used to extract errors and warnings and update the signture store (Azure AI Search)
SAMPLE_FILES_FOLDER=path/to/sample/logs/folder
```

### Setting up Azure Search Index (one-time setup)
Uncomment the setup lines in `__main__` section:
```python
create_search_index()
# Batch process sample files from folder
for sample_file in get_filenames_in_folder(SAMPLE_FILES_FOLDER):
    if not sample_file.endswith('.ulf'):
        continue
    add_sample_error_knowledge(instrumentid, sample_file)
```

## Log Format

Expected ULF log format with XML-like attributes:
```
MsgID="12345" TimeStamp="2024-06-01T10:30:15.123Z" Channel="SystemChannel" Type="Error" Severity="Error" Message="Temperature sensor reading invalid"
```

### ULF Format Fields

- **MsgID**: Unique message identifier
- **TimeStamp**: ISO format timestamp
- **Channel**: Communication channel (e.g., SystemChannel, DataChannel)
- **Type**: Log entry type classification
- **Severity**: Error level (Error, Warning, Info, etc.)
- **Message**: Human-readable error description

## Security Considerations

- Azure credentials are configured via environment variables in `.env` file
- The `.env` file is excluded from version control via `.gitignore`
- Never commit actual API keys or credentials to the repository

## Key Functions

- `extract_log_entry()`: Parses ULF log lines using regex patterns into LogEntry objects
- `normalize_message()`: Removes variable data (GUIDs, IPs, paths) from messages for better pattern matching
- `get_embedding_with_inference_client()`: Generates embeddings using Azure OpenAI text-embedding-3-small
- `add_sample_error_knowledge()`: Processes log files and adds error patterns to search index
- `find_similar_errors()`: Performs vector similarity search against indexed patterns
- `suggest_solution()`: Returns similar error patterns with confidence scores
- `get_filenames_in_folder()`: Recursively finds all files in a directory for batch processing
- `find_matches()`: Processes a single log file and finds similar patterns for each error/warning

## Recent Updates

- **Batch Processing**: Added support for processing entire folders of ULF files
- **Message Normalization**: Implemented text normalization to improve pattern matching by replacing variable data
- **Duplicate Detection**: Added message signature storage to prevent duplicate entries in search index
- **Enhanced LogEntry**: Extended LogEntry class with additional ULF format fields (message_id, channel, log_type)