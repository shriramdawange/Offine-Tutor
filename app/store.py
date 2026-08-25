import json
import os
import shutil
import threading
import time
import uuid

from . import config


class Store:
    def __init__(self):
        self._lock = threading.Lock()
        os.makedirs(config.DATA_DIR, exist_ok=True)

    def _dir(self, sid: str) -> str:
        if not re_valid(sid):
            raise ValueError("bad session id")
        return os.path.join(config.DATA_DIR, sid)

    @staticmethod
    def _path(sid: str, name: str) -> str:
        return os.path.join(config.DATA_DIR, sid, name)

    def create(self, name: str) -> dict:
        sid = uuid.uuid4().hex[:12]
        with self._lock:
            os.makedirs(self._dir(sid), exist_ok=True)
            meta = {
                "id": sid,
                "name": name.strip() or f"Session {sid[:6]}",
                "created": time.time(),
                "status": "empty",
                "docs": [],
                "test_enabled": False,
            }
            self.save_json(sid, "meta.json", meta)
            self.save_json(sid, "chat.json", [])
        return meta

    def exists(self, sid: str) -> bool:
        return os.path.isdir(self._dir(sid))

    def get_meta(self, sid: str) -> dict | None:
        try:
            return self.load_json(sid, "meta.json")
        except FileNotFoundError:
            return None

    def list_sessions(self) -> list[dict]:
        out = []
        with self._lock:
            for sid in sorted(os.listdir(config.DATA_DIR)):
                m = self.get_meta(sid)
                if m:
                    out.append(m)
        return sorted(out, key=lambda m: -m.get("created", 0))

    def save_json(self, sid: str, name: str, data):
        tmp = self._path(sid, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self._path(sid, name))

    def load_json(self, sid: str, name: str):
        with open(self._path(sid, name), encoding="utf-8") as f:
            return json.load(f)

    def update_meta(self, sid: str, **kw) -> dict:
        with self._lock:
            meta = self.load_json(sid, "meta.json")
            meta.update(kw)
            self.save_json(sid, "meta.json", meta)
        return meta

    def append_chat(self, sid: str, role: str, content: str, tag: str | None = None, pane: str | None = None):
        with self._lock:
            chat = self.load_json(sid, "chat.json")
            msg = {"role": role, "content": content, "ts": time.time()}
            if tag:
                msg["tag"] = tag
            if pane:
                msg["pane"] = pane
            chat.append(msg)
            self.save_json(sid, "chat.json", chat)

    def get_chat(self, sid: str) -> list[dict]:
        return self.load_json(sid, "chat.json")

    def delete(self, sid: str):
        with self._lock:
            shutil.rmtree(os.path.join(config.DATA_DIR, sid), ignore_errors=True)

    def wipe_all(self):
        with self._lock:
            shutil.rmtree(config.DATA_DIR, ignore_errors=True)
            os.makedirs(config.DATA_DIR, exist_ok=True)


def re_valid(sid: str) -> bool:
    return bool(sid) and all(c in "0123456789abcdef" for c in sid) and len(sid) == 12


STORE = Store()
