from azure.ai.inference import EmbeddingsClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "https://nikolaos-ai-search.search.windows.net")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
SEARCH_INDEX_NAME = os.getenv("SEARCH_INDEX_NAME", "log-file-errors")

# Validate required environment variables
if not AZURE_SEARCH_KEY:
    raise ValueError("AZURE_SEARCH_KEY environment variable is required")
if not AZURE_OPENAI_ENDPOINT:
    raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
if not AZURE_OPENAI_KEY:
    raise ValueError("AZURE_OPENAI_KEY environment variable is required")

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX_NAME,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

client = EmbeddingsClient(
    endpoint=AZURE_OPENAI_ENDPOINT,
    credential=AzureKeyCredential(AZURE_OPENAI_KEY)
)

class LogEntry:
    def __init__(self, timestamp, level, instrument_id, message):
        self.timestamp = timestamp
        self.level = level
        self.instrument_id = instrument_id
        self.message = message


class InstrumentLogAnalyzer:
    def __init__(self):
        self.chunk_size = 7  # 5-10 log entries per chunk

    def parse_log_line(self, line):
        """Parse individual log line into structured format"""
        # Example log format: 2024-06-01 10:30:15 [ERROR] TEMP_001: Temperature sensor reading invalid: -999.0°C
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (\w+): (.+)'
        match = re.match(pattern, line.strip())

        if match:
            timestamp, level, instrument_id, message = match.groups()
            return LogEntry(timestamp, level, instrument_id, message)
        return None

    def create_log_chunks(self, log_lines):
        """Group log entries into chunks of 5-10 entries"""
        entries = []
        for line in log_lines:
            entry = self.parse_log_line(line)
            if entry:
                entries.append(entry)

        chunks = []
        for i in range(0, len(entries), self.chunk_size):
            chunk_entries = entries[i:i + self.chunk_size]
            if chunk_entries:
                chunks.append(self.format_chunk(chunk_entries))

        return chunks

    def format_chunk(self, entries):
        """Format chunk of log entries with metadata"""
        chunk_text = []
        instrument = ""
        error_types = set()

        for entry in entries:
            chunk_text.append(
                f"{entry.timestamp} [{entry.level}] {entry.instrument_id}: {entry.message}")
            instrument = entry.instrument_id
            if entry.level in ['ERROR', 'WARN']:
                error_types.add(entry.level)

        return {
            'content': '\n'.join(chunk_text),
            'start_time': entries[0].timestamp,
            'end_time': entries[-1].timestamp,
            'instrument': instrument,
            'error_levels': list(error_types),
            'entry_count': len(entries)
        }

    def get_embedding_with_inference_client(self, text):
        """Generate embedding for text chunk"""
        response = client.embed(
            input=[text],
            model="text-embedding-3-small"
        )

        print(f"Response usage: {response.usage}")   
        return response.data[0].embedding


def create_search_index():
    """Create search index for instrument error logs"""
    from azure.search.documents.indexes.models import (
        SearchIndex, SearchField, SearchFieldDataType, SimpleField,
        SearchableField, VectorSearch, VectorSearchProfile,
        HnswAlgorithmConfiguration
    )

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="log_content", type=SearchFieldDataType.String),
        SearchableField(name="solution", type=SearchFieldDataType.String),
        SimpleField(name="start_time", type=SearchFieldDataType.String),
        SimpleField(name="end_time", type=SearchFieldDataType.String),
        SimpleField(name="instrument", type=SearchFieldDataType.String),
        SimpleField(name="error_levels", type=SearchFieldDataType.Collection(
            SearchFieldDataType.String)),
        SimpleField(name="severity", type=SearchFieldDataType.String),
        SearchField(name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True, vector_search_dimensions=1536, vector_search_profile_name="myHnswProfile")
    ]

    vector_search = VectorSearch(
        profiles=[VectorSearchProfile(
            name="myHnswProfile", algorithm_configuration_name="myHnsw")],
        algorithms=[HnswAlgorithmConfiguration(name="myHnsw")]
    )

    index = SearchIndex(name=SEARCH_INDEX_NAME,
                        fields=fields, vector_search=vector_search)

    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    index_client.create_or_update_index(index)
    print(f"Index '{SEARCH_INDEX_NAME}' created successfully")


