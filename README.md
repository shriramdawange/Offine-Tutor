# API-Integrated Tutor (Cloud-first + local fallback)

A document-grounded AI study companion. Upload PDFs, notes, text, code, CSV, and other supported files, then ask questions or learn the material through a structured course. Retrieval remains local and uses the project's lightweight, dependency-free BM25 implementation.

## What changed

- **Cloud-first generation:** Uses an OpenAI-compatible Chat Completions API when `API_KEY` is configured.
- **Automatic local fallback:** If the cloud request fails, returns an error, times out, or returns an invalid/empty answer, generation automatically switches to Ollama.
- **Local model preparation:** If Ollama is installed but the configured model is missing, the application attempts to start Ollama and pull the model automatically.
- **BM25 retrieval:** Existing pure-Python BM25 ranks chunks from the student's uploaded documents. No embedding model, vector database, or GPU is required.
- **Grounded answers and citations:** Ask & Learn uses retrieved excerpts and citations such as `[filename · part/total]`.
- **Learning modes:** Ask & Learn, Fresh → Pro, and Pick Topics remain available.
- **Session isolation:** Uploaded documents, chat, curriculum, and progress remain session-scoped. Deleting a session removes its stored data and in-memory retrieval cache.

## Quick start (Windows)

1. Install Python 3.11+ and [Ollama](https://ollama.com/download).
2. Run `setup.bat` once.
3. Copy `.env.example` to `.env` and configure your cloud API settings. The application reads environment variables; the launcher loads `.env` automatically.
4. Run `start.bat` and open `http://localhost:8000`.

If the cloud API is unavailable, Ollama is used automatically. The first local fallback may take time because the model may need to download. Make sure the machine has enough disk space and internet access for that initial download. After the model is downloaded, local generation works without the cloud API.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto` or `api` tries cloud first; `local` uses Ollama directly |
| `API_BASE_URL` | OpenAI API URL | Base URL for an OpenAI-compatible API |
| `API_KEY` | empty | Cloud API key; never commit it |
| `API_MODEL` | `gpt-4o-mini` | Cloud model name supported by the configured provider |
| `API_TIMEOUT` | `45` | Cloud request timeout in seconds |
| `OLLAMA_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5-coder:3b-instruct-q4_K_M` | Local fallback model |
| `AUTO_PULL_LOCAL_MODEL` | `true` | Automatically prepare the local model when missing |
| `TOP_K` | `4` | Number of BM25-ranked chunks sent as context |

For an OpenAI-compatible provider, set `API_BASE_URL`, `API_KEY`, and `API_MODEL` to the values provided by that service. Do not put secrets in source files or frontend JavaScript.

## Retrieval and answer behavior

- BM25 indexes document chunks per session and is invalidated when documents are changed or the session is deleted.
- Ask & Learn answers are instructed to use retrieved excerpts and cite their source.
- If relevant text is not found, the tutor should say that the answer is not covered by the uploaded documents.
- Both cloud and local generation receive the same messages and retrieved context; provider switching does not re-upload documents or rebuild the index.

## Important runtime details

- Cloud generation is buffered before display so a failure during the cloud request can safely trigger local fallback without mixing partial answers. The UI still renders the answer incrementally after the response is ready.
- Automatic fallback requires Ollama to be installed and runnable. The first-time model pull requires internet access; subsequent fallback generation can run offline.
- API credentials are read from environment variables and must not be committed.
- Keep the server bound to localhost unless you add authentication, rate limiting, and deployment security controls.

## Supported files

See `app/ingest.py` for the authoritative list of supported file extensions.
