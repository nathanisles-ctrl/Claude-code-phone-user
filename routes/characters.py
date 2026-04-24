from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from models.schemas import CharacterCreate, CharacterUpdate, CharacterResponse
from config import settings
import database as db
import notion_manager as notion

router = APIRouter(prefix="/api/characters", tags=["Characters"])


@router.get("", response_model=list[CharacterResponse])
async def list_characters(
    project_id: Optional[int] = Query(None),
    from_notion: bool = Query(False),
):
    if from_notion and settings.NOTION_API_KEY and settings.NOTION_DATABASE_ID:
        try:
            notion_chars = await notion.fetch_all_characters(
                settings.NOTION_API_KEY, settings.NOTION_DATABASE_ID
            )
            # Upsert into local DB
            for nc in notion_chars:
                existing = [
                    c for c in db.list_characters()
                    if c.get("notion_id") == nc["notion_id"]
                ]
                if not existing and project_id:
                    db.create_character(
                        project_id=project_id,
                        name=nc["name"],
                        description=nc["description"],
                        notion_id=nc["notion_id"],
                        voice_id=nc["voice_id"],
                        reference_image_url=nc["reference_image_url"],
                    )
        except Exception as exc:
            pass  # Fall through to local DB on Notion errors

    return db.list_characters(project_id)


@router.post("", response_model=CharacterResponse, status_code=201)
async def create_character(body: CharacterCreate):
    notion_id = ""
    # Push to Notion if configured
    if settings.NOTION_API_KEY and settings.NOTION_DATABASE_ID:
        try:
            project = db.get_project(body.project_id)
            project_name = project["name"] if project else ""
            notion_id = await notion.add_character_to_notion(
                api_key=settings.NOTION_API_KEY,
                database_id=settings.NOTION_DATABASE_ID,
                name=body.name,
                description=body.description,
                voice_id=body.voice_id,
                reference_image_url=body.reference_image_url,
                project=project_name,
            )
        except Exception as exc:
            pass  # Save locally even if Notion fails

    return db.create_character(
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        notion_id=notion_id,
        voice_id=body.voice_id,
        reference_image_url=body.reference_image_url,
    )


@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: int):
    char = db.get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    return char


@router.put("/{character_id}", response_model=CharacterResponse)
async def update_character(character_id: int, body: CharacterUpdate):
    char = db.get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return char
    return db.update_character(character_id, **updates)


@router.delete("/{character_id}", status_code=204)
async def delete_character(character_id: int):
    char = db.get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete_character(character_id)
