import logging
from typing import Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ── Connection ────────────────────────────────────────────────────────────────

async def verify_connection(api_key: str) -> dict:
    """Return workspace info or raise on auth failure."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE_URL}/users/me", headers=_headers(api_key))
        resp.raise_for_status()
        data = resp.json()
        return {
            "connected": True,
            "workspace_name": data.get("name", ""),
            "bot_id": data.get("id", ""),
        }


# ── Database query ─────────────────────────────────────────────────────────────

async def query_database(api_key: str, database_id: str,
                          filter_obj: Optional[dict] = None,
                          sorts: Optional[list] = None) -> list[dict]:
    """Return all pages from a Notion database, handling pagination."""
    pages = []
    start_cursor = None
    body: dict = {}
    if filter_obj:
        body["filter"] = filter_obj
    if sorts:
        body["sorts"] = sorts

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            if start_cursor:
                body["start_cursor"] = start_cursor
            resp = await client.post(
                f"{BASE_URL}/databases/{database_id}/query",
                headers=_headers(api_key),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            pages.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")

    return pages


# ── Database creation ─────────────────────────────────────────────────────────

async def create_characters_database(api_key: str, parent_page_id: str) -> str:
    """Create a Characters database in Notion and return its ID."""
    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": "Characters"}}],
        "properties": {
            "Name": {"title": {}},
            "Description": {"rich_text": {}},
            "Voice ID": {"rich_text": {}},
            "Reference Image URL": {"url": {}},
            "Project": {"rich_text": {}},
            "Created": {"created_time": {}},
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/databases",
            headers=_headers(api_key),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def create_scenes_database(api_key: str, parent_page_id: str) -> str:
    """Create a Scenes database in Notion and return its ID."""
    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": "Scenes"}}],
        "properties": {
            "Title": {"title": {}},
            "Scene Type": {
                "select": {
                    "options": [
                        {"name": "Dialogue", "color": "blue"},
                        {"name": "Action", "color": "red"},
                        {"name": "Transition", "color": "gray"},
                        {"name": "Voiceover", "color": "purple"},
                        {"name": "Montage", "color": "yellow"},
                        {"name": "General", "color": "green"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "Draft", "color": "gray"},
                        {"name": "Ready", "color": "blue"},
                        {"name": "Generating", "color": "yellow"},
                        {"name": "Generated", "color": "orange"},
                        {"name": "Final", "color": "green"},
                        {"name": "Error", "color": "red"},
                    ]
                }
            },
            "Script": {"rich_text": {}},
            "Model": {"rich_text": {}},
            "Duration (s)": {"number": {"format": "number"}},
            "Resolution": {
                "select": {
                    "options": [
                        {"name": "480p"},
                        {"name": "720p"},
                        {"name": "1080p"},
                        {"name": "4k"},
                    ]
                }
            },
            "Character": {"rich_text": {}},
            "Video Path": {"rich_text": {}},
            "Created": {"created_time": {}},
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/databases",
            headers=_headers(api_key),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()["id"]


# ── Page creation ──────────────────────────────────────────────────────────────

async def add_character_to_notion(api_key: str, database_id: str,
                                   name: str, description: str = "",
                                   voice_id: str = "",
                                   reference_image_url: str = "",
                                   project: str = "") -> str:
    """Create a character page in Notion and return the page ID."""
    props: dict = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Description": {"rich_text": [{"text": {"content": description}}]},
        "Voice ID": {"rich_text": [{"text": {"content": voice_id}}]},
        "Project": {"rich_text": [{"text": {"content": project}}]},
    }
    if reference_image_url:
        props["Reference Image URL"] = {"url": reference_image_url}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/pages",
            headers=_headers(api_key),
            json={"parent": {"database_id": database_id}, "properties": props},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def add_scene_to_notion(api_key: str, database_id: str,
                               title: str, scene_type: str, script: str,
                               model: str = "", duration: int = 5,
                               resolution: str = "1080p",
                               character_name: str = "") -> str:
    """Create a scene page in Notion and return the page ID."""
    props = {
        "Title": {"title": [{"text": {"content": title or "Untitled Scene"}}]},
        "Scene Type": {"select": {"name": scene_type.capitalize()}},
        "Status": {"select": {"name": "Draft"}},
        "Script": {"rich_text": [{"text": {"content": script[:2000]}}]},
        "Model": {"rich_text": [{"text": {"content": model}}]},
        "Duration (s)": {"number": duration},
        "Resolution": {"select": {"name": resolution}},
        "Character": {"rich_text": [{"text": {"content": character_name}}]},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/pages",
            headers=_headers(api_key),
            json={"parent": {"database_id": database_id}, "properties": props},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def update_scene_status(api_key: str, page_id: str,
                               status: str, video_path: str = "") -> None:
    """Update scene status and optional video path in Notion."""
    props: dict = {"Status": {"select": {"name": status.capitalize()}}}
    if video_path:
        props["Video Path"] = {"rich_text": [{"text": {"content": video_path}}]}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{BASE_URL}/pages/{page_id}",
            headers=_headers(api_key),
            json={"properties": props},
        )
        resp.raise_for_status()


# ── Page parsing helpers ───────────────────────────────────────────────────────

def _text(prop: dict) -> str:
    items = prop.get("rich_text", []) or prop.get("title", [])
    return "".join(i.get("plain_text", "") for i in items)


def _select(prop: dict) -> str:
    sel = prop.get("select")
    return sel["name"].lower() if sel else ""


def _number(prop: dict) -> Optional[int]:
    return prop.get("number")


def _url(prop: dict) -> str:
    return prop.get("url") or ""


def parse_character_page(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "notion_id": page["id"],
        "name": _text(props.get("Name", {})),
        "description": _text(props.get("Description", {})),
        "voice_id": _text(props.get("Voice ID", {})),
        "reference_image_url": _url(props.get("Reference Image URL", {})),
        "project": _text(props.get("Project", {})),
    }


def parse_scene_page(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "notion_id": page["id"],
        "title": _text(props.get("Title", {})),
        "scene_type": _select(props.get("Scene Type", {})) or "general",
        "status": _select(props.get("Status", {})) or "draft",
        "script": _text(props.get("Script", {})),
        "model": _text(props.get("Model", {})),
        "duration": _number(props.get("Duration (s)", {})) or 5,
        "resolution": _select(props.get("Resolution", {})) or "1080p",
        "character": _text(props.get("Character", {})),
    }


# ── High-level helpers ────────────────────────────────────────────────────────

async def fetch_all_characters(api_key: str, database_id: str) -> list[dict]:
    pages = await query_database(api_key, database_id)
    return [parse_character_page(p) for p in pages]


async def fetch_all_scenes(api_key: str, database_id: str) -> list[dict]:
    pages = await query_database(api_key, database_id)
    return [parse_scene_page(p) for p in pages]
