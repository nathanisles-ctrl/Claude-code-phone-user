import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: list[str], description: str = "") -> subprocess.CompletedProcess:
    """Run ffmpeg with the given args, raise on non-zero exit."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args
    logger.info("ffmpeg %s: %s", description, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({description}):\n{result.stderr}")
    return result


def assemble_video(
    video_path: Path,
    audio_path: Optional[Path],
    captions_srt: Optional[Path],
    output_path: Path,
    fade_duration: float = 0.5,
    background_music: Optional[Path] = None,
    music_volume: float = 0.15,
) -> Path:
    """
    Combine video + voiceover + captions + optional background music into final MP4.

    Steps:
    1. Attach voiceover audio to video
    2. Burn-in SRT captions via ffmpeg subtitles filter
    3. Mix in optional background music at reduced volume
    4. Apply fade-in/fade-out
    5. Write H.264/AAC MP4 to output_path
    """
    if not _ffmpeg_available():
        raise EnvironmentError(
            "ffmpeg is not installed or not on PATH. "
            "Install with: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_path.parent / "_tmp"
    tmp_dir.mkdir(exist_ok=True)

    current = video_path

    # Step 1: Attach audio
    if audio_path and audio_path.exists() and audio_path.stat().st_size > 0:
        audio_out = tmp_dir / "with_audio.mp4"
        _run_ffmpeg(
            [
                "-i", str(current),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                str(audio_out),
            ],
            description="attach audio",
        )
        current = audio_out

    # Step 2: Mix background music (if provided)
    if background_music and background_music.exists():
        music_out = tmp_dir / "with_music.mp4"
        _run_ffmpeg(
            [
                "-i", str(current),
                "-i", str(background_music),
                "-filter_complex",
                f"[0:a][1:a]amix=inputs=2:weights=1 {music_volume}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                str(music_out),
            ],
            description="mix background music",
        )
        current = music_out

    # Step 3: Burn-in captions
    if captions_srt and captions_srt.exists() and captions_srt.stat().st_size > 0:
        caption_out = tmp_dir / "with_captions.mp4"
        # Escape path for ffmpeg filter
        srt_escaped = str(captions_srt).replace("\\", "/").replace(":", "\\:")
        subtitle_style = (
            "FontName=Inter,"
            "FontSize=18,"
            "PrimaryColour=&H00FFFFFF,"      # white text
            "BackColour=&H8C000000,"         # semi-transparent black background
            "BorderStyle=3,"                  # opaque box
            "Alignment=2,"                    # bottom center
            "MarginV=40"
        )
        _run_ffmpeg(
            [
                "-i", str(current),
                "-vf", f"subtitles='{srt_escaped}':force_style='{subtitle_style}'",
                "-c:a", "copy",
                str(caption_out),
            ],
            description="burn captions",
        )
        current = caption_out

    # Step 4: Fade in/out + final encode to H.264/AAC
    # Get video duration for fade-out timing
    duration_result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(current),
        ],
        capture_output=True, text=True,
    )
    try:
        duration = float(duration_result.stdout.strip())
    except (ValueError, AttributeError):
        duration = 10.0  # fallback

    fade_start = max(0.0, duration - fade_duration)

    _run_ffmpeg(
        [
            "-i", str(current),
            "-vf", f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_start}:d={fade_duration}",
            "-af", f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={fade_start}:d={fade_duration}",
            "-c:v", "libx264",
            "-crf", "20",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ],
        description="final encode",
    )

    # Cleanup tmp
    import shutil as _shutil
    _shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info(
        "Assembly complete: %s (%.1f MB)",
        output_path,
        output_path.stat().st_size / 1_000_000,
    )
    return output_path


def get_video_duration(video_path: Path) -> float:
    """Return video duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def concatenate_videos(video_paths: list[Path], output_path: Path) -> Path:
    """Concatenate multiple MP4 files into one using ffmpeg concat demuxer."""
    if not _ffmpeg_available():
        raise EnvironmentError("ffmpeg not found")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.parent / "_concat_list.txt"

    with open(list_file, "w") as f:
        for p in video_paths:
            f.write(f"file '{p.resolve()}'\n")

    _run_ffmpeg(
        [
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path),
        ],
        description="concatenate",
    )
    list_file.unlink(missing_ok=True)
    return output_path
