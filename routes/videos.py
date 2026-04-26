import asyncio
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from models.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoResponse,
    VideoStatusResponse,
)
from config import settings
import database as db
import video_generator as vg
import voiceover_generator as vo
import caption_generator as cg
import video_assembler as va
import notion_manager as notion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/videos", tags=["Videos"])

# Limit concurrent generation pipelines to avoid resource exhaustion
_generation_semaphore: Optional[asyncio.Semaphore] = None


def _semaphore() -> asyncio.Semaphore:
    global _generation_semaphore
    if _generation_semaphore is None:
        _generation_semaphore = asyncio.Semaphore(3)
    return _generation_semaphore


async def _run_generation_pipeline(video_id: int, scene: dict,
                                    model: str, resolution: str,
                                    generate_voiceover: bool,
                                    generate_captions: bool) -> None:
    """Background task: generate video, voiceover, captions, and assemble."""
    base_name = f"scene_{scene['id']}_video_{video_id}"
    video_out = settings.OUTPUT_DIR / "videos" / f"{base_name}.mp4"
    audio_out = settings.OUTPUT_DIR / "audio" / f"{base_name}.mp3"
    caption_dir = settings.OUTPUT_DIR / "captions"
    final_out = settings.OUTPUT_DIR / "final" / f"{base_name}_final.mp4"

    def log(msg: str, level: str = "info") -> None:
        getattr(logger, level)(msg)
        db.add_log(video_id, msg, level)

    async with _semaphore():
        try:
            # ── Step 1: Generate video ────────────────────────────────────────
            db.update_video(video_id, status="generating_video")
            db.update_scene(scene["id"], status="generating")
            log(f"Starting video generation: model={model}, resolution={resolution}")

            prompt = scene["script"]

            ref_images = []
            if scene.get("character_id"):
                char = db.get_character(scene["character_id"])
                if char and char.get("reference_image_url"):
                    ref_images.append(char["reference_image_url"])

            async def progress_cb(state: str, attempt: int):
                log(f"Video generation status: {state} (poll #{attempt})")

            await vg.generate_video_full(
                prompt=prompt,
                output_path=video_out,
                model=model,
                duration=scene.get("duration", 5),
                resolution=resolution,
                reference_image_urls=ref_images or None,
                progress_callback=progress_cb,
            )
            db.update_video(video_id, file_path=str(video_out))
            log(f"Video generated: {video_out}")

            # ── Step 2: Voiceover ─────────────────────────────────────────────
            audio_path = None
            if generate_voiceover:
                db.update_video(video_id, status="generating_audio")
                log("Generating voiceover with ElevenLabs")
                try:
                    voice_map = {}
                    if scene.get("character_id"):
                        char = db.get_character(scene["character_id"])
                        if char and char.get("voice_id") and char.get("name"):
                            voice_map[char["name"]] = char["voice_id"]

                    audio_path = await vo.generate_voiceover(
                        script=scene["script"],
                        output_path=audio_out,
                        character_voice_map=voice_map,
                    )
                    db.update_video(video_id, audio_path=str(audio_path))
                    log(f"Voiceover generated: {audio_path}")
                except Exception as exc:
                    log(f"Voiceover generation failed (continuing without audio): {exc}", "warning")
                    audio_path = None

            # ── Step 3: Captions ──────────────────────────────────────────────
            captions_srt = None
            if generate_captions:
                db.update_video(video_id, status="generating_captions")
                log("Generating captions")
                try:
                    video_duration = va.get_video_duration(video_out)
                    cap_paths = cg.generate_captions(
                        script=scene["script"],
                        output_dir=caption_dir,
                        base_name=base_name,
                        total_duration=video_duration or None,
                    )
                    captions_srt = Path(cap_paths["srt"])
                    db.update_video(video_id, captions_path=cap_paths["vtt"])
                    log(f"Captions generated: {cap_paths}")
                except Exception as exc:
                    log(f"Caption generation failed (continuing without captions): {exc}", "warning")

            # ── Step 4: Assemble final video ──────────────────────────────────
            db.update_video(video_id, status="assembling")
            log("Assembling final video")
            try:
                va.assemble_video(
                    video_path=video_out,
                    audio_path=audio_path,
                    captions_srt=captions_srt,
                    output_path=final_out,
                )
                db.update_video(video_id, final_path=str(final_out), status="completed")
            except Exception as exc:
                log(f"Assembly failed ({exc}); using raw video as final output", "warning")
                db.update_video(video_id, final_path=str(video_out), status="completed")

            db.update_scene(scene["id"], status="generated")
            log("Generation pipeline complete")

            # Sync to Notion
            notion_id = scene.get("notion_id", "")
            if notion_id and settings.NOTION_API_KEY:
                try:
                    final = db.get_video(video_id)
                    await notion.update_scene_status(
                        api_key=settings.NOTION_API_KEY,
                        page_id=notion_id,
                        status="generated",
                        video_path=final.get("final_path", ""),
                    )
                except Exception as exc:
                    logger.warning("Notion status sync failed for video %d: %s", video_id, exc)

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Generation pipeline failed for video %d: %s", video_id, error_msg)
            db.update_video(video_id, status="failed", error_message=error_msg)
            db.update_scene(scene["id"], status="error")
            db.add_log(video_id, f"FAILED: {error_msg}", "error")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=VideoGenerationResponse, status_code=202)
async def generate_video(body: VideoGenerationRequest, background_tasks: BackgroundTasks):
    scene = db.get_scene(body.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    if not scene.get("script"):
        raise HTTPException(status_code=400, detail="Scene has no script")
    if not settings.HIGGSFIELD_API_ID or not settings.HIGGSFIELD_API_SECRET:
        raise HTTPException(status_code=503, detail="Higgsfield API not configured")

    model = body.model.value
    if model == "auto":
        model = settings.SCENE_TYPE_TO_MODEL.get(scene["scene_type"], "higgsfield")
    resolution = body.resolution.value

    video = db.create_video(scene_id=body.scene_id, model_used=model, resolution=resolution)

    background_tasks.add_task(
        _run_generation_pipeline,
        video_id=video["id"],
        scene=scene,
        model=model,
        resolution=resolution,
        generate_voiceover=body.generate_voiceover,
        generate_captions=body.generate_captions,
    )

    return VideoGenerationResponse(
        video_id=video["id"],
        scene_id=body.scene_id,
        status="pending",
        message=f"Generation started with model '{model}'. Poll /api/videos/{video['id']}/status for progress.",
    )


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    limit: Optional[int] = Query(None, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Results to skip"),
):
    return db.list_videos_all(limit=limit, offset=offset)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
async def get_video_status(video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    logs = db.get_logs(video_id)
    last_log = logs[-1]["message"] if logs else ""
    return VideoStatusResponse(
        video_id=video_id,
        status=video["status"],
        progress_message=last_log,
        final_path=video.get("final_path", ""),
        error_message=video.get("error_message", ""),
        logs=logs,
    )


@router.get("/{video_id}/download")
async def download_video(video_id: int):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Video not ready (status: {video['status']})")

    raw_path = video.get("final_path") or video.get("file_path")
    if not raw_path:
        raise HTTPException(status_code=404, detail="Video file path not recorded")

    # Prevent path traversal: resolve and confirm it lives inside OUTPUT_DIR
    video_path = Path(raw_path).resolve()
    output_dir = settings.OUTPUT_DIR.resolve()
    if not str(video_path).startswith(str(output_dir)):
        logger.error("Path traversal attempt for video %d: %s", video_id, raw_path)
        raise HTTPException(status_code=403, detail="Access denied")

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=video_path.name,
    )
