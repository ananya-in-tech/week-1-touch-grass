"""Tiny SQLite store. Everything lives in data/ on this computer."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS quests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    minutes         INTEGER NOT NULL,
    setting         TEXT NOT NULL,
    energy          TEXT NOT NULL,
    title           TEXT NOT NULL,
    intro           TEXT NOT NULL,
    finds           TEXT NOT NULL,          -- JSON [{what, hint}]
    sit_spot        TEXT NOT NULL,
    turn_back       TEXT NOT NULL,
    source          TEXT NOT NULL,          -- ai | fallback
    safety_note     TEXT,
    status          TEXT NOT NULL DEFAULT 'ready',   -- ready | out | back | done
    started_at      TEXT,
    returned_at     TEXT,
    screen_seconds  INTEGER,
    heard           TEXT,
    journal         TEXT,
    journal_source  TEXT
);
CREATE TABLE IF NOT EXISTS photos (
    quest_id    INTEGER NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    file        TEXT NOT NULL,
    match       TEXT NOT NULL,              -- yes | maybe | no | unchecked
    saw         TEXT,
    checked_at  TEXT NOT NULL,
    PRIMARY KEY (quest_id, idx)
);
CREATE TABLE IF NOT EXISTS ai_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    latency_ms  INTEGER NOT NULL,
    ok          INTEGER NOT NULL,
    error       TEXT
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class DB:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # quests -----------------------------------------------------------------------------------

    def insert_quest(self, **q) -> int:
        q["finds"] = json.dumps(q["finds"])
        cols = ", ".join(q)
        with self.conn() as c:
            cur = c.execute(f"INSERT INTO quests (created_at, {cols}) VALUES (?, {', '.join('?' * len(q))})",
                            (now_iso(), *q.values()))
            return cur.lastrowid

    def quest(self, qid: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM quests WHERE id = ?", (qid,)).fetchone()
            if not row:
                return None
            photos = c.execute("SELECT * FROM photos WHERE quest_id = ? ORDER BY idx", (qid,)).fetchall()
        q = dict(row)
        q["finds"] = json.loads(q["finds"])
        q["photos"] = [dict(p) for p in photos]
        return q

    def update_quest(self, qid: int, **fields) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.conn() as c:
            c.execute(f"UPDATE quests SET {sets} WHERE id = ?", (*fields.values(), qid))

    def quests(self, status: str | None = None, limit: int = 50) -> list[dict]:
        sql, args = "SELECT id FROM quests", []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        with self.conn() as c:
            ids = [r["id"] for r in c.execute(sql, (*args, limit))]
        return [self.quest(i) for i in ids]

    def upsert_photo(self, qid: int, idx: int, file: str, match: str, saw: str | None) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO photos (quest_id, idx, file, match, saw, checked_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (qid, idx, file, match, saw, now_iso()))

    def log_ai(self, kind: str, latency_ms: int, ok: bool, error: str | None = None) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO ai_calls (at, kind, latency_ms, ok, error) VALUES (?, ?, ?, ?, ?)",
                      (now_iso(), kind, latency_ms, int(ok), (error or "")[:200] or None))

    def stats(self) -> dict:
        with self.conn() as c:
            done = c.execute("SELECT started_at, returned_at, screen_seconds FROM quests WHERE status = 'done'").fetchall()
            found = c.execute("SELECT COUNT(*) FROM photos WHERE match = 'yes'").fetchone()[0]
            ai = c.execute("SELECT kind, COUNT(*), AVG(latency_ms), SUM(ok) FROM ai_calls GROUP BY kind").fetchall()
        outside = sum(int((parse_iso(r["returned_at"]) - parse_iso(r["started_at"])).total_seconds())
                      for r in done if r["started_at"] and r["returned_at"])
        screen = sum(r["screen_seconds"] or 0 for r in done)
        return {
            "quests_done": len(done),
            "outside_seconds": outside,
            "screen_seconds": screen,
            "finds_confirmed": found,
            "ai": [{"kind": k, "calls": n, "avg_latency_ms": int(avg or 0), "ok_rate": round((ok or 0) / n, 2)}
                   for k, n, avg, ok in ai],
        }
