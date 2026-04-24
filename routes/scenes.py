from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from models.schemas import SceneCreate, SceneUpdate, SceneResponse
from config import settings
import database as db
import notion_manager as notion

router = APIRouter(prefix="/api/scenes", tags=["Scenes"])


@router.get("", response_model=list[SceneResponse])
async def list_scenes(project_id: Optional[int] = Query(None)):
    return db.list_scenes(project_id)


@router.post("", response_model=SceneResponse, status_code=201)
async def create_scene(body: SceneCreate):
    model = body.model.value
    if model == "auto":
        model = settings.SCENE_TYPE_TO_MODEL.get(body.scene_type.value, "higgsfield")

    notion_id = ""
    if settings.NOTION_API_KEY and settings.NOTION_DATABASE_ID:
        try:
            character_name = ""
            if body.character_id:
                char = db.get_character(body.character_id)
                if char:
                    character_name = char["name"]
            notion_id = await notion.add_scene_to_notion(
                api_key=settings.NOTION_API_KEY,
                database_id=settings.NOTION_DATABASE_ID,
                title=body.title,
                scene_type=body.scene_type.value,
                script=body.script,
                model=model,
                duration=body.duration,
                resolution=body.resolution.value,
                character_name=character_name,
            )
        except Exception:
            pass

    return db.create_scene(
        project_id=body.project_id,
        scene_type=body.scene_type.value,
        script=body.script,
        title=body.title,
        character_id=body.character_id,
        model=model,
        duration=body.duration,
        resolution=body.resolution.value,
        notion_id=notion_id,
        previous_scene_id=body.previous_scene_id,
    )


@router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(scene_id: int):
    scene = db.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.put("/{scene_id}", response_model=SceneResponse)
async def update_scene(scene_id: int, body: SceneUpdate):
    scene = db.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    updates = body.model_dump(exclude_none=True)
    # Convert enums to values
    for k, v in updates.items():
        if hasattr(v, "value"):
            updates[k] = v.value
    if not updates:
        return scene

    updated = db.update_scene(scene_id, **updates)

    # Sync status to Notion
    if scene.get("notion_id") and settings.NOTION_API_KEY and "status" in updates:
        try:
            await notion.update_scene_status(
                api_key=settings.NOTION_API_KEY,
                page_id=scene["notion_id"],
                status=updates["status"],
            )
        except Exception:
            pass

    return updated
