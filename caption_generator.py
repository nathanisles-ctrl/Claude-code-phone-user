import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Caption style constants
CAPTION_STYLE = {
    "color": "#FFFFFF",
    "font": "Inter, Arial, sans-serif",
    "font_size": "18px",
    "position": "10%",          # distance from bottom
    "max_width": "90%",
    "background": "rgba(0,0,0,0.55)",
    "padding": "4px 12px",
    "border_radius": "4px",
}

WORDS_PER_MINUTE = 150
CHARS_PER_LINE = 42


def estimate_duration(text: str) -> float:
    """Estimate how long it takes to speak `text` in seconds."""
    words = len(text.split())
    return max(1.0, (words / WORDS_PER_MINUTE) * 60)


def split_into_lines(text: str, max_chars: int = CHARS_PER_LINE) -> list[str]:
    """Break text into display lines of at most max_chars."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def format_vtt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def format_srt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


DIALOGUE_PATTERN = re.compile(
    r'^\[(?P<character>[^\]]+)\]:\s*"(?P<text>[^"]+)"',
    re.MULTILINE,
)


def parse_segments(script: str) -> list[dict]:
    """Return timed caption segments from a script."""
    dialogues = list(DIALOGUE_PATTERN.finditer(script))
    segments: list[dict] = []
    current_time = 0.0

    if dialogues:
        for match in dialogues:
            character = match.group("character").strip()
            text = match.group("text").strip()
            dur = estimate_duration(text)
            segments.append({
                "start": current_time,
                "end": current_time + dur,
                "character": character,
                "text": text,
            })
            current_time += dur + 0.3  # small gap between lines
    else:
        # Treat whole script as narration — break into 6-word chunks
        words = script.split()
        chunk_size = 6
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            dur = estimate_duration(chunk)
            segments.append({
                "start": current_time,
                "end": current_time + dur,
                "character": "",
                "text": chunk,
            })
            current_time += dur + 0.2

    return segments


def generate_vtt(script: str, output_path: Path, total_duration: Optional[float] = None) -> Path:
    """Generate a WebVTT subtitle file from a script."""
    segments = parse_segments(script)
    if total_duration:
        # Scale timing to fit video duration
        natural_end = segments[-1]["end"] if segments else 1.0
        scale = total_duration / natural_end if natural_end > 0 else 1.0
        for seg in segments:
            seg["start"] *= scale
            seg["end"] *= scale

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, seg in enumerate(segments, 1):
            lines = split_into_lines(seg["text"])
            display = "\n".join(lines)
            if seg["character"]:
                display = f"<c.character>{seg['character']}:</c.character> {display}"
            f.write(f"{i}\n")
            f.write(f"{format_vtt_timestamp(seg['start'])} --> {format_vtt_timestamp(seg['end'])}\n")
            f.write(f"{display}\n\n")

    logger.info("VTT captions written: %s (%d segments)", output_path, len(segments))
    return output_path


def generate_srt(script: str, output_path: Path, total_duration: Optional[float] = None) -> Path:
    """Generate an SRT subtitle file from a script."""
    segments = parse_segments(script)
    if total_duration:
        natural_end = segments[-1]["end"] if segments else 1.0
        scale = total_duration / natural_end if natural_end > 0 else 1.0
        for seg in segments:
            seg["start"] *= scale
            seg["end"] *= scale

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            lines = split_into_lines(seg["text"])
            display = "\n".join(lines)
            if seg["character"]:
                display = f"{seg['character']}: {display}"
            f.write(f"{i}\n")
            f.write(f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n")
            f.write(f"{display}\n\n")

    logger.info("SRT captions written: %s (%d segments)", output_path, len(segments))
    return output_path


def generate_captions(script: str, output_dir: Path, base_name: str,
                       total_duration: Optional[float] = None) -> dict:
    """Generate both VTT and SRT files. Returns paths dict."""
    vtt_path = output_dir / f"{base_name}.vtt"
    srt_path = output_dir / f"{base_name}.srt"
    generate_vtt(script, vtt_path, total_duration)
    generate_srt(script, srt_path, total_duration)
    return {"vtt": str(vtt_path), "srt": str(srt_path)}
