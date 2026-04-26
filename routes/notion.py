import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from dotenv import set_key
from models.schemas import NotionConnectRequest, NotionSetupRequest, NotionStatusResponse
from config import settings
import notion_manager as notion
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notion", tags=["Notion"])

_ENV_FILE = str(Path(__file__).parent.parent / ".env")


def _persist_notion_settings(**pairs: str) -> None:
    """Write Notion credentials to the .env file for persistence across restarts."""
    try:
        for key, value in pairs.items():
            set_key(_ENV_FILE, key, value)
    except Exception as exc:
        logger.warning("Could not persist Notion settings to .env: %s", exc)


@router.get("/status", response_model=NotionStatusResponse)
async def notion_status():
    if not settings.NOTION_API_KEY:
        return NotionStatusResponse(
            connected=False,
            workspace_name="",
            database_id="",
            message="NOTION_API_KEY not set in .env",
        )
    try:
        info = await notion.verify_connection(settings.NOTION_API_KEY)
        return NotionStatusResponse(
            connected=True,
            workspace_name=info.get("workspace_name", ""),
            database_id=settings.NOTION_DATABASE_ID,
            message="Connected",
        )
    except Exception as exc:
        return NotionStatusResponse(
            connected=False,
            workspace_name="",
            database_id="",
            message=str(exc),
        )


@router.post("/connect")
async def connect_notion(body: NotionConnectRequest):
    """Verify Notion credentials and persist them to .env for future restarts."""
    try:
        info = await notion.verify_connection(body.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Notion connection failed: {exc}")

    settings.NOTION_API_KEY = body.api_key
    env_pairs = {"NOTION_API_KEY": body.api_key}
    if body.database_id:
        settings.NOTION_DATABASE_ID = body.database_id
        env_pairs["NOTION_DATABASE_ID"] = body.database_id

    _persist_notion_settings(**env_pairs)

    return {
        "connected": True,
        "workspace_name": info.get("workspace_name", ""),
        "message": "Connected and credentials saved to .env for persistence.",
    }


@router.post("/setup")
async def setup_notion(body: NotionSetupRequest):
    """
    Create Characters and Scenes databases in the user's Notion workspace
    under the given parent page.
    """
    try:
        info = await notion.verify_connection(body.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Notion connection failed: {exc}")

    try:
        chars_db_id, scenes_db_id = await asyncio.gather(
            notion.create_characters_database(body.api_key, body.parent_page_id),
            notion.create_scenes_database(body.api_key, body.parent_page_id),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create Notion databases: {exc}")

    settings.NOTION_API_KEY = body.api_key
    settings.NOTION_DATABASE_ID = scenes_db_id

    _persist_notion_settings(
        NOTION_API_KEY=body.api_key,
        NOTION_DATABASE_ID=scenes_db_id,
    )

    return {
        "success": True,
        "workspace": info.get("workspace_name", ""),
        "characters_database_id": chars_db_id,
        "scenes_database_id": scenes_db_id,
        "message": (
            f"Databases created and credentials saved to .env!\n"
            f"Characters DB ID: {chars_db_id}\n"
            f"Scenes DB ID: {scenes_db_id}"
        ),
    }


@router.get("/characters")
async def fetch_notion_characters():
    if not settings.NOTION_API_KEY or not settings.NOTION_DATABASE_ID:
        raise HTTPException(status_code=503, detail="Notion not configured")
    try:
        return await notion.fetch_all_characters(settings.NOTION_API_KEY, settings.NOTION_DATABASE_ID)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/scenes")
async def fetch_notion_scenes():
    if not settings.NOTION_API_KEY or not settings.NOTION_DATABASE_ID:
        raise HTTPException(status_code=503, detail="Notion not configured")
    try:
        return await notion.fetch_all_scenes(settings.NOTION_API_KEY, settings.NOTION_DATABASE_ID)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
