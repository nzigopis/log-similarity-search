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
SAMPLE_FILES = os.getenv("SAMPLE_FILES")
SAMPLE_FILES_FOLDER = os.getenv("SAMPLE_FILES_FOLDER")

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

message_db = {}

class LogEntry:
    def __init__(self, timestamp, level, instrument_id, message, full_log_text, message_id, channel, log_type):
        self.timestamp = timestamp
        self.level = level
        self.instrument_id = instrument_id
        self.message = message
        self.full_log_text = full_log_text
        self.message_id = message_id
        self.channel = channel
        self.log_type = log_type

    def get_text_to_embed(self):
        """Generate text to embed for this log entry"""
        
        normalized_message = normalize_message(self.message[0:200])
        text_to_embed = f"{self.channel}, {self.log_type}, {self.level}, {normalized_message}"
        return text_to_embed
    
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

def extract_log_entry(line):
    """Parse individual log line into structured format"""
        
    global pattern
        
    match = re.search(pattern, line, re.DOTALL)

    if match:
        msg_id = match.group("MsgID")
        timestamp = match.group("TimeStamp")
        channel = match.group("Channel")
        log_type = match.group("Type")
        severity = match.group("Severity")
        message = match.group("Message")
        # exception = match.group("Exception")

        return LogEntry(timestamp, severity, "", message, line, msg_id, channel, log_type)
    else:
        return None
        
def get_embedding_with_inference_client(text):
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
        SearchableField(name="embedded_content", type=SearchFieldDataType.String),
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


def normalize_message(message):
    message = re.sub(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', 'GUID', message)
    # replace IP addresses with the word "IP"
    message = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', 'IP', message)
    # replace email addresses with the word "EMAIL"
    message = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', 'EMAIL', message)
    # replace file paths with the word "FILEPATH"
    message = re.sub(r'([a-zA-Z]:)?(\\[a-zA-Z0-9._-]+)+\\?', 'FILEPATH', message)
    # replace URLs with the word "URL"
    message = re.sub(r'https?://[^\s]+', 'URL', message)
    # replace phone numbers with the word "PHONE"
    message = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', 'PHONE', message)
    # replace dates with the word "DATE"
    message = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', 'DATE', message)
    # replace times with the word "TIME"
    message = re.sub(r'\b\d{1,2}:\d{2}:\d{2}\b', 'TIME', message)
    
    return message
    
def add_sample_error_knowledge(instrument_id, filename):
    """Add sample error patterns and their solutions"""

    documents = []
    
    with open(filename, 'r') as file:
        for line in file:
            entry = extract_log_entry(line)
            if entry and (entry.level in ['Error', 'Warning']):
                # print(f"{entry.timestamp} [{entry.level}] {entry.instrument_id}: {entry.message}")
    
                id_safe = re.sub(r'[^a-zA-Z0-9]', '-', f"{instrument_id}:{entry.message_id}:{entry.timestamp}")
                
                # Generate embedding for the log content
                normalized_message = normalize_message(entry.message[0:200])
                if normalized_message in message_db:
                    # print(f"Skipping duplicate message: {normalized_message}")
                    continue
                
                message_db[normalized_message] = True
                
                text_to_embed = entry.get_text_to_embed()
                
                # f"{entry.channel}, {entry.log_type}, {entry.level}, {normalized_message}"
                embedding = get_embedding_with_inference_client(text_to_embed)

                doc = {
                    "id": id_safe,
                    "log_content": entry.full_log_text,
                    "embedded_content": text_to_embed,
                    "solution": "",
                    "start_time": entry.timestamp,  
                    "end_time": entry.timestamp,
                    "instrument": instrument_id,
                    "error_levels": [entry.level],
                    "severity": entry.level,
                    "content_vector": embedding
                }
                # print(f"Adding error/warning pattern: {normalized_message}")
                documents.append(doc)
                # print(text_to_embed)

    if len(documents) > 0:
        result = search_client.upload_documents(documents)
        print(f"Uploaded {len(result)} error patterns to knowledge base")


def find_similar_errors(log, top_k=1):
    """Find similar error patterns for current log entries"""
    log_entry = extract_log_entry(log)
    # if not log_entry or log_entry.level not in ['Error']:
    #     return []
    
    log_embedding = get_embedding_with_inference_client(log_entry.get_text_to_embed())

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


def suggest_solution(log, top_k=1):
    """Main function to suggest solutions for current error logs"""

    similar_errors = find_similar_errors(log, top_k)

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


def get_filenames_in_folder(folder):
    # A list to store full paths of all files
    extracted_files = []

    # Walk through the given folder and its subfolders
    for root, dirs, files in os.walk(folder):
        for file in files:
            # Add the full path of the file to the list
            full_path = os.path.join(root, file)
            extracted_files.append(full_path)

    return extracted_files


def find_matches(filename, top_k=1):
    with open(filename, 'r') as file:
        for line in file:
            entry = extract_log_entry(line)
            if entry and (entry.level in ['Error', 'Warning']):
                signature_matches = suggest_solution(entry.full_log_text, top_k)
                if signature_matches:
                    matches = [f"Confidence: {match['confidence']},{match['signature log']}" for match in signature_matches]
                    matches_string = ''.join(matches)
                    print(f"{line}->\n{matches_string}")
                else:
                    print(f"\nCurrent Error {entry.message_id}:\n{line}No signature matches found")
    
    
if __name__ == "__main__":
    # Setup (run once)
    # create_search_index()
    
    #  SAMPLE_FILES.split(',')
    # for sample_file in get_filenames_in_folder(SAMPLE_FILES_FOLDER):
    #     if not sample_file.endswith('.ulf'):
    #         continue
    #     print(f"Adding log file to search index: {sample_file}")
    #     parts = sample_file.split('/')
    #     # sample_file = parts[-1] if len(parts) > 0 else sample_file
    #     instrumentid = parts[-2] if len(parts) > 1 else 'unknown'
        
    #     add_sample_error_knowledge(instrumentid, sample_file)
    
    find_matches(LOG_FILE, 3)                
    
