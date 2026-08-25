import math
import re
import threading
from collections import Counter

from . import config, store

_word = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _word.findall(text.lower())


class BM25:
    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs_tokens)
        self.avgdl = sum(len(d) for d in docs_tokens) / max(self.n, 1) or 1.0
        self.doc_len = [len(d) for d in docs_tokens]
        self.tfs = [Counter(d) for d in docs_tokens]
        df = Counter()
        for tf in self.tfs:
            for term in tf:
                df[term] += 1
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, k: int) -> list[int]:
        q = tokenize(query)
        if not q or self.n == 0:
            return []
        scores = []
        qc = Counter(q)
        for i in range(self.n):
            tf_map = self.tfs[i]
            dl = self.doc_len[i] or 1
            s = 0.0
            for term, qtf in qc.items():
                tf = tf_map.get(term)
                if not tf:
                    continue
                idf = self.idf.get(term, 0.0)
                s += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        return [i for s, i in scores[:k] if s > 0]


class Retriever:
    def __init__(self):
        self._cache: dict[str, tuple[list[dict], BM25]] = {}
        self._lock = threading.Lock()

    def invalidate(self, sid: str):
        with self._lock:
            self._cache.pop(sid, None)

    def wipe(self):
        with self._lock:
            self._cache.clear()

    def get_chunks(self, sid: str) -> list[dict]:
        chunks = store.STORE.load_json(sid, "chunks.json")
        return chunks

    def search(self, sid: str, query: str, k: int = config.TOP_K) -> list[dict]:
        with self._lock:
            cached = self._cache.get(sid)
            if cached is None:
                try:
                    chunks = self.get_chunks(sid)
                except FileNotFoundError:
                    return []
                tokens = [tokenize(c["text"]) for c in chunks]
                cached = (chunks, BM25(tokens))
                self._cache[sid] = cached
        chunks, index = cached
        idxs = index.search(query, k)
        return [chunks[i] for i in idxs]


RETRIEVER = Retriever()
