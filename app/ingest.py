import csv
import io
import json
import os
import re

from pypdf import PdfReader

from . import config


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n\n".join(pages)
    if ext in (".txt", ".md", ".log", ".py", ".html", ".xml"):
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".csv":
        rows = []
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.reader(f):
                rows.append(" | ".join(cell.strip() for cell in row))
        return "\n".join(rows)
    if ext == ".json":
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.dumps(json.load(f), indent=2, ensure_ascii=False)
    raise ValueError(f"Unsupported file type: {ext}")


def _split_long(text: str, size: int) -> list[str]:
    words = text.split(" ")
    parts, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > size:
            if cur:
                parts.append(cur)
            cur = w[-size:] if len(w) > size else w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        parts.append(cur)
    return parts


def chunk_text(text: str, docname: str) -> list[dict]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    raw, cur = [], ""
    for para in paragraphs:
        if len(para) > config.CHUNK_SIZE * 2:
            if cur:
                raw.append(cur)
                cur = ""
            raw.extend(_split_long(para, config.CHUNK_SIZE))
        elif len(cur) + len(para) + 2 > config.CHUNK_SIZE:
            raw.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para).strip()
    if cur:
        raw.append(cur)

    chunks = []
    for i, part in enumerate(raw):
        body = part
        if i > 0 and config.CHUNK_OVERLAP > 0 and len(part) < config.CHUNK_SIZE:
            prev_tail = raw[i - 1][-config.CHUNK_OVERLAP:]
            body = prev_tail + " ... " + part
        chunks.append({
            "id": len(chunks),
            "doc": docname,
            "part": i + 1,
            "total": None,
            "text": body,
        })
    total = len(chunks)
    for c in chunks:
        c["total"] = total
    return chunks


def ingest_file(path: str, docname: str) -> list[dict]:
    return chunk_text(extract_text(path), docname)


SUPPORTED_EXTS = {".pdf", ".txt", ".md", ".csv", ".json", ".log", ".py", ".html", ".xml"}


def read_stream_safe(fp) -> bytes:
    buf = io.BytesIO()
    while True:
        b = fp.read(1024 * 1024)
        if not b:
            break
        buf.write(b)
    return buf.getvalue()
