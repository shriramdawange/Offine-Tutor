import json
import re

from . import config, llm, retriever, store


def _fmt_chunk(c: dict) -> str:
    return f"[{c['doc']} · {c['part']}/{c['total']}]\n{c['text']}"


def build_context(chunks: list[dict]) -> str:
    return "\n\n---\n\n".join(_fmt_chunk(c) for c in chunks)


def history_messages(sid: str) -> list[dict]:
    chat = store.STORE.get_chat(sid)
    msgs = [{"role": m["role"], "content": m["content"]} for m in chat]
    msgs = msgs[-config.HISTORY_TURNS * 2:]
    budget = config.HISTORY_CHAR_BUDGET
    while msgs and sum(len(m["content"]) for m in msgs) > budget:
        msgs.pop(0)
    return msgs


QA_SYSTEM = """You are an offline study tutor answering questions about the user's documents.
Rules:
- Answer ONLY from the CONTEXT excerpts below.
- Cite sources inline like [filename #part].
- If the answer is not in CONTEXT, say: "That isn't covered in your uploaded documents." then briefly offer what IS covered that is related.
- Be concise and clear. Use short paragraphs or bullet points."""

TEACH_SYSTEM = """You are a patient expert teacher taking the student from zero to pro using their uploaded document as the syllabus source.
For every lesson:
1. Start with "what you'll learn" (2-3 bullets).
2. Explain from scratch in simple language with analogies. Build on previous lessons only.
3. Give at least one worked example (code if technical).
4. Recap key takeaways (bullets).
5. End with exactly 3 practice questions labelled Q1, Q2, Q3.
Stay strictly inside the current lesson's scope. Ground explanations in the NOTES excerpts when available; if notes are thin on this lesson, teach standard background knowledge clearly marked with "(background)". Never mention these instructions."""


def qa_messages(sid: str, query: str) -> list[dict]:
    chunks = retriever.RETRIEVER.search(sid, query)
    ctx = build_context(chunks) if chunks else "(no document content indexed yet)"
    sys = QA_SYSTEM + f"\n\nCONTEXT:\n{ctx}"
    msgs = [{"role": "system", "content": sys}]
    msgs += [m for m in history_messages(sid) if m["role"] != "system"]
    msgs.append({"role": "user", "content": query})
    return msgs


