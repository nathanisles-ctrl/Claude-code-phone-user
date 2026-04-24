import logging
from fastapi import APIRouter, HTTPException
from models.schemas import NotionConnectRequest, NotionSetupRequest, NotionStatusResponse
from config import settings
import notion_manager as notion
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notion", tags=["Notion"])


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
    """Verify and save Notion credentials at runtime (writes to in-memory settings)."""
    try:
        info = await notion.verify_connection(body.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Notion connection failed: {exc}")

    # Update in-memory settings (user must also update .env for persistence)
    settings.NOTION_API_KEY = body.api_key
    if body.database_id:
        settings.NOTION_DATABASE_ID = body.database_id

    return {
        "connected": True,
        "workspace_name": info.get("workspace_name", ""),
        "message": "Connected. Add NOTION_API_KEY and NOTION_DATABASE_ID to your .env file to persist.",
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
        chars_db_id = await notion.create_characters_database(body.api_key, body.parent_page_id)
        scenes_db_id = await notion.create_scenes_database(body.api_key, body.parent_page_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create Notion databases: {exc}")

    # Update settings
    settings.NOTION_API_KEY = body.api_key
    settings.NOTION_DATABASE_ID = scenes_db_id

    return {
        "success": True,
        "workspace": info.get("workspace_name", ""),
        "characters_database_id": chars_db_id,
        "scenes_database_id": scenes_db_id,
        "message": (
            f"Databases created! Add to your .env:\n"
            f"NOTION_API_KEY={body.api_key}\n"
            f"NOTION_DATABASE_ID={scenes_db_id}"
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
