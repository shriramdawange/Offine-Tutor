import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, ingest, llm, retriever, store, tutor, websearch

app = FastAPI(title="API-Integrated Tutor")

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SessionIn(BaseModel):
    name: str


class SettingsIn(BaseModel):
    test_enabled: bool | None = None


class ChatIn(BaseModel):
    action: str = "ask"
    message: str | None = None
    topic: str | None = None
    lesson: int | None = None
    pane: str | None = None


class SubmitIn(BaseModel):
    answers: list


class ModelSelectIn(BaseModel):
    model: str = Field(min_length=1, max_length=160)


def _safe_load(sid: str, name: str, default):
    try:
        return store.STORE.load_json(sid, name)
    except FileNotFoundError:
        return default


def _session_or_404(sid: str) -> dict:
    meta = store.STORE.get_meta(sid)
    if not meta:
        raise HTTPException(404, "session not found")
    return meta


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status")
def status():
    return {
        **llm.provider_status(),
        "model": config.MODEL,
        "ollama": llm.model_available(),
        "web_search_enabled": config.WEB_SEARCH_ENABLED,
        "sessions": len(store.STORE.list_sessions()),
    }


@app.get("/api/models")
def models():
    return {
        "cloud_configured": bool(config.API_KEY),
        "cloud_model": config.API_MODEL,
        "ollama_url": config.OLLAMA_URL,
        "ollama_models": llm.available_local_models(),
        "selected_local_model": llm.provider_status()["local_model"],
    }



