# 📚 OfflineTutor

A **100% offline** study companion. Upload PDFs/notes, and a local LLM (Qwen2.5-Coder 3B via Ollama)
either answers your questions with citations, or teaches you the material from zero to pro.

## Quick start

1. Double-click **`setup.bat`** (one time only).
2. From then on, **`start.bat` is all you need** — even at the office:
   - starts Ollama automatically if it's not running
   - starts the web server (skips if already running)
   - opens http://localhost:8000 in your browser
3. To shut everything down: **`stop.bat`**

No internet needed at any point.

## The two learning modes

| Mode | What it does |
|---|---|
| 💬 **Ask & Learn** | Grounded Q&A over your documents with `[filename #part]` citations. If it's not in your docs, it says so. |
| 🎓 **Fresh → Pro** | Builds a full course plan from your docs, then teaches lesson-by-lesson — analogies, worked examples, recaps, and practice questions. Progress bar, previous/next navigation, jump to any lesson. |
| 📑 **Pick Topics** | Generates a document index/table-of-contents. You pick exactly what you want to master; the tutor deep-dives that topic only. |

The chat input works in every tab — questions asked during a lesson or topic stay in that context automatically (each mode keeps its own conversation thread).

## Test gate (MCQ quizzes)

Toggle **🧪 Test gate** in the Fresh → Pro sidebar:

- **OFF (default)** — lessons flow one after another, no tests.
- **ON** — the tutor writes a fresh 5-question MCQ test from your documents after each lesson; you must score ≥60% to unlock the next lesson. Wrong answers show explanations, and you can retry or ask for entirely new questions.
- Answer keys never leave the server — grading happens locally in `tests.json`.

## Memory & privacy guarantees (by design)

- The LLM is called **statelessly** every time (`POST /api/chat`) — Ollama keeps **no conversation memory**, nothing is stored in any "universal model memory".
- All context lives in **your session folder**: `data/sessions/<id>/`
  - `docs/` original uploads · `chunks.json` text chunks · `chat.json` history · `curriculum.json` / `topics.json` progress
- **Deleting a session wipes everything**: its folder on disk, its RAM cache (BM25 index + chunk cache), and chat history are all removed immediately.
- "Delete ALL data" in the sidebar nukes `data/sessions` completely.

## Lightweight by design

- Retrieval uses a **pure-Python BM25 index** written from scratch — no embedding models, no GPU, no numpy, no vector DB.
- Model runs via **Ollama**, which auto-unloads the model from RAM after ~20 min idle (`KEEP_ALIVE` in `app/config.py`). Idle RAM ≈ 0 for the LLM; active ≈ ~2 GB for the 3B Q4 model.
- Context is capped: top-4 retrieved chunks (~5 KB), last 8 turns of history (~6 KB), 4096-token context window. RAM stays flat even after hours of use.
- Responses stream token-by-token so long lessons feel instant.

## Tuning knobs — `app/config.py`

| Setting | Default | Meaning |
|---|---|---|
| `MODEL` | qwen2.5-coder:3b… | any Ollama model name works |
| `NUM_CTX` | 4096 | context window (raise if you have RAM headroom) |
| `TOP_K` | 4 | chunks retrieved per question |
| `CHUNK_SIZE` | 1100 chars | document chunk size |
| `KEEP_ALIVE` | 20m | how long the model stays loaded while idle |
| `HISTORY_TURNS` | 8 | conversation turns sent back to the model |

## Supported files

`.pdf` `.txt` `.md` `.csv` `.json` `.log` `.py` `.html` `.xml`

> Tip: the project sits inside OneDrive — consider moving it out (or pausing sync) so OneDrive doesn't sync the venv/session data.