def add_sample_error_knowledge():
    """Add sample error patterns and their solutions"""
    sample_errors = [
        {
            "id": "temp_sensor_invalid",
            "log_content": """2024-06-01 10:30:15 [ERROR] TEMP_001: Temperature sensor reading invalid: -999.0°C
2024-06-01 10:30:16 [WARN] TEMP_001: Sensor calibration check failed
2024-06-01 10:30:17 [ERROR] TEMP_001: Connection timeout to sensor
2024-06-01 10:30:18 [ERROR] TEMP_001: Sensor offline
2024-06-01 10:30:19 [INFO] SYSTEM: Switching to backup temperature sensor
2024-06-01 10:30:20 [ERROR] TEMP_002: Backup sensor also showing invalid readings
2024-06-01 10:30:21 [ERROR] SYSTEM: Temperature monitoring compromised""",
            "solution": "1. Check sensor cable connections\n2. Perform sensor recalibration using procedure TEMP-CAL-001\n3. If issue persists, replace temperature sensor\n4. Verify power supply to sensor module",
            "instrument": "Fluent 123456 1080",
            "error_levels": ["ERROR", "WARN"],
            "severity": "HIGH"
        },
        {
            "id": "pressure_drift",
            "log_content": """2024-06-01 11:15:30 [WARN] PRESS_001: Pressure reading drift detected: 45.2 PSI (expected 50.0 PSI)
2024-06-01 11:15:31 [INFO] PRESS_001: Running self-diagnostic
2024-06-01 11:15:32 [WARN] PRESS_001: Calibration reference out of range
2024-06-01 11:15:33 [ERROR] PRESS_001: Pressure sensor accuracy compromised
2024-06-01 11:15:34 [INFO] SYSTEM: Pressure alarm threshold adjusted
2024-06-01 11:15:35 [WARN] PRESS_001: Sensor requires recalibration""",
            "solution": "1. Perform pressure sensor recalibration using reference standard\n2. Check for ambient temperature effects on sensor\n3. Inspect sensor diaphragm for damage\n4. Update calibration coefficients in system",
            "instrument": "Fluent 123456 1080",
            "error_levels": ["ERROR", "WARN"],
            "severity": "MEDIUM"
        },
        {
            "id": "flow_blockage",
            "log_content": """2024-06-01 14:22:10 [WARN] FLOW_001: Flow rate below minimum threshold: 2.1 L/min (min: 5.0 L/min)
2024-06-01 14:22:11 [ERROR] FLOW_001: Flow sensor reading inconsistent
2024-06-01 14:22:12 [INFO] PUMP_001: Increasing pump speed to compensate
2024-06-01 14:22:13 [ERROR] FLOW_001: Flow rate continues to decrease: 1.8 L/min
2024-06-01 14:22:14 [ERROR] SYSTEM: Flow blockage suspected
2024-06-01 14:22:15 [ERROR] PUMP_001: Pump pressure exceeded maximum limit
2024-06-01 14:22:16 [ERROR] SYSTEM: Emergency shutdown activated""",
            "solution": "1. Check for blockages in flow lines and filters\n2. Inspect pump inlet and outlet connections\n3. Clean or replace flow filters\n4. Verify flow sensor is not obstructed\n5. Check for air bubbles in system",
            "instrument": "Fluent 123456 1080",
            "error_levels": ["ERROR", "WARN"],
            "severity": "HIGH"
        }
    ]

    analyzer = InstrumentLogAnalyzer()
    documents = []

    for error in sample_errors:
        # Generate embedding for the log content
        embedding = analyzer.get_embedding_with_inference_client(error["log_content"])

        doc = {
            "id": error["id"],
            "log_content": error["log_content"],
            "solution": error["solution"],
            "start_time": "2024-06-01 00:00:00",  # Would extract from actual logs
            "end_time": "2024-06-01 23:59:59",
            "instrument": error["instrument"],
            "error_levels": error["error_levels"],
            "severity": error["severity"],
            "content_vector": embedding
        }
        documents.append(doc)

    result = search_client.upload_documents(documents)
    print(f"Uploaded {len(documents)} error patterns to knowledge base")


def find_similar_errors(current_logs, top_k=1):
    """Find similar error patterns for current log entries"""
    analyzer = InstrumentLogAnalyzer()

    # Create chunk from current logs
    chunks = analyzer.create_log_chunks(current_logs)
    if not chunks:
        return []

    # Use the first chunk for similarity search
    current_chunk = chunks[0]
    current_embedding = analyzer.get_embedding_with_inference_client(current_chunk['content'])

    # Vector search
    vector_query = VectorizedQuery(
        vector=current_embedding,
        k_nearest_neighbors=top_k,
        fields="content_vector"
    )

    results = search_client.search(
        search_text="",
        vector_queries=[vector_query],
        select=["log_content", "solution", "instrument", "severity"],
        top=top_k
    )

    return list(results)


def suggest_solution(current_logs):
    """Main function to suggest solutions for current error logs"""
    print("Analyzing current error logs...")
    print("="*60)

    # Display current logs
    for i, log in enumerate(current_logs[:5], 1):  # Show first 5 lines
        print(f"{i}. {log.strip()}")
    if len(current_logs) > 5:
        print(f"... and {len(current_logs)-5} more entries")

    print("\nSearching for similar error patterns...")
    print("-"*60)

    # Find similar errors
    similar_errors = find_similar_errors(current_logs)

    if not similar_errors:
        return "No similar error patterns found in knowledge base."

    # Display results
    best_match = similar_errors[0]
    confidence = best_match.get('@search.score', 0)

    print(f"Best Match (Confidence: {confidence:.3f}):")
    print(f"Severity: {best_match['severity']}")
    print(f"Affected Instrument: {best_match['instrument']}")
    print("\nRecommended Solution:")
    print(best_match['solution'])

    return best_match['solution']


# Example usage
if __name__ == "__main__":
    # Setup (run once)
    # create_search_index()
    # add_sample_error_knowledge()

    # Simulate current error logs
    current_error_logs = [
        # "2024-06-01 15:45:10 [ERROR] TEMP_003: Temperature sensor reading invalid: -999.0°C",
        "2024-06-01 15:45:11 [WARN] TEMP_003: Sensor connection unstable",
        "2024-06-01 15:45:12 [ERROR] TEMP_003: Calibration data corrupted",
        "2024-06-01 15:45:13 [ERROR] TEMP_003: Sensor communication lost",
        "2024-06-01 15:45:14 [INFO] SYSTEM: Attempting sensor reset",
        "2024-06-01 15:45:15 [ERROR] TEMP_003: Reset failed - sensor unresponsive",
        "2024-06-01 15:45:16 [ERROR] SYSTEM: Temperature monitoring offline"
    ]

    # Get solution suggestion
    solution = suggest_solution(current_error_logs)
