"""Notion API integration — database creation, querying, and mutation."""

import httpx
from config import NOTION_BASE_URL, NOTION_VERSION


class NotionManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ── Connection ─────────────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{NOTION_BASE_URL}/users/me", headers=self.headers)
            if r.status_code == 200:
                data = r.json()
                return {"ok": True, "name": data.get("name", "Unknown")}
            return {"ok": False, "error": r.text}

    # ── Database creation ──────────────────────────────────────────────────────

    async def create_characters_database(self, parent_page_id: str) -> dict:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "Characters"}}],
            "properties": {
                "Name":               {"title": {}},
                "Voice ID":           {"rich_text": {}},
                "Reference Image":    {"files": {}},
                "Description":        {"rich_text": {}},
                "Is Main Character":  {"checkbox": {}},
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{NOTION_BASE_URL}/databases", headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()

    async def create_scenes_database(self, parent_page_id: str) -> dict:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "Scenes"}}],
            "properties": {
                "Title": {"title": {}},
                "Scene Number": {"number": {}},
                "Script": {"rich_text": {}},
                "Scene Type": {
                    "select": {
                        "options": [
                            {"name": "Dialogue",   "color": "blue"},
                            {"name": "Action",     "color": "red"},
                            {"name": "Transition", "color": "green"},
                            {"name": "Voiceover",  "color": "purple"},
                            {"name": "Montage",    "color": "orange"},
                        ]
                    }
                },
                "Model": {
                    "select": {
                        "options": [
                            {"name": "Veo 3",       "color": "blue"},
                            {"name": "Seedance 2",  "color": "green"},
                            {"name": "Kling 3.0",  "color": "orange"},
                            {"name": "Sora 2",      "color": "purple"},
                            {"name": "Wan 2.7",     "color": "yellow"},
                        ]
                    }
                },
                "Duration": {
                    "select": {
                        "options": [
                            {"name": "5s"},
                            {"name": "10s"},
                            {"name": "15s"},
                        ]
                    }
                },
                "Status": {
                    "select": {
                        "options": [
                            {"name": "Draft",     "color": "gray"},
                            {"name": "Ready",     "color": "blue"},
                            {"name": "Generated", "color": "green"},
                            {"name": "Final",     "color": "purple"},
                        ]
                    }
                },
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{NOTION_BASE_URL}/databases", headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()

    # ── Query ──────────────────────────────────────────────────────────────────

    async def query_database(self, database_id: str, filter_: dict = None) -> list:
        results, has_more, cursor = [], True, None
        async with httpx.AsyncClient(timeout=30) as client:
            while has_more:
                body: dict = {"page_size": 100}
                if cursor:
                    body["start_cursor"] = cursor
                if filter_:
                    body["filter"] = filter_
                r = await client.post(
                    f"{NOTION_BASE_URL}/databases/{database_id}/query",
                    headers=self.headers,
                    json=body,
                )
                r.raise_for_status()
                data = r.json()
                results.extend(data.get("results", []))
                has_more = data.get("has_more", False)
                cursor = data.get("next_cursor")
        return results

    # ── Pages ──────────────────────────────────────────────────────────────────

    async def create_character_page(self, db_id: str, char: dict) -> dict:
        props = {
            "Name":              {"title": [{"text": {"content": char.get("name", "")}}]},
            "Voice ID":          {"rich_text": [{"text": {"content": char.get("voice_id", "")}}]},
            "Description":       {"rich_text": [{"text": {"content": char.get("description", "")}}]},
            "Is Main Character": {"checkbox": bool(char.get("is_main_character", False))},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{NOTION_BASE_URL}/pages",
                headers=self.headers,
                json={"parent": {"database_id": db_id}, "properties": props},
            )
            r.raise_for_status()
            return r.json()

    async def create_scene_page(self, db_id: str, scene: dict) -> dict:
        model_display = {
            "veo-3":      "Veo 3",
            "seedance-2": "Seedance 2",
            "kling-3.0":  "Kling 3.0",
            "sora-2":     "Sora 2",
            "wan-2.7":    "Wan 2.7",
        }.get(scene.get("model", "veo-3"), "Veo 3")

        props = {
            "Title":        {"title": [{"text": {"content": scene.get("title", "")}}]},
            "Scene Number": {"number": scene.get("scene_number", 0)},
            "Script":       {"rich_text": [{"text": {"content": scene.get("script", "")[:2000]}}]},
            "Scene Type":   {"select": {"name": scene.get("scene_type", "Dialogue")}},
            "Model":        {"select": {"name": model_display}},
            "Duration":     {"select": {"name": scene.get("duration", "10s")}},
            "Status":       {"select": {"name": scene.get("status", "Draft")}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{NOTION_BASE_URL}/pages",
                headers=self.headers,
                json={"parent": {"database_id": db_id}, "properties": props},
            )
            r.raise_for_status()
            return r.json()

    async def update_scene_status(self, page_id: str, status: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(
                f"{NOTION_BASE_URL}/pages/{page_id}",
                headers=self.headers,
                json={"properties": {"Status": {"select": {"name": status}}}},
            )
            r.raise_for_status()
            return r.json()

    async def update_page(self, page_id: str, properties: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(
                f"{NOTION_BASE_URL}/pages/{page_id}",
                headers=self.headers,
                json={"properties": properties},
            )
            r.raise_for_status()
            return r.json()

    # ── Parsers ────────────────────────────────────────────────────────────────

    def parse_character(self, page: dict) -> dict:
        p = page.get("properties", {})
        return {
            "notion_id": page["id"],
            "name":               self._title(p.get("Name")),
            "voice_id":           self._rich_text(p.get("Voice ID")),
            "description":        self._rich_text(p.get("Description")),
            "is_main_character":  self._checkbox(p.get("Is Main Character")),
        }

    def parse_scene(self, page: dict) -> dict:
        p = page.get("properties", {})
        model_map = {
            "Veo 3":      "veo-3",
            "Seedance 2": "seedance-2",
            "Kling 3.0":  "kling-3.0",
            "Sora 2":     "sora-2",
            "Wan 2.7":    "wan-2.7",
        }
        raw_model = self._select(p.get("Model")) or "Veo 3"
        return {
            "notion_id":    page["id"],
            "scene_number": self._number(p.get("Scene Number")) or 0,
            "title":        self._title(p.get("Title")),
            "script":       self._rich_text(p.get("Script")),
            "scene_type":   self._select(p.get("Scene Type")) or "Dialogue",
            "model":        model_map.get(raw_model, "veo-3"),
            "duration":     self._select(p.get("Duration")) or "10s",
            "status":       self._select(p.get("Status")) or "Draft",
        }

    def _title(self, prop) -> str:
        if not prop:
            return ""
        return "".join(r.get("plain_text", "") for r in prop.get("title", []))

    def _rich_text(self, prop) -> str:
        if not prop:
            return ""
        return "".join(r.get("plain_text", "") for r in prop.get("rich_text", []))

    def _select(self, prop) -> str | None:
        if not prop:
            return None
        s = prop.get("select")
        return s.get("name") if s else None

    def _checkbox(self, prop) -> bool:
        return bool(prop.get("checkbox", False)) if prop else False

    def _number(self, prop):
        return prop.get("number") if prop else None
