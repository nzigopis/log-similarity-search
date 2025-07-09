# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based remote diagnostics tool for instrument log analysis. The main application (`instrument_log_qa.py`) provides intelligent error pattern matching and solution suggestions using Azure AI Search and OpenAI embeddings.

## Key Architecture Components

### Core Classes
- **`LogEntry`**: Represents a single log entry with timestamp, level, instrument_id, and message
- **`InstrumentLogAnalyzer`**: Main analyzer class that handles log parsing, chunking, and embedding generation
  - Parses log entries using regex patterns
  - Groups log entries into chunks of 7 entries for analysis
  - Generates embeddings using Azure OpenAI text-embedding-3-small model

### Data Flow
1. Log entries are parsed into structured `LogEntry` objects
2. Entries are grouped into chunks with metadata (timestamps, instrument info, error levels)
3. Text embeddings are generated for each chunk using Azure OpenAI
4. Vector similarity search is performed against a knowledge base of known error patterns
5. Solutions are returned based on the best matching error patterns

### Azure Integration
- **Azure AI Search**: Stores indexed error patterns with vector embeddings
- **Azure OpenAI**: Generates text embeddings for semantic search
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
1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` file with your actual Azure credentials:
```bash
# Azure Search Configuration
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_KEY=your-azure-search-key-here
SEARCH_INDEX_NAME=log-file-errors

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-openai-service.openai.azure.com/openai/deployments/text-embedding-3-small
AZURE_OPENAI_KEY=your-azure-openai-key-here
```

### Setting up Azure Search Index (one-time setup)
Uncomment the setup lines in `__main__` section:
```python
create_search_index()
add_sample_error_knowledge()
```

## Log Format
Expected log format: `YYYY-MM-DD HH:MM:SS [LEVEL] INSTRUMENT_ID: message`

Example:
```
2024-06-01 10:30:15 [ERROR] TEMP_001: Temperature sensor reading invalid: -999.0°C
```

## Security Considerations
- Azure credentials are configured via environment variables in `.env` file
- The `.env` file is excluded from version control via `.gitignore`
- Use `.env.example` as a template for setting up local development environment
- Never commit actual API keys or credentials to the repository

## Key Functions
- `parse_log_line()`: Parses individual log lines into structured format
- `create_log_chunks()`: Groups log entries into analyzable chunks
- `get_embedding_with_inference_client()`: Generates embeddings for text
- `find_similar_errors()`: Performs vector similarity search
- `suggest_solution()`: Main function that provides error analysis and solutions