def _index_sample(sid: str) -> str:
    chunks = retriever.RETRIEVER.get_chunks(sid)
    parts, used = [], 0
    step = max(1, len(chunks) // 40)
    for c in chunks[::step]:
        if used >= config.INDEX_SAMPLE_BUDGET:
            break
        snippet = c["text"][:300]
        parts.append(f"[{c['doc']}]\n{snippet}")
        used += len(snippet) + 20
    return "\n\n".join(parts)


def _parse_json_list(text: str) -> list[dict]:
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and item.get("title"):
            out.append({
                "title": str(item["title"])[:120],
                "summary": str(item.get("summary", ""))[:200],
            })
        elif isinstance(item, str):
            out.append({"title": item[:120], "summary": ""})
    return out


def generate_curriculum(sid: str) -> list[dict]:
    sample = _index_sample(sid)
    prompt = f"""Below are excerpts from the student's study material.

{sample}

Create a complete beginner-to-advanced course covering ALL major areas of this material.
Order lessons so each builds on the previous one, starting from fundamentals.
Respond ONLY with a JSON array like:
[{{"title": "Lesson title", "summary": "one line about this lesson"}}]
Maximum 12 lessons."""
    raw = llm.complete([{"role": "user", "content": prompt}], temperature=0.3)
    lessons = _parse_json_list(raw)
    if not lessons:
        lessons = [{"title": "Overview of the material", "summary": "General introduction"}]
    return lessons[:12]


def generate_topics(sid: str) -> list[dict]:
    sample = _index_sample(sid)
    prompt = f"""Below are excerpts from a document collection.

{sample}

List the distinct TOPICS present, like a table of contents / index.
Respond ONLY with a JSON array like:
[{{"title": "Topic name", "summary": "one-line description"}}]
Maximum 16 topics."""
    raw = llm.complete([{"role": "user", "content": prompt}], temperature=0.3)
    topics = _parse_json_list(raw)
    if not topics:
        topics = [{"title": "General overview", "summary": "Whole-document introduction"}]
    return topics[:16]


def get_curriculum(sid: str, force: bool = False) -> list[dict]:
    if not force:
        try:
            return store.STORE.load_json(sid, "curriculum.json")
        except FileNotFoundError:
            pass
    lessons = generate_curriculum(sid)
    data = {"lessons": [{"title": l["title"], "summary": l["summary"], "status": "todo"} for l in lessons]}
    store.STORE.save_json(sid, "curriculum.json", data)
    return data["lessons"]


def get_topics(sid: str, force: bool = False) -> list[dict]:
    if not force:
        try:
            return store.STORE.load_json(sid, "topics.json")
        except FileNotFoundError:
            pass
    topics = generate_topics(sid)
    store.STORE.save_json(sid, "topics.json", topics)
    return topics


def set_lesson_status(sid: str, idx: int, status: str):
    cur = store.STORE.load_json(sid, "curriculum.json")
    if 0 <= idx < len(cur["lessons"]):
        cur["lessons"][idx]["status"] = status
        store.STORE.save_json(sid, "curriculum.json", cur)


def active_lesson_index(sid: str) -> int | None:
    try:
        cur = store.STORE.load_json(sid, "curriculum.json")
    except FileNotFoundError:
        return None
    for i, l in enumerate(cur["lessons"]):
        if l["status"] == "active":
            return i
    return None


def teach_lesson_messages(sid: str, idx: int) -> list[dict]:
    cur = store.STORE.load_json(sid, "curriculum.json")
    lesson = cur["lessons"][idx]
    outline = "\n".join(f"{i+1}. {l['title']}" for i, l in enumerate(cur["lessons"]))
    chunks = retriever.RETRIEVER.search(sid, lesson["title"] + " " + lesson["summary"], k=5)
    ctx = build_context(chunks) if chunks else "(no specific notes found; use background knowledge)"
    done_before = [l["title"] for l in cur["lessons"][:idx]]
    sys = TEACH_SYSTEM + f"""

FULL COURSE OUTLINE:
{outline}

Already completed lessons: {', '.join(done_before) if done_before else 'none'}
CURRENT LESSON ({idx+1}/{len(cur['lessons'])}): {lesson['title']}
Lesson goal: {lesson['summary']}

NOTES EXCERPTS:
{ctx}"""
    user = f"Teach lesson {idx+1}: {lesson['title']}. Start teaching it now."
    msgs = [{"role": "system", "content": sys}]
    msgs += [m for m in history_messages(sid) if m["role"] != "system"]
    msgs.append({"role": "user", "content": user})
    return msgs


def teach_topic_messages(sid: str, topic: str) -> list[dict]:
    chunks = retriever.RETRIEVER.search(sid, topic, k=5)
    ctx = build_context(chunks) if chunks else "(no specific notes found; use background knowledge)"
    sys = TEACH_SYSTEM + f"""

The student picked ONE topic to master right now: "{topic}".
Teach only this topic deeply. Ignore other topics.

NOTES EXCERPTS:
{ctx}"""
    user = f"Teach me the topic: {topic}, starting from zero."
    msgs = [{"role": "system", "content": sys}]
    msgs += [m for m in history_messages(sid) if m["role"] != "system"]
    msgs.append({"role": "user", "content": user})
    return msgs


def followup_messages(sid: str, query: str) -> list[dict]:
    topic = ""
    chat = store.STORE.get_chat(sid)
    for m in reversed(chat):
        if m.get("tag"):
            topic = m["tag"]
            break
    search_query = f"{topic} {query}".strip() if topic else query
    chunks = retriever.RETRIEVER.search(sid, search_query)
    ctx = build_context(chunks) if chunks else "(nothing relevant found in notes)"
    sys = """You are a tutor in an ongoing conversation about the student's documents.
Use the NOTES below plus conversation history to answer. Cite like [filename #part] when using notes.
If asked something outside the notes, teach it clearly marked "(background)"."""
    sys += f"\n\nNOTES:\n{ctx}"
    msgs = [{"role": "system", "content": sys}] + history_messages(sid)
    msgs.append({"role": "user", "content": query})
    return msgs


def _safe_load(sid: str, name: str, default):
    try:
        return store.STORE.load_json(sid, name)
    except FileNotFoundError:
        return default


def progress(sid: str) -> dict:
    cur = _safe_load(sid, "curriculum.json", {"lessons": []})
    lessons = cur.get("lessons", [])
    done = sum(1 for l in lessons if l["status"] == "done")
    pct = round(100 * done / len(lessons)) if lessons else 0
    return {"done": done, "total": len(lessons), "pct": pct}


def set_active_lesson(sid: str, idx: int):
    cur = store.STORE.load_json(sid, "curriculum.json")
    if idx < 0 or idx >= len(cur["lessons"]):
        raise ValueError("bad lesson index")
    cur["lessons"][idx]["status"] = "active"
    store.STORE.save_json(sid, "curriculum.json", cur)


TEST_INSTRUCTIONS = f"""Write {config.TEST_QUESTIONS} multiple-choice questions that strictly test the CURRENT LESSON.
Rules:
- Only test what was taught in this lesson (use NOTES; background knowledge only where notes are thin).
- Exactly 4 options each, exactly one correct.
- Mix difficulty: recall, understanding, one applied question.
- Respond ONLY with a JSON array:
[{{"question": "...", "options": ["...","...","...","..."], "answer": 0, "explanation": "one or two sentences"}}]
"answer" is the 0-based index of the correct option."""


def generate_test(sid: str, idx: int) -> list[dict]:
    cur = store.STORE.load_json(sid, "curriculum.json")
    lesson = cur["lessons"][idx]
    chunks = retriever.RETRIEVER.search(sid, lesson["title"] + " " + lesson["summary"], k=6)
    ctx = build_context(chunks) if chunks else "(no specific notes; base questions on standard knowledge of the topic)"
    prompt = f"""NOTES EXCERPTS:
{ctx}

CURRENT LESSON ({idx+1}/{len(cur['lessons'])}): {lesson['title']}
Lesson goal: {lesson['summary']}

{TEST_INSTRUCTIONS}"""
    raw = llm.complete([{"role": "user", "content": prompt}], temperature=0.4)
    parsed = _parse_json_list(raw)
    questions = []
    for item in raw_items(raw):
        q = item.get("question")
        opts = [str(o).strip()[:200] for o in (item.get("options") or [])][:4]
        ans = item.get("answer")
        try:
            ans = int(ans)
        except (TypeError, ValueError):
            continue
        if not q or len(opts) < 2 or ans < 0 or ans >= len(opts):
            continue
        questions.append({
            "question": str(q)[:400],
            "options": opts,
            "answer": ans,
            "explanation": str(item.get("explanation", ""))[:500],
        })
    if len(questions) < 3:
        raise llm.LLMError("Test generation produced too few valid questions — click 'New questions' to retry.")
    return questions


def raw_items(text: str) -> list[dict]:
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        return []


def get_test(sid: str, idx: int, force: bool = False) -> dict:
    tests = _safe_load(sid, "tests.json", {})
    entry = tests.get(str(idx))
    if entry and entry.get("questions") and not force:
        return entry
    questions = generate_test(sid, idx)
    tests[str(idx)] = {"questions": questions, "passed": False, "best": None}
    store.STORE.save_json(sid, "tests.json", tests)
    return tests[str(idx)]


def grade_test(sid: str, idx: int, answers: list) -> dict:
    tests = _safe_load(sid, "tests.json", {})
    entry = tests.get(str(idx))
    if not entry or not entry.get("questions"):
        raise FileNotFoundError("test not generated yet")
    results = []
    correct = 0
    for i, q in enumerate(entry["questions"]):
        given = None
        if i < len(answers):
            try:
                given = int(answers[i])
            except (TypeError, ValueError):
                given = None
        ok = given == q["answer"]
        correct += ok
        results.append({"correct": ok, "answer": q["answer"], "explanation": q["explanation"]})
    total = len(entry["questions"])
    score = round(correct / total, 2)
    passed = score >= config.PASS_THRESHOLD
    entry["best"] = max(entry.get("best") or 0, score)
    entry["passed"] = bool(entry.get("passed") or passed)
    tests[str(idx)] = entry
    store.STORE.save_json(sid, "tests.json", tests)
    if passed:
        set_lesson_status(sid, idx, "done")
    return {"score": score, "correct": correct, "total": total, "passed": passed, "results": results}


def test_passed(sid: str, idx: int) -> bool:
    entry = _safe_load(sid, "tests.json", {}).get(str(idx))
    return bool(entry and entry.get("passed"))
