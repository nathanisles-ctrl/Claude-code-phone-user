import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
(UPLOADS_DIR / "audio").mkdir(exist_ok=True)
(UPLOADS_DIR / "video").mkdir(exist_ok=True)
(UPLOADS_DIR / "assembled").mkdir(exist_ok=True)

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
HIGGSFIELD_API_ID = os.getenv("HIGGSFIELD_API_ID", "5e328565-11ef-4469-9828-80b8b18ab200")
HIGGSFIELD_API_SECRET = os.getenv("HIGGSFIELD_API_SECRET", "fcf63d4b3ec9870b13d81898c0899552fe75c90928f051185585ad004741109")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "b20628fa260535f39389a4d46eaa4d97c9a3f7ed857a8559f3c3a9f72f0923f0")

SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")

# API Base URLs
HIGGSFIELD_BASE_URL = "https://api.higgsfield.ai"
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Model display names → API slugs
HIGGSFIELD_MODELS = {
    "veo-3":      {"display": "Veo 3",       "description": "Best for dialogue & voiceover scenes"},
    "seedance-2": {"display": "Seedance 2",   "description": "Best for action sequences"},
    "kling-3.0":  {"display": "Kling 3.0",   "description": "Best for transitions"},
    "sora-2":     {"display": "Sora 2",       "description": "Best for montages"},
    "wan-2.7":    {"display": "Wan 2.7",      "description": "Versatile cinematic model"},
}

SCENE_TYPE_MODEL_MAP = {
    "Dialogue":   "veo-3",
    "Action":     "seedance-2",
    "Transition": "kling-3.0",
    "Voiceover":  "veo-3",
    "Montage":    "sora-2",
}

VIDEO_RESOLUTIONS = ["480p", "720p", "1080p", "4K"]
VIDEO_DURATIONS   = ["5s", "10s", "15s"]
SCENE_TYPES       = ["Dialogue", "Action", "Transition", "Voiceover", "Montage"]
SCENE_STATUSES    = ["Draft", "Ready", "Generated", "Final"]
