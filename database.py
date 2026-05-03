import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "studio.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id                     TEXT PRIMARY KEY,
            name                   TEXT NOT NULL,
            description            TEXT DEFAULT '',
            notion_characters_db   TEXT DEFAULT '',
            notion_scenes_db       TEXT DEFAULT '',
            notion_page_id         TEXT DEFAULT '',
            created_at             TEXT NOT NULL,
            updated_at             TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS characters (
            id                 TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            name               TEXT NOT NULL,
            voice_id           TEXT DEFAULT '',
            reference_image    TEXT DEFAULT '',
            description        TEXT DEFAULT '',
            is_main_character  INTEGER DEFAULT 0,
            notion_page_id     TEXT DEFAULT '',
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scenes (
            id             TEXT PRIMARY KEY,
            project_id     TEXT NOT NULL,
            scene_number   INTEGER DEFAULT 0,
            title          TEXT DEFAULT '',
            script         TEXT DEFAULT '',
            scene_type     TEXT DEFAULT 'Dialogue',
            model          TEXT DEFAULT 'veo-3',
            duration       TEXT DEFAULT '10s',
            resolution     TEXT DEFAULT '720p',
            characters     TEXT DEFAULT '[]',
            status         TEXT DEFAULT 'Draft',
            notion_page_id TEXT DEFAULT '',
            video_url      TEXT DEFAULT '',
            thumbnail_url  TEXT DEFAULT '',
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS video_jobs (
            id                  TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL,
            scene_id            TEXT DEFAULT '',
            higgsfield_job_id   TEXT DEFAULT '',
            status              TEXT DEFAULT 'pending',
            prompt              TEXT DEFAULT '',
            model               TEXT DEFAULT 'veo-3',
            duration            TEXT DEFAULT '10s',
            resolution          TEXT DEFAULT '720p',
            video_url           TEXT DEFAULT '',
            local_path          TEXT DEFAULT '',
            error_message       TEXT DEFAULT '',
            reference_image_url TEXT DEFAULT '',
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audio_jobs (
            id           TEXT PRIMARY KEY,
            project_id   TEXT NOT NULL,
            scene_id     TEXT DEFAULT '',
            text_content TEXT DEFAULT '',
            voice_id     TEXT DEFAULT '',
            voice_name   TEXT DEFAULT '',
            status       TEXT DEFAULT 'pending',
            audio_file   TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return datetime.utcnow().isoformat()


# ── Generic helpers ────────────────────────────────────────────────────────────

def insert(table: str, data: dict):
    conn = get_db()
    keys = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    conn.close()


def select_all(table: str, where: str = "", params: list = None) -> list:
    conn = get_db()
    q = f"SELECT * FROM {table}"
    if where:
        q += f" WHERE {where}"
    rows = [dict(r) for r in conn.execute(q, params or []).fetchall()]
    conn.close()
    return rows


def select_one(table: str, where: str, params: list) -> dict | None:
    rows = select_all(table, where, params)
    return rows[0] if rows else None


def update(table: str, data: dict, where: str, params: list):
    conn = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in data.keys())
    conn.execute(f"UPDATE {table} SET {set_clause} WHERE {where}", list(data.values()) + params)
    conn.commit()
    conn.close()


def delete(table: str, where: str, params: list):
    conn = get_db()
    conn.execute(f"DELETE FROM {table} WHERE {where}", params)
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    row = select_one("settings", "key = ?", [key])
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [key, value],
    )
    conn.commit()
    conn.close()
