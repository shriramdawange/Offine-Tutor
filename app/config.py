import os

def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()

def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# Generation routing: cloud API first when configured, then local Ollama.
LLM_PROVIDER = _env("LLM_PROVIDER", "auto").lower()
API_BASE_URL = _env("API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_KEY = _env("API_KEY", "")
API_MODEL = _env("API_MODEL", "gpt-4o-mini")
API_TIMEOUT = int(_env("API_TIMEOUT", "45"))
API_MAX_RETRIES = int(_env("API_MAX_RETRIES", "0"))

OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = _env("OLLAMA_MODEL", "qwen2.5-coder:3b-instruct-q4_K_M")
KEEP_ALIVE = _env("OLLAMA_KEEP_ALIVE", "20m")
AUTO_PULL_LOCAL_MODEL = _bool_env("AUTO_PULL_LOCAL_MODEL", True)
LOCAL_PULL_TIMEOUT = int(_env("LOCAL_PULL_TIMEOUT", "900"))

NUM_CTX = int(_env("NUM_CTX", "4096"))
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
