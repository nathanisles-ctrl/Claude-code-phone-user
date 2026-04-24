from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class SceneType(str, Enum):
    dialogue = "dialogue"
    action = "action"
    transition = "transition"
    voiceover = "voiceover"
    montage = "montage"
    general = "general"


class Resolution(str, Enum):
    r480p = "480p"
    r720p = "720p"
    r1080p = "1080p"
    r4k = "4k"


class VideoModel(str, Enum):
    veo3 = "veo3"
    seedance2 = "seedance2"
    kling3 = "kling3"
    sora2 = "sora2"
    higgsfield = "higgsfield"
    auto = "auto"


class SceneStatus(str, Enum):
    draft = "draft"
    ready = "ready"
    generating = "generating"
    generated = "generated"
    final = "final"
    error = "error"


class VideoStatus(str, Enum):
    pending = "pending"
    generating_video = "generating_video"
    generating_audio = "generating_audio"
    generating_captions = "generating_captions"
    assembling = "assembling"
    completed = "completed"
    failed = "failed"


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    notion_workspace_id: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    notion_workspace_id: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    notion_workspace_id: str
    created_at: str
    updated_at: str


# ── Characters ────────────────────────────────────────────────────────────────

class CharacterCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    voice_id: str = ""
    reference_image_url: str = ""


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    voice_id: Optional[str] = None
    reference_image_url: Optional[str] = None
    notion_id: Optional[str] = None


class CharacterResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    notion_id: str
    voice_id: str
    reference_image_url: str
    created_at: str
    updated_at: str


# ── Scenes ────────────────────────────────────────────────────────────────────

class SceneCreate(BaseModel):
    project_id: int
    title: str = ""
    scene_type: SceneType = SceneType.general
    script: str = Field(..., min_length=1)
    character_id: Optional[int] = None
    model: VideoModel = VideoModel.auto
    duration: int = Field(default=5, ge=1, le=60)
    resolution: Resolution = Resolution.r1080p
    previous_scene_id: Optional[int] = None


class SceneUpdate(BaseModel):
    title: Optional[str] = None
    scene_type: Optional[SceneType] = None
    script: Optional[str] = None
    character_id: Optional[int] = None
    model: Optional[VideoModel] = None
    duration: Optional[int] = None
    resolution: Optional[Resolution] = None
    status: Optional[SceneStatus] = None
    notion_id: Optional[str] = None


class SceneResponse(BaseModel):
    id: int
    project_id: int
    character_id: Optional[int]
    title: str
    scene_type: str
    script: str
    model: str
    duration: int
    resolution: str
    status: str
    notion_id: str
    previous_scene_id: Optional[int]
    created_at: str
    updated_at: str


# ── Videos ────────────────────────────────────────────────────────────────────

class VideoGenerationRequest(BaseModel):
    scene_id: int
    model: VideoModel = VideoModel.auto
    resolution: Resolution = Resolution.r1080p
    generate_voiceover: bool = True
    generate_captions: bool = True


class VideoGenerationResponse(BaseModel):
    video_id: int
    scene_id: int
    status: str
    message: str


class VideoResponse(BaseModel):
    id: int
    scene_id: int
    file_path: str
    audio_path: str
    captions_path: str
    final_path: str
    generation_job_id: str
    model_used: str
    duration: Optional[int]
    resolution: str
    status: str
    error_message: str
    created_at: str
    updated_at: str


class VideoStatusResponse(BaseModel):
    video_id: int
    status: str
    progress_message: str
    final_path: str
    error_message: str
    logs: list[dict]


# ── Notion ────────────────────────────────────────────────────────────────────

class NotionConnectRequest(BaseModel):
    api_key: str
    database_id: str = ""


class NotionSetupRequest(BaseModel):
    api_key: str
    parent_page_id: str


class NotionStatusResponse(BaseModel):
    connected: bool
    workspace_name: str
    database_id: str
    message: str


# ── Voice ─────────────────────────────────────────────────────────────────────

class VoiceResponse(BaseModel):
    voice_id: str
    name: str
    preview_url: str
    category: str


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    higgsfield_configured: bool
    elevenlabs_configured: bool
    notion_configured: bool
    database: str
