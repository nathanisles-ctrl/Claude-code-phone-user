import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = settings.ELEVENLABS_BASE_URL

# Default voice ID — Rachel (warm, clear)
DEFAULT_VOICE_ID = settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"


def _headers() -> dict:
    return {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }


def _json_headers() -> dict:
    return {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }


# ── Voice management ──────────────────────────────────────────────────────────

async def list_voices() -> list[dict]:
    """Return all available ElevenLabs voices."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ELEVENLABS_BASE}/voices",
            headers=_json_headers(),
        )
        if resp.status_code == 401:
            raise ValueError("ElevenLabs authentication failed — check API key")
        resp.raise_for_status()
        voices = resp.json().get("voices", [])
        return [
            {
                "voice_id": v["voice_id"],
                "name": v["name"],
                "preview_url": v.get("preview_url", ""),
                "category": v.get("category", ""),
            }
            for v in voices
        ]


# ── Script parsing ────────────────────────────────────────────────────────────

DIALOGUE_PATTERN = re.compile(
    r'^\[(?P<character>[^\]]+)\]:\s*"(?P<text>[^"]+)"',
    re.MULTILINE,
)


def parse_script_dialogues(script: str) -> list[dict]:
    """
    Parse [Character]: "dialogue text" lines from a script.
    Returns list of {character, text} dicts in order.
    """
    dialogues = []
    for match in DIALOGUE_PATTERN.finditer(script):
        dialogues.append({
            "character": match.group("character").strip(),
            "text": match.group("text").strip(),
        })
    if not dialogues:
        # Treat the whole script as narration
        clean = script.strip()
        if clean:
            dialogues.append({"character": "Narrator", "text": clean})
    return dialogues


# ── Audio generation ──────────────────────────────────────────────────────────

async def generate_speech(
    text: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    speed: float = 1.0,
) -> bytes:
    """Generate speech audio bytes for a single text/voice combination."""
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code == 401:
            raise ValueError("ElevenLabs authentication failed — check API key")
        resp.raise_for_status()
        return resp.content


async def generate_voiceover(
    script: str,
    output_path: Path,
    character_voice_map: Optional[dict] = None,
    default_voice_id: Optional[str] = None,
) -> Path:
    """
    Generate a full voiceover MP3 from a script.

    - Parses [Character]: "dialogue" lines.
    - Maps each character to a voice ID via character_voice_map.
    - Falls back to default_voice_id for unmapped characters.
    - Concatenates all audio segments and writes to output_path.
    """
    voice_map = character_voice_map or {}
    fallback_voice = default_voice_id or DEFAULT_VOICE_ID

    dialogues = parse_script_dialogues(script)
    if not dialogues:
        logger.warning("No dialogue found in script; generating silence placeholder")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"")
        return output_path

    logger.info("Generating voiceover for %d dialogue segments", len(dialogues))
    segments: list[bytes] = []

    for seg in dialogues:
        voice_id = voice_map.get(seg["character"], fallback_voice)
        if voice_id == fallback_voice and seg["character"] != "Narrator":
            logger.debug("  [%s] has no mapped voice, using default", seg["character"])
        logger.debug("  [%s] → voice %s: '%.60s'", seg["character"], voice_id, seg["text"])
        audio = await generate_speech(seg["text"], voice_id)
        segments.append(audio)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if len(segments) == 1:
        output_path.write_bytes(segments[0])
    else:
        await _concat_mp3_segments(segments, output_path)

    logger.info("Voiceover saved: %s (%.1f KB)", output_path, output_path.stat().st_size / 1000)
    return output_path


async def _concat_mp3_segments(segments: list[bytes], output_path: Path) -> None:
    """Concatenate MP3 segments properly using ffmpeg concat demuxer."""
    if not shutil.which("ffmpeg"):
        # ffmpeg unavailable — fall back to raw concatenation with a warning
        logger.warning("ffmpeg not found; MP3 segments concatenated as raw bytes (may cause glitches)")
        with open(output_path, "wb") as f:
            for seg_bytes in segments:
                f.write(seg_bytes)
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        seg_files: list[Path] = []
        for i, audio in enumerate(segments):
            seg_file = tmp_path / f"seg_{i:04d}.mp3"
            seg_file.write_bytes(audio)
            seg_files.append(seg_file)

        list_file = tmp_path / "concat.txt"
        list_file.write_text("\n".join(f"file '{f}'" for f in seg_files))

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg MP3 concat failed: {stderr.decode()[:500]}")


async def get_voice_info(voice_id: str) -> dict:
    """Return info for a specific voice."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ELEVENLABS_BASE}/voices/{voice_id}",
            headers=_json_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def get_api_usage() -> dict:
    """Return current API usage/quota."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ELEVENLABS_BASE}/user/subscription",
            headers=_json_headers(),
        )
        resp.raise_for_status()
        return resp.json()
