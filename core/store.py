"""SQLite persistence: run history + web-fetch cache.

Two tables in one DB file (path from GROUNDWORK_DB):
  - runs:        one row per research run (question, summary metrics, full
                 result + trace as JSON) so the dashboard can show history.
  - fetch_cache: cleaned page text keyed by URL, so repeated fetches of the
                 same source within a TTL don't re-hit the network.

Plain stdlib sqlite3; each call opens its own connection (the API runs research
in worker threads).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    question TEXT NOT NULL,
    mode TEXT,
    answer TEXT,
    grounding_verified INTEGER,
    grounding_total INTEGER,
    cost_usd REAL,
    n_tasks INTEGER,
    n_accepted INTEGER,
    n_revised INTEGER,
    result_json TEXT,
    trace_json TEXT
);
CREATE TABLE IF NOT EXISTS fetch_cache (
    url TEXT PRIMARY KEY,
    title TEXT,
    text TEXT,
    fetched_at REAL NOT NULL
);
"""


def default_db_path() -> str:
    return os.environ.get("GROUNDWORK_DB") or str(Path.cwd() / "groundwork.db")


def _conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #

def save_run(path: str, question: str, mode: str, result: dict) -> int:
    workers = result.get("worker_results", [])
    verified = sum(w.get("grounding", {}).get("verified", 0) for w in workers)
    total = sum(w.get("grounding", {}).get("total", 0) for w in workers)
    with _conn(path) as conn:
        cur = conn.execute(
            "INSERT INTO runs (created_at, question, mode, answer, grounding_verified, "
            "grounding_total, cost_usd, n_tasks, n_accepted, n_revised, result_json, trace_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), question, mode, result.get("answer", ""), verified, total,
             result.get("cost", {}).get("total_usd", 0.0), result.get("n_tasks", 0),
             result.get("n_accepted", 0), result.get("n_revised", 0),
             json.dumps(result, default=str), json.dumps(result.get("trace", []), default=str)),
        )
        return int(cur.lastrowid)


def list_runs(path: str, limit: int = 50) -> list[dict]:
    with _conn(path) as conn:
        rows = conn.execute(
            "SELECT id, created_at, question, mode, grounding_verified, grounding_total, "
            "cost_usd, n_tasks, n_accepted, n_revised FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(path: str, run_id: int) -> dict | None:
    with _conn(path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["result"] = json.loads(d.pop("result_json") or "{}")
    d["trace"] = json.loads(d.pop("trace_json") or "[]")
    return d


# --------------------------------------------------------------------------- #
# Fetch cache
# --------------------------------------------------------------------------- #

@dataclass
class CachedPage:
    url: str
    title: str
    text: str
    fetched_at: float


def cache_get(path: str, url: str, ttl: float = 86400.0) -> CachedPage | None:
    with _conn(path) as conn:
        row = conn.execute("SELECT * FROM fetch_cache WHERE url = ?", (url,)).fetchone()
    if not row:
        return None
    if time.time() - row["fetched_at"] > ttl:
        return None
    return CachedPage(url=row["url"], title=row["title"], text=row["text"], fetched_at=row["fetched_at"])


def cache_put(path: str, url: str, title: str, text: str) -> None:
    with _conn(path) as conn:
        conn.execute(
            "INSERT INTO fetch_cache (url, title, text, fetched_at) VALUES (?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, text=excluded.text, "
            "fetched_at=excluded.fetched_at",
            (url, title, text, time.time()),
        )
