"""Final video assembly — combines video + voiceover + captions using ffmpeg."""

import asyncio
import shutil
from pathlib import Path
from config import UPLOADS_DIR


class VideoAssembler:
    def __init__(self):
        self.assembled_dir = UPLOADS_DIR / "assembled"
        self._check_ffmpeg()

    @staticmethod
    def _check_ffmpeg():
        if not shutil.which("ffmpeg"):
            raise EnvironmentError(
                "ffmpeg not found. Install it with: sudo apt install ffmpeg  (or brew install ffmpeg on Mac)"
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def assemble(
        self,
        video_url: str,
        audio_path: str = "",
        srt_path: str = "",
        output_filename: str = "output.mp4",
        resolution: str = "720p",
    ) -> str:
        """
        Download the generated video then optionally mix in audio + captions.
        Returns the local path of the assembled MP4.
        """
        local_video = await self._download_video(video_url, output_filename)

        if audio_path and Path(audio_path).exists():
            mixed = await self._mix_audio(local_video, audio_path, output_filename.replace(".mp4", "_mixed.mp4"))
        else:
            mixed = local_video

        if srt_path and Path(srt_path).exists():
            final = await self._burn_captions(mixed, srt_path, output_filename.replace(".mp4", "_final.mp4"))
        else:
            final = mixed

        return final

    async def add_captions_only(self, video_path: str, srt_path: str, output_filename: str) -> str:
        return await self._burn_captions(video_path, srt_path, output_filename)

    async def concatenate_scenes(self, video_paths: list[str], output_filename: str) -> str:
        """Join multiple scene videos into one, with a crossfade transition."""
        out_path = str(self.assembled_dir / output_filename)
        list_file = self.assembled_dir / f"{output_filename}.txt"
        list_file.write_text("\n".join(f"file '{p}'" for p in video_paths))

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
            out_path,
        ]
        await self._run_ffmpeg(cmd)
        list_file.unlink(missing_ok=True)
        return out_path

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _download_video(self, url: str, output_filename: str) -> str:
        """Download a remote video to uploads/video/ and return local path."""
        import httpx
        out_path = UPLOADS_DIR / "video" / output_filename
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=1024 * 64):
                        f.write(chunk)
        return str(out_path)

    async def _mix_audio(self, video_path: str, audio_path: str, output_filename: str) -> str:
        out_path = str(self.assembled_dir / output_filename)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            out_path,
        ]
        await self._run_ffmpeg(cmd)
        return out_path

    async def _burn_captions(self, video_path: str, srt_path: str, output_filename: str) -> str:
        out_path = str(self.assembled_dir / output_filename)
        # Escape special chars in path for ffmpeg filter
        safe_srt = srt_path.replace("\\", "/").replace(":", "\\:")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles={safe_srt}:force_style='Fontname=Inter,Fontsize=18,PrimaryColour=&HFFFFFF,Outline=1,Shadow=0,BackColour=&H80000000,BorderStyle=3,Alignment=2,MarginV=30'",
            "-c:a", "copy",
            out_path,
        ]
        await self._run_ffmpeg(cmd)
        return out_path

    @staticmethod
    async def _run_ffmpeg(cmd: list[str]):
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {stderr.decode()[-2000:]}")

    @staticmethod
    def resolution_scale(resolution: str) -> str:
        """Return ffmpeg scale filter string for the given resolution label."""
        return {
            "480p":  "scale=854:480",
            "720p":  "scale=1280:720",
            "1080p": "scale=1920:1080",
            "4K":    "scale=3840:2160",
        }.get(resolution, "scale=1280:720")