@app.get("/api/provider/models")
def provider_models():
    """List model IDs available to the configured Groq API key."""
    if not config.API_KEY:
        return {"configured": False, "provider": "Groq", "active_model": config.API_MODEL, "models": []}
    try:
        import requests
        response = requests.get(
            f"{config.API_BASE_URL}/models",
            headers={"Authorization": f"Bearer {config.API_KEY}"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        # /models also returns audio, speech, and safety models. Keep only
        # general-purpose text models suitable for /chat/completions.
        models = sorted({
            str(item.get("id", "")).strip()
            for item in response.json().get("data", [])
            if isinstance(item, dict)
            and item.get("id")
            and int(item.get("context_window") or 0) >= 4096
            and not any(part in str(item.get("id", "")).lower() for part in ("whisper", "orpheus", "guard", "speech"))
        })
        return {"configured": True, "provider": "Groq", "active_model": config.API_MODEL, "models": models}
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        raise HTTPException(502, f"Could not load Groq models (HTTP {status_code or 'network error'}). Check API key and connectivity.") from exc


@app.put("/api/provider/model")
def select_provider_model(body: ModelSelectIn):
    """Change the cloud model for this running server process."""
    if not config.API_KEY:
        raise HTTPException(400, "Add your Groq API key to .env and restart OfflineTutor.")
    try:
        import requests
        response = requests.get(
            f"{config.API_BASE_URL}/models",
            headers={"Authorization": f"Bearer {config.API_KEY}"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        available = {str(item.get("id", "")) for item in response.json().get("data", []) if isinstance(item, dict)}
    except Exception as exc:
        raise HTTPException(502, "Unable to verify Groq model access. Check the API key and connection.") from exc
    if body.model not in available:
        raise HTTPException(400, "That model is not available to this Groq API key.")
    config.API_MODEL = body.model
    return {"active_model": config.API_MODEL, "note": "Runtime selection only. Set API_MODEL in .env to keep it after restart."}


@app.post("/api/provider/test")
def test_provider():
    if not config.API_KEY:
        raise HTTPException(400, "Groq API key is missing. Add API_KEY to .env.")
    try:
        import requests
        response = requests.post(
            f"{config.API_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"},
            json={"model": config.API_MODEL, "messages": [{"role": "user", "content": "Reply with OK."}], "max_completion_tokens": 8, "temperature": 0},
            timeout=(5, config.API_TIMEOUT),
        )
        response.raise_for_status()
        return {"ok": True, "provider": "Groq", "model": config.API_MODEL}
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        raise HTTPException(502, f"Groq test failed (HTTP {status_code or 'network error'}). Check model access, key, and network.") from exc


@app.get("/api/sessions")
def list_sessions():
    return store.STORE.list_sessions()


@app.post("/api/sessions")
def create_session(body: SessionIn):
    return store.STORE.create(body.name)


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    meta = _session_or_404(sid)
    out = dict(meta)
    lessons = _safe_load(sid, "curriculum.json", {"lessons": []}).get("lessons", [])
    tests = _safe_load(sid, "tests.json", {})
    for i, l in enumerate(lessons):
        entry = tests.get(str(i))
        l["test_passed"] = bool(entry and entry.get("passed"))
    out["curriculum"] = lessons
    out["topics"] = _safe_load(sid, "topics.json", [])
    out["chat"] = _safe_load(sid, "chat.json", [])
    out["progress"] = tutor.progress(sid)
    out["test_enabled"] = bool(meta.get("test_enabled"))
    return out


@app.patch("/api/sessions/{sid}/settings")
def update_settings(sid: str, body: SettingsIn):
    kw = {}
    if body.test_enabled is not None:
        kw["test_enabled"] = body.test_enabled
    if not kw:
        raise HTTPException(400, "nothing to update")
    meta = store.STORE.update_meta(sid, **kw)
    return {"test_enabled": bool(meta.get("test_enabled"))}


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    if not store.STORE.exists(sid):
        raise HTTPException(404, "session not found")
    retriever.RETRIEVER.invalidate(sid)
    store.STORE.delete(sid)
    return {"deleted": sid}


@app.delete("/api/sessions")
def wipe_all():
    retriever.RETRIEVER.wipe()
    store.STORE.wipe_all()
    return {"deleted": "all"}


@app.post("/api/sessions/{sid}/upload")
async def upload(sid: str, files: list[UploadFile] = File(...)):
    meta = _session_or_404(sid)
    docs_dir = os.path.join(config.DATA_DIR, sid, "docs")
    os.makedirs(docs_dir, exist_ok=True)

    chunks = _safe_load(sid, "chunks.json", [])
    results = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ingest.SUPPORTED_EXTS:
            results.append({"file": f.filename, "ok": False, "error": f"unsupported type {ext}"})
            continue
        raw = ingest.read_stream_safe(f.file)
        if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
            results.append({"file": f.filename, "ok": False, "error": "file too large"})
            continue
        safe_name = os.path.basename(f.filename).replace("\\", "_").replace("/", "_")
        chunks = [c for c in chunks if c["doc"] != safe_name]
        meta["docs"] = [d for d in meta.get("docs", []) if d["name"] != safe_name]
        path = os.path.join(docs_dir, safe_name)
        with open(path, "wb") as out:
            out.write(raw)
        new_chunks = ingest.ingest_file(path, safe_name)
        for c in new_chunks:
            c["id"] = len(chunks)
            chunks.append(c)
        docs = meta.setdefault("docs", [])
        docs.append({"name": safe_name, "chunks": len(new_chunks), "bytes": len(raw)})
        results.append({"file": safe_name, "ok": True, "chunks": len(new_chunks)})

    store.STORE.save_json(sid, "chunks.json", chunks)
    store.STORE.update_meta(sid, docs=meta.get("docs", []), status="ready" if chunks else "empty")
    retriever.RETRIEVER.invalidate(sid)

    if chunks and not (_safe_load(sid, "curriculum.json", None) or _safe_load(sid, "topics.json", None)):
        try:
            tutor.get_curriculum(sid, force=False)
            tutor.get_topics(sid, force=False)
        except llm.LLMError:
            pass
    return {"results": results, "total_chunks": len(chunks)}


@app.delete("/api/sessions/{sid}/docs/{name}")
def delete_doc(sid: str, name: str):
    meta = _session_or_404(sid)
    chunks = [c for c in _safe_load(sid, "chunks.json", []) if c["doc"] != name]
    store.STORE.save_json(sid, "chunks.json", chunks)
    docs = [d for d in meta.get("docs", []) if d["name"] != name]
    store.STORE.update_meta(sid, docs=docs, status="ready" if chunks else "empty")
    path = os.path.join(config.DATA_DIR, sid, "docs", name)
    if os.path.isfile(path):
        os.remove(path)
    retriever.RETRIEVER.invalidate(sid)
    return {"deleted": name, "remaining_chunks": len(chunks)}


@app.post("/api/sessions/{sid}/index/rebuild")
def rebuild_index(sid: str):
    _session_or_404(sid)
    n_chunks = len(_safe_load(sid, "chunks.json", []))
    if n_chunks == 0:
        raise HTTPException(400, "upload documents first")
    lessons = tutor.get_curriculum(sid, force=True)
    topics = tutor.get_topics(sid, force=True)
    return {"lessons": lessons, "topics": topics, "chunks": n_chunks}


@app.get("/api/sessions/{sid}/lesson/{idx}/gate")
def lesson_gate(sid: str, idx: int):
    _session_or_404(sid)
    required = bool(store.STORE.get_meta(sid).get("test_enabled"))
    passed = tutor.test_passed(sid, idx) if required else True
    return {"required": required, "passed": passed}


@app.post("/api/sessions/{sid}/test/{idx}")
def get_test(sid: str, idx: int, force: bool = False):
    _session_or_404(sid)
    if not _safe_load(sid, "curriculum.json", None):
        raise HTTPException(400, "Build the course first (Fresh → Pro → Build my course)")
    try:
        entry = tutor.get_test(sid, idx, force=force)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    questions = [
        {"question": q["question"], "options": q["options"]}
        for q in entry["questions"]
    ]
    return {
        "questions": questions,
        "passed": entry.get("passed", False),
        "best": entry.get("best"),
    }


@app.post("/api/sessions/{sid}/test/{idx}/submit")
def submit_test(sid: str, idx: int, body: SubmitIn):
    _session_or_404(sid)
    try:
        result = tutor.grade_test(sid, idx, body.answers)
    except FileNotFoundError:
        raise HTTPException(400, "generate the test first")
    return result


def _last_tag(sid: str) -> str | None:
    chat = _safe_load(sid, "chat.json", [])
    for m in reversed(chat):
        if m.get("role") == "assistant" and m.get("tag"):
            return m["tag"]
    return None


def _plan(sid: str, body: ChatIn):
    temp = config.TEMP_QA
    tag = None
    pane = body.pane or ("course" if body.action in ("start_course", "next_lesson", "goto_lesson") else "topics" if body.action == "teach_topic" else "ask")
    user_text = ""
    done_text = None

    if body.action == "start_course":
        cur = tutor.get_curriculum(sid, force=False)
        nxt = next((i for i, l in enumerate(cur) if l["status"] != "done"), 0)
        tutor.set_active_lesson(sid, nxt)
        msgs = tutor.teach_lesson_messages(sid, nxt)
        tag, temp = f"course:{nxt}", config.TEMP_TEACH
        user_text = "[Course] Start the course"
    elif body.action == "next_lesson":
        cur = store.STORE.load_json(sid, "curriculum.json")["lessons"]
        active = tutor.active_lesson_index(sid)
        nxt = next((i for i, l in enumerate(cur) if l["status"] != "done"), None)
        if nxt is None:
            done_text = "Course complete — every lesson finished! Ask me anything to review."
            user_text = "[Course] Next lesson please"
            return None, tag, temp, pane, user_text, done_text
        for i in range(nxt):
            if cur[i]["status"] != "done":
                tutor.set_lesson_status(sid, i, "done")
        tutor.set_active_lesson(sid, nxt)
        msgs = tutor.teach_lesson_messages(sid, nxt)
        tag, temp = f"course:{nxt}", config.TEMP_TEACH
        user_text = "[Course] Next lesson please"
    elif body.action == "goto_lesson":
        cur = store.STORE.load_json(sid, "curriculum.json")["lessons"]
        idx = body.lesson if body.lesson is not None else 0
        if idx < 0 or idx >= len(cur):
            raise ValueError("bad lesson index")
        tutor.set_active_lesson(sid, idx)
        msgs = tutor.teach_lesson_messages(sid, idx)
        tag, temp = f"course:{idx}", config.TEMP_TEACH
        user_text = f"[Course] Open lesson {idx+1}: {cur[idx]['title']}"
    elif body.action == "teach_topic":
        topic = (body.topic or "").strip() or "General overview"
        tutor.get_topics(sid, force=False)
        msgs = tutor.teach_topic_messages(sid, topic)
        tag, temp = f"topic:{topic}", config.TEMP_TEACH
        user_text = f"[Topic] Teach me: {topic}"
    else:
        query = (body.message or "").strip()
        if not query:
            raise ValueError("empty message")
        last = _last_tag(sid)
        if last and (last.startswith("course:") or last.startswith("topic:")):
            msgs = tutor.followup_messages(sid, query)
        else:
            chunks = retriever.RETRIEVER.search(sid, query)
            # Search online only when the uploaded-document index has no matching chunks.
            web_results = websearch.search(query) if not chunks else []
            msgs = tutor.qa_messages(sid, query, web_results=web_results)
            if web_results:
                body._web_sources = web_results
        user_text = query

    return msgs, tag, temp, pane, user_text, done_text


@app.post("/api/chat/stream")
async def chat_stream(sid: str, body: ChatIn):
    if not store.STORE.exists(sid):
        raise HTTPException(404, "session not found")

    try:
        msgs, tag, temp, pane, user_text, done_text = _plan(sid, body)
    except FileNotFoundError:
        raise HTTPException(400, "Upload documents and build the course/index first")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))

    if msgs is None:
        store.STORE.append_chat(sid, "user", user_text, pane=pane)
        store.STORE.append_chat(sid, "assistant", done_text, pane=pane)
        return StreamingResponse(iter([done_text]), media_type="text/plain; charset=utf-8")

    def gen():
        full = []
        ok = True
        web_sources = getattr(body, "_web_sources", [])
        try:
            for token in llm.stream_chat(msgs, temperature=temp):
                full.append(token)
                yield token
            if web_sources:
                appendix = "\n\n### Web sources\n" + "\n".join(
                    f"- [{item['title']}]({item['url']})" for item in web_sources
                )
                full.append(appendix)
                yield appendix
        except llm.LLMError as e:
            ok = False
            yield f"\n\n__ERROR__ {e}"
        if ok:
            store.STORE.append_chat(sid, "user", user_text, pane=pane)
            store.STORE.append_chat(sid, "assistant", "".join(full), tag=tag, pane=pane)

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
