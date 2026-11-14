import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx


class ProviderError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, payload, record_id=None):
        record_id = record_id or str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?)", (record_id, kind, json.dumps(payload)))
        return record_id

    def get(self, kind, record_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.connect() as db:
            rows = db.execute("SELECT id, payload FROM records WHERE kind=? ORDER BY rowid DESC LIMIT 100", (kind,)).fetchall()
        return [dict(json.loads(row["payload"]), id=row["id"]) for row in rows]


class LocalLLM:
    def __init__(self, base_url=None, model=None):
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.environ.get("AI_MODEL", "qwen2.5:1.5b")

    def complete(self, messages, schema=None, max_tokens=512):
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": 8192}}
        if schema is not None:
            payload["format"] = schema
        try:
            response = httpx.post(self.base_url + "/api/chat", json=payload, timeout=180)
            response.raise_for_status()
            raw = response.json()
            text = raw["message"]["content"]
            if not isinstance(text, str):
                raise ValueError("Expected textual model output")
            return {"text": text, "input_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count")}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Local model unavailable or returned invalid output. Start Ollama and pull the configured AI_MODEL.") from exc

    def structured(self, system, data, schema):
        result = self.complete([{"role": "system", "content": system},
                                {"role": "user", "content": json.dumps(data)}], schema=schema)
        try:
            value = json.loads(result["text"])
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
        except ValueError as exc:
            raise ProviderError("Model returned malformed structured output.") from exc
