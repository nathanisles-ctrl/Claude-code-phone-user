import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from config import settings

logger = logging.getLogger(__name__)

DB_PATH = settings.DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    notion_workspace_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    notion_id TEXT DEFAULT '',
    voice_id TEXT DEFAULT '',
    reference_image_url TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    character_id INTEGER,
    title TEXT DEFAULT '',
    scene_type TEXT NOT NULL DEFAULT 'general',
    script TEXT NOT NULL DEFAULT '',
    model TEXT DEFAULT '',
    duration INTEGER DEFAULT 5,
    resolution TEXT DEFAULT '1080p',
    status TEXT DEFAULT 'draft',
    notion_id TEXT DEFAULT '',
    previous_scene_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    file_path TEXT DEFAULT '',
    audio_path TEXT DEFAULT '',
    captions_path TEXT DEFAULT '',
    final_path TEXT DEFAULT '',
    generation_job_id TEXT DEFAULT '',
    model_used TEXT DEFAULT '',
    duration INTEGER,
    resolution TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    error_message TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    log_level TEXT DEFAULT 'info',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info("Database initialized at %s", DB_PATH)
    finally:
        conn.close()


def _now() -> str:
    return datetime.utcnow().isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── Projects ──────────────────────────────────────────────────────────────────

def create_project(name: str, description: str = "", notion_workspace_id: str = "") -> dict:
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO projects (name, description, notion_workspace_id, created_at, updated_at) VALUES (?,?,?,?,?)",
            (name, description, notion_workspace_id, now, now),
        )
        conn.commit()
        return get_project(cur.lastrowid)
    finally:
        conn.close()


def get_project(project_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_projects() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_project(project_id: int, **kwargs) -> Optional[dict]:
    kwargs["updated_at"] = _now()
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [project_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE projects SET {fields} WHERE id=?", values)
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()


def delete_project(project_id: int) -> bool:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ── Characters ────────────────────────────────────────────────────────────────

def create_character(project_id: int, name: str, description: str = "",
                     notion_id: str = "", voice_id: str = "",
                     reference_image_url: str = "") -> dict:
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO characters (project_id, name, description, notion_id, voice_id, reference_image_url, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (project_id, name, description, notion_id, voice_id, reference_image_url, now, now),
        )
        conn.commit()
        return get_character(cur.lastrowid)
    finally:
        conn.close()


def get_character(character_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (character_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_characters(project_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute("SELECT * FROM characters WHERE project_id=? ORDER BY name", (project_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM characters ORDER BY name").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_character(character_id: int, **kwargs) -> Optional[dict]:
    kwargs["updated_at"] = _now()
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [character_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE characters SET {fields} WHERE id=?", values)
        conn.commit()
        return get_character(character_id)
    finally:
        conn.close()


def delete_character(character_id: int) -> bool:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM characters WHERE id=?", (character_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ── Scenes ────────────────────────────────────────────────────────────────────

def create_scene(project_id: int, scene_type: str, script: str, title: str = "",
                 character_id: Optional[int] = None, model: str = "",
                 duration: int = 5, resolution: str = "1080p",
                 notion_id: str = "", previous_scene_id: Optional[int] = None) -> dict:
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO scenes (project_id, character_id, title, scene_type, script, model, duration, resolution, status, notion_id, previous_scene_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, character_id, title, scene_type, script, model, duration, resolution, "draft", notion_id, previous_scene_id, now, now),
        )
        conn.commit()
        return get_scene(cur.lastrowid)
    finally:
        conn.close()


def get_scene(scene_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_scenes(project_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    try:
        if project_id:
            rows = conn.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM scenes ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_scene(scene_id: int, **kwargs) -> Optional[dict]:
    kwargs["updated_at"] = _now()
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [scene_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE scenes SET {fields} WHERE id=?", values)
        conn.commit()
        return get_scene(scene_id)
    finally:
        conn.close()


# ── Videos ────────────────────────────────────────────────────────────────────

def create_video(scene_id: int, model_used: str = "", resolution: str = "") -> dict:
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO videos (scene_id, model_used, resolution, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (scene_id, model_used, resolution, "pending", now, now),
        )
        conn.commit()
        return get_video(cur.lastrowid)
    finally:
        conn.close()


def get_video(video_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_videos(scene_id: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    try:
        if scene_id:
            rows = conn.execute("SELECT * FROM videos WHERE scene_id=? ORDER BY created_at DESC", (scene_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM videos ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_video(video_id: int, **kwargs) -> Optional[dict]:
    kwargs["updated_at"] = _now()
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [video_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE videos SET {fields} WHERE id=?", values)
        conn.commit()
        return get_video(video_id)
    finally:
        conn.close()


def list_videos_all() -> list[dict]:
    return list_videos()


# ── Generation Logs ───────────────────────────────────────────────────────────

def add_log(video_id: int, message: str, level: str = "info") -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO generation_logs (video_id, log_level, message, created_at) VALUES (?,?,?,?)",
            (video_id, level, message, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_logs(video_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM generation_logs WHERE video_id=? ORDER BY created_at ASC",
            (video_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()
