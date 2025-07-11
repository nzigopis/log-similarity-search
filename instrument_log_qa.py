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
LOG_FILE = os.getenv("LOG_FILE")

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
    def __init__(self, timestamp, level, instrument_id, message, full_log_text, message_id):
        self.timestamp = timestamp
        self.level = level
        self.instrument_id = instrument_id
        self.message = message
        self.full_log_text = full_log_text
        self.message_id = message_id


class InstrumentLogAnalyzer:
    def __init__(self):
        self.chunk_size = 1  # log entries per chunk

    def extract_log_entry(self, line):
        """Parse individual log line into structured format"""
        
        pattern = (
            r'MsgID="(?P<MsgID>[^"]+)"\s+' 
            r'TimeStamp="(?P<TimeStamp>[^"]+)"\s+'  # TimeStamp field
            r'Channel="(?P<Channel>[^"]+)"\s+'      # Channel field
            r'Type="(?P<Type>[^"]+)"\s+'            # Type field
            r'Severity="(?P<Severity>[^"]+)"\s+'    # Severity field
            # r'Message="(?P<Message>.*?)(?=(?:\s*at\s+[^"]+.*?){2})'
            r'Message="(?P<Message>[^"]+?)"\s*'     # Matches Message up to the next tag
            # r'(?:<Exception>\s*<!\[CDATA\[(?P<Exception>.*?)\]\]>\s*</Exception>)?'  # Matches optional Exception tag
            # r'Message="(?P<Message>[^"]+.[^<]*)"\s*' # Message field up to <Exception>
            # r'<Exception>\s*<!\[CDATA\[(?P<Exception>.*?)\]\]>'  # Exception block
        )
        
        match = re.search(pattern, line, re.DOTALL)

        if match:
            msg_id = match.group("MsgID")
            timestamp = match.group("TimeStamp")
            channel = match.group("Channel")
            log_type = match.group("Type")
            severity = match.group("Severity")
            message = match.group("Message")
            # exception = match.group("Exception")

            return LogEntry(timestamp, severity, "", message, line, msg_id)
        else:
            return None

    def create_log_chunks(self, log_lines):
        """Group log entries into chunks of 5-10 entries"""
        entries = []
        for line in log_lines:
            entry = self.extract_log_entry(line)
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
                f"{entry.timestamp} [{entry.level}] {entry.instrument_id}: {entry.message} - {entry.exception if entry.exception else 'No Exception'}")
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

        # print(f"Response usage: {response.usage}")   
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


def add_sample_error_knowledge(filename):
    """Add sample error patterns and their solutions"""

    analyzer = InstrumentLogAnalyzer()
    documents = []

    
    with open(filename, 'r') as file:
        for line in file:
            entry = analyzer.extract_log_entry(line)
            if entry and (entry.level in ['Error']):
                print(f"{entry.timestamp} [{entry.level}] {entry.instrument_id}: {entry.message}")
    
                # Generate embedding for the log content
                embedding = analyzer.get_embedding_with_inference_client(entry.message)

                doc = {
                    "id": entry.message_id,
                    "log_content": entry.full_log_text,
                    "solution": "",
                    "start_time": entry.timestamp,  
                    "end_time": entry.timestamp,
                    "instrument": "",
                    "error_levels": [entry.level],
                    "severity": entry.level,
                    "content_vector": embedding
                }
                documents.append(doc)

    result = search_client.upload_documents(documents)
    print(f"Uploaded {len(documents)} error patterns to knowledge base")


def find_similar_errors(log, top_k=1):
    """Find similar error patterns for current log entries"""
    analyzer = InstrumentLogAnalyzer()

    log_entry = analyzer.extract_log_entry(log)
    if not log_entry or log_entry.level not in ['Error']:
        return []
    
    log_embedding = analyzer.get_embedding_with_inference_client(log_entry.message)

    # Vector search
    vector_query = VectorizedQuery(
        vector=log_embedding,
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


def suggest_solution(log):
    """Main function to suggest solutions for current error logs"""

    similar_errors = find_similar_errors(log)

    if not similar_errors:
        return "No similar error patterns found in knowledge base."

    results = []

    for i, error in enumerate(similar_errors):
        confidence = error.get('@search.score', 0)
        best_match = {
            'severity': error['severity'],
            'log_content': error['log_content'] if 'log_content' in error else ''
        }
        results.append({
            'confidence': confidence,
            'severity': best_match['severity'],
            'signature log': best_match['log_content']
        })   

    return results

def parse_log(filename):
    """Parse log file and return list of log lines"""
    analyser = InstrumentLogAnalyzer()
    with open(filename, 'r') as file:
        n = 1
        for line in file:
            entry = analyser.extract_log_entry(line)
            if entry and (entry.level in ['Error']):
                print(f"{n}. {entry.timestamp} [{entry.level}] {entry.instrument_id}: {entry.message}")
            n += 1
            

if __name__ == "__main__":
    analyser = InstrumentLogAnalyzer()
    with open(LOG_FILE, 'r') as file:
        for line in file:
            entry = analyser.extract_log_entry(line)
            if entry and (entry.level in ['Error']):
                signature_matches = suggest_solution(entry.full_log_text)
                if signature_matches:
                    for match in signature_matches:
                        print(f"\nCurrent Error {entry.message_id}:\n{line}Matched Signature Confidence: {match['confidence']}, Severity: {match['severity']}, Log:\n{match['signature log']}")
                else:
                    print(f"\nCurrent Error {entry.message_id}:\n{line}No signature matches found")
                    
    # Setup (run once)
    # create_search_index()
    # add_sample_error_knowledge()
    
