import os

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:3b-instruct-q4_K_M"
KEEP_ALIVE = "20m"

NUM_CTX = 4096
TEMP_QA = 0.3
TEMP_TEACH = 0.6

CHUNK_SIZE = 1100
CHUNK_OVERLAP = 150
TOP_K = 4

HISTORY_TURNS = 8
HISTORY_CHAR_BUDGET = 6000
INDEX_SAMPLE_BUDGET = 9000

TEST_QUESTIONS = 5
PASS_THRESHOLD = 0.6

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sessions")
MAX_UPLOAD_MB = 100
