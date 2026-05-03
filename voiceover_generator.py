"""ElevenLabs voiceover generation — dialogue parsing and audio synthesis."""

import re
import asyncio
import httpx
from pathlib import Path
from config import ELEVENLABS_BASE_URL, ELEVENLABS_API_KEY, UPLOADS_DIR


class VoiceoverGenerator:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or ELEVENLABS_API_KEY
        self.audio_dir = UPLOADS_DIR / "audio"

    @property
    def _headers(self) -> dict:
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

    # ── API ────────────────────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{ELEVENLABS_BASE_URL}/user",
                    headers={"xi-api-key": self.api_key},
                )
                if r.status_code == 200:
                    data = r.json()
                    return {"ok": True, "tier": data.get("subscription", {}).get("tier", "free")}
                return {"ok": False, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def list_voices(self) -> list:
        """Return available voices as [{id, name, preview_url, labels}]."""
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"{ELEVENLABS_BASE_URL}/voices",
                headers={"xi-api-key": self.api_key},
            )
            r.raise_for_status()
            voices = r.json().get("voices", [])
            return [
                {
                    "id":          v["voice_id"],
                    "name":        v["name"],
                    "preview_url": v.get("preview_url", ""),
                    "category":    v.get("category", ""),
                    "labels":      v.get("labels", {}),
                }
                for v in voices
            ]

    async def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_filename: str,
        model_id: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> str:
        """Generate audio for `text` and save to uploads/audio/. Returns file path."""
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability":        stability,
                "similarity_boost": similarity_boost,
            },
        }
        headers = {**self._headers, "Accept": "audio/mpeg"}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
                headers=headers,
                json=payload,
            )
            if r.status_code != 200:
                raise ValueError(f"ElevenLabs error {r.status_code}: {r.text}")
            out_path = self.audio_dir / output_filename
            out_path.write_bytes(r.content)
            return str(out_path)

    # ── Script parsing ─────────────────────────────────────────────────────────

    @staticmethod
    def parse_dialogue(script: str) -> list[dict]:
        """
        Parse lines of the form:
            [Character Name]: "dialogue text"
        Returns [{"character": str, "text": str}]
        Falls back to treating the whole script as a single unnamed block.
        """
        pattern = re.compile(r'^\[([^\]]+)\]:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
        matches = pattern.findall(script)
        if matches:
            return [{"character": m[0].strip(), "text": m[1].strip()} for m in matches]
        # No tagged dialogue — return full script as narrator block
        return [{"character": "Narrator", "text": script.strip()}]

    async def generate_scene_voiceover(
        self,
        script: str,
        character_voice_map: dict,
        scene_id: str,
        default_voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Rachel
    ) -> list[dict]:
        """
        Generate audio for every dialogue segment in the script.
        Returns list of {"character", "text", "audio_file"}.
        """
        segments = self.parse_dialogue(script)
        results = []
        for idx, seg in enumerate(segments):
            char = seg["character"]
            voice = character_voice_map.get(char, default_voice_id)
            filename = f"{scene_id}_{idx}_{char.lower().replace(' ', '_')}.mp3"
            try:
                path = await self.generate_audio(seg["text"], voice, filename)
                results.append({**seg, "audio_file": path, "status": "ok"})
            except Exception as e:
                results.append({**seg, "audio_file": "", "status": "error", "error": str(e)})
        return results

    async def combine_audio_segments(self, segment_paths: list[str], output_filename: str) -> str:
        """
        Concatenate multiple MP3 files using ffmpeg.
        Returns path of the combined file.
        """
        out_path = str(self.audio_dir / output_filename)
        if len(segment_paths) == 1:
            import shutil
            shutil.copy(segment_paths[0], out_path)
            return out_path

        # Write a concat list for ffmpeg
        list_path = self.audio_dir / f"{output_filename}.txt"
        list_path.write_text("\n".join(f"file '{p}'" for p in segment_paths))

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_path), "-c", "copy", out_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        list_path.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {stderr.decode()}")
        return out_path
