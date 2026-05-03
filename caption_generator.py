"""Caption/subtitle generation — produces SRT files from script text."""

import re
from pathlib import Path
from config import UPLOADS_DIR


class CaptionGenerator:
    WORDS_PER_SECOND = 2.5  # average speech rate

    def __init__(self):
        self.upload_dir = UPLOADS_DIR

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_srt(self, script: str, total_duration_seconds: float, output_filename: str) -> str:
        """
        Break the script into timed subtitle blocks and write an SRT file.
        Returns the file path.
        """
        blocks = self._split_into_blocks(script)
        timed = self._assign_timecodes(blocks, total_duration_seconds)
        srt_content = self._render_srt(timed)

        out_path = self.upload_dir / "audio" / output_filename
        out_path.write_text(srt_content, encoding="utf-8")
        return str(out_path)

    def generate_ass(self, script: str, total_duration_seconds: float, output_filename: str) -> str:
        """
        Generate an ASS subtitle file with styled captions (white, bottom, semi-transparent bg).
        Returns the file path.
        """
        blocks = self._split_into_blocks(script)
        timed = self._assign_timecodes(blocks, total_duration_seconds)
        ass_content = self._render_ass(timed)

        out_path = self.upload_dir / "audio" / output_filename
        out_path.write_text(ass_content, encoding="utf-8")
        return str(out_path)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _split_into_blocks(self, script: str) -> list[str]:
        """Split script into caption-sized chunks (~8 words each)."""
        # Strip character tags like [Name]: "..."
        clean = re.sub(r'^\[([^\]]+)\]:\s*["\']?', '', script, flags=re.MULTILINE)
        clean = re.sub(r'["\']$', '', clean, flags=re.MULTILINE)

        words = clean.split()
        blocks, chunk_size = [], 8
        for i in range(0, len(words), chunk_size):
            blocks.append(" ".join(words[i:i + chunk_size]))
        return [b for b in blocks if b.strip()]

    def _assign_timecodes(self, blocks: list[str], total_duration: float) -> list[dict]:
        """Assign start/end times to each block proportionally by word count."""
        if not blocks:
            return []
        total_words = sum(len(b.split()) for b in blocks)
        if total_words == 0:
            return []

        timed, cursor = [], 0.0
        for block in blocks:
            word_count = len(block.split())
            duration = (word_count / total_words) * total_duration
            duration = max(duration, 1.0)  # at least 1 second
            timed.append({
                "text":  block,
                "start": cursor,
                "end":   min(cursor + duration, total_duration),
            })
            cursor += duration
        return timed

    @staticmethod
    def _fmt_srt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _fmt_ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    def _render_srt(self, timed: list[dict]) -> str:
        lines = []
        for idx, item in enumerate(timed, start=1):
            lines.append(str(idx))
            lines.append(f"{self._fmt_srt_time(item['start'])} --> {self._fmt_srt_time(item['end'])}")
            lines.append(item["text"])
            lines.append("")
        return "\n".join(lines)

    def _render_ass(self, timed: list[dict]) -> str:
        header = (
            "[Script Info]\n"
            "Title: Creative Video Studio Captions\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1280\n"
            "PlayResY: 720\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            # White text, semi-transparent black box, Inter font, bottom center
            "Style: Default,Inter,36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,3,0,0,2,20,20,30,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        events = []
        for item in timed:
            start = self._fmt_ass_time(item["start"])
            end   = self._fmt_ass_time(item["end"])
            text  = item["text"].replace("\n", "\\N")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        return header + "\n".join(events)
