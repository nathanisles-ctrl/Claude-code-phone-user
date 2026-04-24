import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./studio.sqlite3")
    DATABASE_PATH: str = DATABASE_URL.replace("sqlite:///", "")

    # Notion
    NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")

    # Higgsfield
    HIGGSFIELD_API_ID: str = os.getenv("HIGGSFIELD_API_ID", "")
    HIGGSFIELD_API_SECRET: str = os.getenv("HIGGSFIELD_API_SECRET", "")
    HIGGSFIELD_BASE_URL: str = os.getenv("HIGGSFIELD_BASE_URL", "https://api.higgsfield.ai")

    # ElevenLabs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    ELEVENLABS_BASE_URL: str = "https://api.elevenlabs.io/v1"

    # Storage
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "uploads"))
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "output"))

    # Video models and their recommended scene types
    VIDEO_MODELS = {
        "veo3": {"name": "Veo 3", "scene_types": ["dialogue", "voiceover"], "provider": "google"},
        "seedance2": {"name": "Seedance 2", "scene_types": ["action"], "provider": "bytedance"},
        "kling3": {"name": "Kling 3.0", "scene_types": ["transition"], "provider": "kuaishou"},
        "sora2": {"name": "Sora 2", "scene_types": ["montage"], "provider": "openai"},
        "higgsfield": {"name": "Higgsfield", "scene_types": ["general"], "provider": "higgsfield"},
    }

    SCENE_TYPE_TO_MODEL = {
        "dialogue": "veo3",
        "action": "seedance2",
        "transition": "kling3",
        "voiceover": "veo3",
        "montage": "sora2",
        "general": "higgsfield",
    }

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of missing required config keys."""
        missing = []
        if not cls.HIGGSFIELD_API_ID:
            missing.append("HIGGSFIELD_API_ID")
        if not cls.HIGGSFIELD_API_SECRET:
            missing.append("HIGGSFIELD_API_SECRET")
        if not cls.ELEVENLABS_API_KEY:
            missing.append("ELEVENLABS_API_KEY")
        return missing

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (cls.OUTPUT_DIR / "videos").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "audio").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "captions").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "final").mkdir(exist_ok=True)


settings = Config()
